"""Reviewer role implementation."""

from __future__ import annotations

from typing import Any

from forgex.agents.prompts.reviewer import REVIEWER_PROMPT
from forgex.agents.roles.base import AgentRole
from forgex.core.exceptions import AgentError


class ReviewerRole(AgentRole):
    """Reviews implementation quality, safety, and correctness."""

    name = "reviewer"
    template = REVIEWER_PROMPT

    def validate(self, data: dict[str, Any]) -> None:
        super().validate(data)
        required = ("approved", "summary", "findings")
        missing = [key for key in required if key not in data]
        if missing:
            raise AgentError(
                "Reviewer output missing required fields.",
                details={"missing": missing},
            )
        if not isinstance(data.get("approved"), bool):
            raise AgentError("Reviewer 'approved' must be a boolean.")
        if not isinstance(data.get("findings"), list):
            raise AgentError("Reviewer 'findings' must be a list.")


__all__ = ["ReviewerRole"]
