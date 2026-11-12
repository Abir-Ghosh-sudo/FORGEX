"""Tester role implementation."""

from __future__ import annotations

from typing import Any

from forgex.agents.prompts.tester import TESTER_PROMPT
from forgex.agents.roles.base import AgentRole
from forgex.core.exceptions import AgentError


class TesterRole(AgentRole):
    """Plans and evaluates verification/testing outcomes."""

    __test__ = False

    name = "tester"
    template = TESTER_PROMPT

    def validate(self, data: dict[str, Any]) -> None:
        super().validate(data)
        required = ("summary", "verified", "next_action")
        missing = [key for key in required if key not in data]
        if missing:
            raise AgentError(
                "Tester output missing required fields.",
                details={"missing": missing},
            )
        if not isinstance(data.get("verified"), bool):
            raise AgentError("Tester 'verified' must be a boolean.")


__all__ = ["TesterRole"]
