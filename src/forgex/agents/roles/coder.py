"""Coder role implementation."""

from __future__ import annotations

from typing import Any

from forgex.agents.prompts.coder import CODER_PROMPT
from forgex.agents.roles.base import AgentRole
from forgex.core.exceptions import AgentError


class CoderRole(AgentRole):
    """Produces implementation actions and change summaries."""

    name = "coder"
    template = CODER_PROMPT

    def validate(self, data: dict[str, Any]) -> None:
        super().validate(data)
        required = ("summary", "actions")
        missing = [key for key in required if key not in data]
        if missing:
            raise AgentError(
                "Coder output missing required fields.",
                details={"missing": missing},
            )
        if not isinstance(data.get("actions"), list):
            raise AgentError("Coder 'actions' must be a list.")


__all__ = ["CoderRole"]
