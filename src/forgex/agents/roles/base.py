"""Base role abstractions for FORGEX agents."""

from __future__ import annotations

import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from forgex.agents.prompts.base import PromptTemplate, render_prompt_messages
from forgex.core.exceptions import AgentError

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


@runtime_checkable
class AgentModelProtocol(Protocol):
    """Minimal async/sync model interface expected by agent roles."""

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        ...


@dataclass(slots=True)
class AgentRoleResult:
    """Normalized result produced by an agent role."""

    agent: str
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, str]] = field(default_factory=list)
    raw: Any = None

    def to_state_update(self) -> dict[str, Any]:
        return {
            "current_agent": self.agent,
            "output": self.data or self.content,
            "messages": self.messages,
        }


class AgentRole:
    """Base class for prompt-driven FORGEX agent roles."""

    name: str = "agent"
    template: PromptTemplate

    def __init__(self, model: AgentModelProtocol | None = None) -> None:
        self.model = model

    def build_messages(
        self,
        variables: Mapping[str, Any],
    ) -> list[dict[str, str]]:
        return render_prompt_messages(self.template, variables)

    async def run(self, variables: Mapping[str, Any]) -> AgentRoleResult:
        messages = self.build_messages(variables)
        if self.model is None:
            raise AgentError(
                f"Agent '{self.name}' requires a configured model.",
                details={"agent": self.name},
            )

        try:
            response = self.model.generate(messages, agent=self.name)
            if inspect.isawaitable(response):
                response = await response
        except Exception as exc:
            raise AgentError(
                f"Agent '{self.name}' failed during model generation: {exc}",
                details={"agent": self.name},
            ) from exc

        content = self._extract_content(response)
        data = self.parse_json(content)
        self.validate(data)
        trace = list(messages) + [{"role": "assistant", "content": content}]
        return AgentRoleResult(
            agent=self.name,
            content=content,
            data=data,
            messages=trace,
            raw=response,
        )

    def validate(self, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise AgentError(
                f"Agent '{self.name}' must return a JSON object.",
                details={"agent": self.name},
            )

    @staticmethod
    def parse_json(content: str) -> dict[str, Any]:
        text = (content or "").strip()
        if not text:
            raise AgentError("Agent returned empty content.")

        candidates = [text]
        match = _JSON_BLOCK_RE.search(text)
        if match:
            candidates.insert(0, match.group(1).strip())

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
                return {"value": parsed}
            except Exception as exc:
                last_error = exc

        raise AgentError(
            "Agent response is not valid JSON.",
            details={"error": str(last_error) if last_error else "unknown"},
        )

    @staticmethod
    def _extract_content(response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, Mapping):
            for key in ("content", "text", "output", "message"):
                value = response.get(key)
                if isinstance(value, str):
                    return value
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0]
                if isinstance(msg, Mapping):
                    message = msg.get("message")
                    if isinstance(message, Mapping):
                        content = message.get("content")
                        if isinstance(content, str):
                            return content
                    content = msg.get("text") or msg.get("content")
                    if isinstance(content, str):
                        return content
            return json.dumps(response, ensure_ascii=False, default=str)

        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text
        return str(response)


__all__ = ["AgentModelProtocol", "AgentRole", "AgentRoleResult"]
