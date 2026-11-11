"""Planner workflow node."""

from __future__ import annotations

from typing import Any

from forgex.agents.nodes.base import AgentNode
from forgex.agents.roles.planner import PlannerRole
from forgex.core.orchestrator import ForgexState


class PlannerNode(AgentNode):
    """Generates an execution plan and stores it in workflow state."""

    node_name = "planner"
    state_key = "plan"

    def __init__(self, role: PlannerRole | None = None, model: Any = None) -> None:
        super().__init__(role or PlannerRole(model=model))

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        update = await super().__call__(state)
        update["output"] = update.get("plan")
        return update


__all__ = ["PlannerNode"]
