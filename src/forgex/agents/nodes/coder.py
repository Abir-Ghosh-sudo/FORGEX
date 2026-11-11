"""Coder workflow node."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forgex.agents.execution.action_executor import ActionExecutor
from forgex.agents.nodes.base import AgentNode
from forgex.agents.roles.coder import CoderRole
from forgex.core.orchestrator import ForgexState


class CoderNode(AgentNode):
    """Produces implementation actions and executes them against the workspace."""

    node_name = "coder"
    state_key = "implementation"

    def __init__(
        self,
        role: CoderRole | None = None,
        model: Any = None,
        action_executor: ActionExecutor | None = None,
    ) -> None:
        super().__init__(role or CoderRole(model=model))
        self.action_executor = action_executor or ActionExecutor()

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        update = await super().__call__(state)
        implementation = dict(update.get("implementation") or {})
        actions = implementation.get("actions") or []

        raw_workspace = state.get("workspace") or Path.cwd()
        workspace = Path(raw_workspace).expanduser().resolve()

        if actions and workspace.exists():
            exec_summary = await self.action_executor.execute_actions(workspace, actions)
            implementation["files_changed"] = exec_summary["files_changed"]
            implementation["execution_results"] = exec_summary["results"]

            if exec_summary["errors"]:
                existing_blockers = list(implementation.get("blockers") or [])
                existing_blockers.extend(exec_summary["errors"])
                implementation["blockers"] = existing_blockers

        update["implementation"] = implementation
        update["output"] = implementation
        if implementation.get("blockers"):
            update["error"] = "; ".join(str(item) for item in implementation["blockers"])
        return update


__all__ = ["CoderNode"]
