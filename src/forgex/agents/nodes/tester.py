"""Tester workflow node."""

from __future__ import annotations

from typing import Any

from forgex.agents.nodes.base import AgentNode
from forgex.agents.roles.tester import TesterRole
from forgex.core.orchestrator import ForgexState


class TesterNode(AgentNode):
    """Evaluates verification status and stores test outcomes."""

    node_name = "tester"
    state_key = "test_report"

    def __init__(self, role: TesterRole | None = None, model: Any = None) -> None:
        super().__init__(role or TesterRole(model=model))

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        update = await super().__call__(state)
        report = update.get("test_report") or {}
        update["output"] = report
        failures = report.get("failures") or []
        if failures and not report.get("verified", False):
            update["error"] = "; ".join(str(item) for item in failures)
        elif report.get("verified", False):
            update["error"] = ""
        return update


__all__ = ["TesterNode"]
