"""Planner role implementation."""

from __future__ import annotations

from typing import Any

from forgex.agents.prompts.planner import PLANNER_PROMPT
from forgex.agents.roles.base import AgentRole
from forgex.core.exceptions import AgentError


class PlannerRole(AgentRole):
    """Produces structured execution plans for coding tasks."""

    name = "planner"
    template = PLANNER_PROMPT

    def validate(self, data: dict[str, Any]) -> None:
        super().validate(data)
        required = ("summary", "steps")
        missing = [key for key in required if key not in data]
        if missing:
            raise AgentError(
                "Planner output missing required fields.",
                details={"missing": missing},
            )
        if not isinstance(data.get("steps"), list):
            raise AgentError("Planner 'steps' must be a list.")
        if not data.get("summary"):
            raise AgentError("Planner 'summary' cannot be empty.")


__all__ = ["PlannerRole"]
