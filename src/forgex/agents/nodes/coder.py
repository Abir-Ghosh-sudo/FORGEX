"""Coder workflow node."""

from __future__ import annotations

from typing import Any

from forgex.agents.nodes.base import AgentNode
from forgex.agents.roles.coder import CoderRole
from forgex.core.orchestrator import ForgexState


class CoderNode(AgentNode):
    """Produces implementation actions/results in workflow state."""

    node_name = "coder"
    state_key = "implementation"

    def __init__(self, role: CoderRole | None = None, model: Any = None) -> None:
        super().__init__(role or CoderRole(model=model))

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        update = await super().__call__(state)
        implementation = update.get("implementation") or {}
        update["output"] = implementation
        if implementation.get("blockers"):
            update["error"] = "; ".join(str(item) for item in implementation["blockers"])
        return update


__all__ = ["CoderNode"]
