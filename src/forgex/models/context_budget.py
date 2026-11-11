"""Context window budgeting for local model prompts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from forgex.models.base import ModelMessage


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Computed token budget for a request."""

    context_window: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    prompt_budget_tokens: int
    estimated_prompt_tokens: int
    fits: bool
    truncated: bool
    message_count: int


class ContextBudgeter:
    """Estimates prompt size and trims messages to fit model context."""

    def __init__(
        self,
        *,
        context_window: int,
        reserved_output_tokens: int = 2048,
        safety_margin_tokens: int = 256,
        chars_per_token: float = 4.0,
    ) -> None:
        self.context_window = max(256, int(context_window))
        self.reserved_output_tokens = max(1, int(reserved_output_tokens))
        self.safety_margin_tokens = max(0, int(safety_margin_tokens))
        self.chars_per_token = max(1.5, float(chars_per_token))

    @property
    def prompt_budget_tokens(self) -> int:
        budget = (
            self.context_window
            - self.reserved_output_tokens
            - self.safety_margin_tokens
        )
        return max(128, budget)

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(math.ceil(len(text) / self.chars_per_token)))

    def estimate_messages(
        self,
        messages: Sequence[ModelMessage | Mapping[str, object]],
    ) -> int:
        total = 0
        for msg in messages:
            if isinstance(msg, ModelMessage):
                content = msg.content
                role = msg.role
            else:
                content = str(msg.get("content", ""))
                role = str(msg.get("role", ""))
            total += self.estimate_tokens(content) + self.estimate_tokens(role) + 4
        return total

    def fit_messages(
        self,
        messages: Sequence[ModelMessage | Mapping[str, object]],
    ) -> tuple[list[ModelMessage], ContextBudget]:
        normalized: list[ModelMessage] = []
        for msg in messages:
            if isinstance(msg, ModelMessage):
                normalized.append(msg)
            else:
                normalized.append(ModelMessage.from_mapping(msg))  # type: ignore[arg-type]

        if not normalized:
            budget = ContextBudget(
                context_window=self.context_window,
                reserved_output_tokens=self.reserved_output_tokens,
                safety_margin_tokens=self.safety_margin_tokens,
                prompt_budget_tokens=self.prompt_budget_tokens,
                estimated_prompt_tokens=0,
                fits=True,
                truncated=False,
                message_count=0,
            )
            return [], budget

        system: list[ModelMessage] = []
        rest: list[ModelMessage] = []
        for msg in normalized:
            if msg.role.lower() == "system":
                system.append(msg)
            else:
                rest.append(msg)

        truncated = False
        kept_reversed: list[ModelMessage] = []
        used = self.estimate_messages(system)

        for msg in reversed(rest):
            cost = self.estimate_messages([msg])
            if used + cost <= self.prompt_budget_tokens or not kept_reversed:
                if used + cost > self.prompt_budget_tokens and not kept_reversed:
                    trimmed = self._trim_message(msg, self.prompt_budget_tokens - used)
                    kept_reversed.append(trimmed)
                    used += self.estimate_messages([trimmed])
                    truncated = True
                else:
                    kept_reversed.append(msg)
                    used += cost
            else:
                truncated = True

        fitted = system + list(reversed(kept_reversed))
        estimated = self.estimate_messages(fitted)
        fits = estimated <= self.prompt_budget_tokens
        budget = ContextBudget(
            context_window=self.context_window,
            reserved_output_tokens=self.reserved_output_tokens,
            safety_margin_tokens=self.safety_margin_tokens,
            prompt_budget_tokens=self.prompt_budget_tokens,
            estimated_prompt_tokens=estimated,
            fits=fits,
            truncated=truncated,
            message_count=len(fitted),
        )
        return fitted, budget

    def _trim_message(self, message: ModelMessage, remaining_tokens: int) -> ModelMessage:
        max_chars = max(64, int(remaining_tokens * self.chars_per_token))
        content = message.content
        if len(content) <= max_chars:
            return message
        head = content[: max_chars - 40]
        trimmed = head + "\n...[truncated for context budget]..."
        return ModelMessage(
            role=message.role,
            content=trimmed,
            name=message.name,
            metadata=dict(message.metadata),
        )


__all__ = ["ContextBudget", "ContextBudgeter"]
