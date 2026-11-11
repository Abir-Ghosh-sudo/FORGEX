"""Base LangGraph node wrapper for FORGEX agent roles."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from forgex.agents.roles.base import AgentRole
from forgex.core.orchestrator import ForgexState

logger = logging.getLogger(__name__)


class AgentNode:
    """Executes an agent role and merges its result into workflow state."""

    node_name: str = "agent"
    state_key: str = "output"

    def __init__(self, role: AgentRole) -> None:
        self.role = role

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        variables = self.build_variables(state)
        result = await self.role.run(variables)

        existing_messages = list(state.get("messages") or [])
        new_messages = list(result.messages)
        merged_messages = existing_messages + new_messages

        update: dict[str, Any] = {
            "current_agent": self.node_name,
            "messages": merged_messages,
            self.state_key: result.data,
        }

        metadata = dict(state.get("metadata") or {})
        agent_trace = dict(metadata.get("agent_trace") or {})
        agent_trace[self.node_name] = {
            "summary": result.data.get("summary", ""),
            "data": result.data,
        }
        metadata["agent_trace"] = agent_trace
        update["metadata"] = metadata
        return update

    def build_variables(self, state: ForgexState) -> dict[str, Any]:
        metadata = state.get("metadata") or {}
        return {
            "task": state.get("prompt", ""),
            "workspace": state.get("workspace", ""),
            "context": self._format_context(state, metadata),
            "plan": self._format_value(state.get("plan")),
            "implementation": self._format_value(
                state.get("implementation") or state.get("coder_output")
            ),
            "review": self._format_value(
                state.get("review") or state.get("reviewer_output")
            ),
        }

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(value)

    def _format_context(
        self,
        state: ForgexState,
        metadata: Mapping[str, Any],
    ) -> str:
        context: dict[str, Any] = {
            "task_id": state.get("task_id"),
            "current_agent": state.get("current_agent"),
            "error": state.get("error"),
            "output": state.get("output"),
        }
        extra = metadata.get("context")
        if extra is not None:
            context["metadata_context"] = extra
        for key in ("repository", "files", "tool_results", "test_results"):
            if key in metadata:
                context[key] = metadata[key]
        return self._format_value(context)


__all__ = ["AgentNode"]
