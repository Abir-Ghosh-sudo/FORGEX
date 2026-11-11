"""LangGraph-powered autonomous workflow orchestration for FORGEX."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from forgex.core.exceptions import ExecutionError, TaskCancelledError
from forgex.core.task import ForgexTask, TaskManager, TaskStatus

logger = logging.getLogger(__name__)


class ForgexState(TypedDict, total=False):
    """Shared state passed between LangGraph workflow nodes."""

    task_id: str
    prompt: str
    workspace: str
    output: Any
    error: str
    current_agent: str
    messages: list[dict[str, Any]]
    metadata: dict[str, Any]
    plan: dict[str, Any]
    implementation: dict[str, Any]
    review: dict[str, Any]
    test_report: dict[str, Any]


NodeHandler = Callable[
    [ForgexState],
    Mapping[str, Any] | Awaitable[Mapping[str, Any]],
]

RouteHandler = Callable[
    [ForgexState],
    str | Awaitable[str],
]


class WorkflowOrchestrator:
    """Builds and executes autonomous LangGraph workflows."""

    def __init__(
        self,
        task_manager: TaskManager,
        workspace: Path,
        *,
        max_concurrency: int = 1,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1.")

        self.task_manager = task_manager
        self.workspace = workspace.expanduser().resolve()

        if not self.workspace.exists() or not self.workspace.is_dir():
            raise NotADirectoryError(f"Invalid workspace: {self.workspace}")

        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

        self._builder = StateGraph(ForgexState)
        self._compiled_graph: Any | None = None

        self._registered_nodes: set[str] = set()
        self._entry_point_set = False
        self._finish_points: set[str] = set()

    @property
    def is_compiled(self) -> bool:
        """Check whether the workflow graph has been compiled."""
        return self._compiled_graph is not None

    @property
    def registered_nodes(self) -> tuple[str, ...]:
        """Return the names of registered workflow nodes."""
        return tuple(sorted(self._registered_nodes))

    def _invalidate_graph(self) -> None:
        """Invalidate the compiled graph after configuration changes."""
        self._compiled_graph = None

    def register_node(
        self,
        name: str,
        handler: NodeHandler,
    ) -> None:
        """Register an executable workflow node."""

        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("Node name cannot be empty.")

        if normalized_name in {START, END}:
            raise ValueError("Reserved graph node name.")

        if normalized_name in self._registered_nodes:
            raise ValueError(f"Workflow node already exists: {normalized_name}")

        async def execute_node(
            state: ForgexState,
            config: Any = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            """Execute a node with task cancellation checks."""

            cfg = (
                config
                if isinstance(config, dict)
                else (getattr(config, "configurable", None) or {})
            )
            configurable = cfg.get("configurable", cfg) if isinstance(cfg, dict) else {}
            task_id = configurable.get("forgex_task_id") or state.get("task_id")

            if not isinstance(task_id, str):
                raise ExecutionError("Missing FORGEX task ID in graph configuration or state.")

            task = await self.task_manager.get_task(task_id)
            task.check_cancelled()

            logger.info(
                "Executing workflow node: %s (task=%s)",
                normalized_name,
                task_id,
            )

            result = handler(state)

            if inspect.isawaitable(result):
                result = await result

            task.check_cancelled()

            if not isinstance(result, Mapping):
                raise ExecutionError(f"Node '{normalized_name}' must return a mapping.")

            return dict(result)

        self._builder.add_node(normalized_name, execute_node)
        self._registered_nodes.add(normalized_name)
        self._invalidate_graph()

    def add_edge(self, source: str, destination: str) -> None:
        """Connect two workflow nodes."""

        self._validate_node_reference(source)
        self._validate_node_reference(destination)

        self._builder.add_edge(source, destination)
        self._invalidate_graph()

    def add_conditional_edges(
        self,
        source: str,
        router: RouteHandler,
        path_map: Mapping[str, str] | None = None,
    ) -> None:
        """Add conditional routing between workflow nodes."""

        self._validate_node_reference(source)

        if path_map:
            for destination in path_map.values():
                self._validate_node_reference(destination)

        self._builder.add_conditional_edges(
            source,
            router,
            dict(path_map) if path_map is not None else None,
        )

        self._invalidate_graph()

    def set_entry_point(self, node_name: str) -> None:
        """Set the first node executed by the workflow."""

        self._validate_node_reference(node_name)

        self._builder.add_edge(START, node_name)
        self._entry_point_set = True

        self._invalidate_graph()

    def set_finish_point(self, node_name: str) -> None:
        """Connect a workflow node to the graph's END node."""

        self._validate_node_reference(node_name)

        self._builder.add_edge(node_name, END)
        self._finish_points.add(node_name)

        self._invalidate_graph()

    def mark_finish_point(self, node_name: str) -> None:
        """Register a node as a finish point when terminated via conditional edges."""

        self._validate_node_reference(node_name)
        self._finish_points.add(node_name)

    def _validate_node_reference(self, name: str) -> None:
        """Validate a workflow node reference."""

        if name in {START, END}:
            return

        if name not in self._registered_nodes:
            raise ValueError(f"Workflow node is not registered: {name}")

    def compile(self) -> Any:
        """Compile and validate the LangGraph workflow."""

        if not self._registered_nodes:
            raise ExecutionError("Cannot compile an empty workflow.")

        if not self._entry_point_set:
            raise ExecutionError("Workflow entry point has not been configured.")

        if not self._finish_points:
            raise ExecutionError("Workflow requires at least one finish point.")

        try:
            self._compiled_graph = self._builder.compile()

        except Exception as exc:
            logger.exception("Workflow compilation failed.")

            raise ExecutionError(f"Could not compile workflow: {exc}") from exc

        logger.info(
            "Workflow compiled successfully with %d nodes.",
            len(self._registered_nodes),
        )

        return self._compiled_graph

    async def execute(
        self,
        task: ForgexTask,
        *,
        initial_state: Mapping[str, Any] | None = None,
        recursion_limit: int = 100,
    ) -> dict[str, Any]:
        """Execute a coding task through the compiled workflow."""

        if recursion_limit < 1:
            raise ValueError("recursion_limit must be at least 1.")

        if task.status not in {
            TaskStatus.PENDING,
            TaskStatus.QUEUED,
            TaskStatus.PAUSED,
        }:
            raise ExecutionError(f"Task cannot be executed from state: {task.status.value}")

        if self._compiled_graph is None:
            self.compile()

        async with self._semaphore:
            task = await self.task_manager.get_task(task.task_id)

            if task.status == TaskStatus.CANCELLED:
                raise TaskCancelledError()

            if task.status not in {
                TaskStatus.PENDING,
                TaskStatus.QUEUED,
                TaskStatus.PAUSED,
            }:
                raise ExecutionError(f"Task cannot start from state: {task.status.value}")

            await self.task_manager.transition(
                task.task_id,
                TaskStatus.RUNNING,
            )

            state: ForgexState = {
                "task_id": task.task_id,
                "prompt": task.prompt,
                "workspace": str(self.workspace),
                "output": None,
                "error": "",
                "current_agent": "",
                "messages": [],
                "metadata": dict(task.metadata),
            }

            if initial_state:
                reserved_keys = {
                    "task_id",
                    "prompt",
                    "workspace",
                }

                if reserved_keys.intersection(initial_state):
                    await self.task_manager.fail_task(
                        task.task_id,
                        "Initial state cannot override reserved fields.",
                    )

                    raise ExecutionError(
                        "Initial state cannot override task_id, prompt or workspace."
                    )

                state.update(initial_state)

            config = {
                "recursion_limit": recursion_limit,
                "configurable": {
                    "thread_id": task.task_id,
                    "forgex_task_id": task.task_id,
                },
            }

            try:
                result = await self._compiled_graph.ainvoke(
                    state,
                    config=config,
                )

                task = await self.task_manager.get_task(task.task_id)
                task.check_cancelled()

                if not isinstance(result, dict):
                    raise ExecutionError("Workflow returned an invalid state.")

                await self.task_manager.complete_task(
                    task.task_id,
                    result=result,
                )

                logger.info(
                    "Workflow completed successfully: task=%s",
                    task.task_id,
                )

                return result

            except asyncio.CancelledError:
                task = await self.task_manager.get_task(task.task_id)

                if not task.is_terminal:
                    await self.task_manager.cancel_task(task.task_id)

                logger.warning(
                    "Workflow execution cancelled: task=%s",
                    task.task_id,
                )

                raise

            except TaskCancelledError:
                task = await self.task_manager.get_task(task.task_id)

                if not task.is_terminal:
                    await self.task_manager.cancel_task(task.task_id)

                raise

            except Exception as exc:
                logger.exception(
                    "Workflow execution failed: task=%s",
                    task.task_id,
                )

                task = await self.task_manager.get_task(task.task_id)

                if not task.is_terminal:
                    await self.task_manager.fail_task(
                        task.task_id,
                        str(exc),
                    )

                raise ExecutionError(f"Workflow execution failed: {exc}") from exc


__all__ = [
    "ForgexState",
    "NodeHandler",
    "RouteHandler",
    "WorkflowOrchestrator",
]
