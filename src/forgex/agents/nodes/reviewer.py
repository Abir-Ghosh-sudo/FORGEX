"""Reviewer workflow node."""

from __future__ import annotations

from typing import Any

from forgex.agents.nodes.base import AgentNode
from forgex.agents.roles.reviewer import ReviewerRole
from forgex.core.orchestrator import ForgexState


class ReviewerNode(AgentNode):
    """Reviews implementation and records approval/findings."""

    node_name = "reviewer"
    state_key = "review"

    def __init__(
        self,
        role: ReviewerRole | None = None,
        model: Any = None,
    ) -> None:
        super().__init__(role or ReviewerRole(model=model))

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        update = await super().__call__(state)
        review = update.get("review") or {}
        update["output"] = review
        if not review.get("approved", False):
            required = review.get("required_fixes") or []
            if required:
                update["error"] = "; ".join(str(item) for item in required)
        else:
            update["error"] = ""
        return update


__all__ = ["ReviewerNode"]
