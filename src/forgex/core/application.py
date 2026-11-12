"""Main application composition root for FORGEX."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from forgex.core.context import ApplicationContext
from forgex.core.lifecycle import ApplicationLifecycle
from forgex.core.orchestrator import WorkflowOrchestrator
from forgex.core.task import ForgexTask, TaskManager
from forgex.runtime.supervisor import ProcessSupervisor
from forgex.security.permissions import PermissionManager
from forgex.security.policy import OperationType, SecurityPolicy, SecurityPolicyConfig
from forgex.tools.terminal import (
    PolicyTerminalAuthorizer,
    SupervisorTerminalRunner,
    TerminalExecutor,
    TerminalSecurityDecision,
)

logger = logging.getLogger(__name__)


class ForgexApplication:
    """Compose and manage the core FORGEX application services.

    The application acts as the composition root for:
    - Application context
    - Event bus
    - Task manager
    - Workflow orchestrator
    - Application lifecycle

    Other subsystems should obtain shared services through the
    application context instead of creating duplicate instances.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        max_concurrency: int = 1,
        metadata: Mapping[str, Any] | None = None,
        model_manager: Any | None = None,
        approval_handler: Callable[..., Any] | None = None,
        file_approval_handler: Callable[[str, str], Any] | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1.")

        workspace_path = Path(workspace).expanduser().resolve()

        if not workspace_path.exists():
            raise FileNotFoundError(f"Workspace does not exist: {workspace_path}")

        if not workspace_path.is_dir():
            raise NotADirectoryError(f"Workspace is not a directory: {workspace_path}")

        self.context = ApplicationContext(
            workspace=workspace_path,
            metadata=dict(metadata or {}),
        )

        self.task_manager = TaskManager(
            event_bus=self.context.event_bus,
        )

        self.orchestrator = WorkflowOrchestrator(
            task_manager=self.task_manager,
            workspace=self.context.workspace,
            max_concurrency=max_concurrency,
        )

        if model_manager is not None:
            self.model_manager = model_manager
        else:
            try:
                from forgex.models.manager import ModelManager

                self.model_manager = ModelManager()
            except Exception as exc:
                logger.debug("ModelManager initialization deferred: %s", exc)
                self.model_manager = None

        self.lifecycle = ApplicationLifecycle(self.context)
        self.approval_handler = approval_handler
        self.file_approval_handler = file_approval_handler
        self.process_supervisor = ProcessSupervisor()
        self.permission_manager = PermissionManager()
        self.security_policy = SecurityPolicy(
            self.permission_manager,
            SecurityPolicyConfig(workspace=workspace_path),
        )

        async def evaluate_terminal(request, command_text):
            evaluation = self.security_policy.evaluate(
                subject=request.subject,
                operation=OperationType.TERMINAL_EXECUTE,
                resource=command_text,
                workspace=request.working_directory,
                command=command_text,
            )
            if evaluation.requires_approval:
                return TerminalSecurityDecision(
                    allowed=False,
                    requires_approval=True,
                    reason=evaluation.decision.reason,
                    risk_level=evaluation.risk.value,
                )
            return TerminalSecurityDecision(
                allowed=evaluation.allowed,
                reason=evaluation.decision.reason,
                risk_level=evaluation.risk.value,
            )

        self.terminal_executor = TerminalExecutor(
            authorizer=PolicyTerminalAuthorizer(
                policy_evaluator=evaluate_terminal,
                approval_handler=approval_handler,
                workspace=workspace_path,
            ),
            runner=SupervisorTerminalRunner(self.process_supervisor),
        )

        self._started = False
        self._shutdown = False

        self._register_services()

        logger.debug(
            "FORGEX application initialized for workspace: %s",
            workspace_path,
        )

    def _register_services(self) -> None:
        """Register shared application services in the context."""

        self.context.register_service(
            "task_manager",
            self.task_manager,
        )

        self.context.register_service(
            "orchestrator",
            self.orchestrator,
        )

        self.context.register_service(
            "lifecycle",
            self.lifecycle,
        )

        if self.model_manager is not None:
            self.context.register_service(
                "model_manager",
                self.model_manager,
            )

    @property
    def workspace(self) -> Path:
        """Return the active workspace path."""

        return self.context.workspace

    @property
    def is_running(self) -> bool:
        """Whether the application has successfully started."""

        return self._started and not self._shutdown

    @property
    def is_shutdown(self) -> bool:
        """Whether application shutdown has completed."""

        return self._shutdown

    def _ensure_running(self) -> None:
        """Ensure an operation is performed on a running application."""

        if not self.is_running:
            raise RuntimeError(
                "FORGEX application is not running. Call 'await application.start()' first."
            )

    async def start(self) -> None:
        """Initialize the application and start its lifecycle."""

        if self._shutdown:
            raise RuntimeError(
                "A shut down FORGEX application cannot be restarted. "
                "Create a new application instance."
            )

        if self._started:
            logger.debug("FORGEX application is already running.")
            return

        # Register the default multi-agent workflow if no nodes are registered yet.
        if not self.orchestrator.registered_nodes:
            from forgex.agents.workflow import build_default_agent_workflow

            build_default_agent_workflow(
                self.orchestrator,
                model=self.model_manager,
                terminal_executor=self.terminal_executor,
                file_approval_handler=self.file_approval_handler,
            )

        if not self.orchestrator.is_compiled:
            self.orchestrator.compile()

        await self.lifecycle.startup()
        self._started = True

        logger.info(
            "FORGEX application started. Workspace: %s",
            self.workspace,
        )

    async def execute_task(
        self,
        task: ForgexTask | str,
        *,
        initial_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a task through the configured workflow orchestrator.

        Args:
            task: Task created by the application's TaskManager, or a prompt string.
            initial_state: Optional workflow-specific initial state.

        Returns:
            Final workflow state.
        """

        self._ensure_running()

        if isinstance(task, str):
            task = await self.task_manager.create_task(task)

        return await self.orchestrator.execute(
            task,
            initial_state=initial_state,
        )

    async def shutdown(self) -> None:
        """Gracefully shut down the application."""

        if self._shutdown:
            return

        if not self._started:
            try:
                await self.terminal_executor.close(wait=True)
                await self.process_supervisor.shutdown()
                await self.context.close()
            finally:
                self._shutdown = True
            logger.debug("Unstarted FORGEX application resources closed.")
            return

        try:
            await self.lifecycle.shutdown()
        finally:
            await self.terminal_executor.close(wait=True)
            await self.process_supervisor.shutdown()
            self._started = False
            self._shutdown = True

        logger.info("FORGEX application shut down.")

    async def close(self) -> None:
        """Alias for graceful application shutdown."""

        await self.shutdown()

    async def __aenter__(self) -> ForgexApplication:
        """Start the application when entering an async context."""

        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        """Shut down the application when leaving an async context."""

        await self.shutdown()


__all__ = [
    "ForgexApplication",
]
