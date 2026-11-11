"""LangChain integration helpers for FORGEX model providers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from forgex.models.base import BaseModelProvider, GenerationResult, ModelMessage


def build_langchain_messages(
    messages: Sequence[ModelMessage | Mapping[str, Any]],
) -> list[Any]:
    """Convert normalized messages to LangChain message objects when available."""
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except Exception:
        return [m.to_dict() if isinstance(m, ModelMessage) else dict(m) for m in messages]

    converted: list[Any] = []
    for item in messages:
        msg = item if isinstance(item, ModelMessage) else ModelMessage.from_mapping(item)
        role = msg.role.lower()
        if role == "system":
            converted.append(SystemMessage(content=msg.content))
        elif role in {"assistant", "ai"}:
            converted.append(AIMessage(content=msg.content))
        else:
            converted.append(HumanMessage(content=msg.content))
    return converted


class LangChainChatAdapter:
    """Wraps a FORGEX provider as a simple LangChain-like runnable."""

    def __init__(self, provider: BaseModelProvider) -> None:
        self.provider = provider

    def invoke(
        self,
        messages: Sequence[ModelMessage | Mapping[str, Any]],
        **kwargs: Any,
    ) -> GenerationResult | str:
        return self.provider.generate(messages, **kwargs)

    async def ainvoke(
        self,
        messages: Sequence[ModelMessage | Mapping[str, Any]],
        **kwargs: Any,
    ) -> GenerationResult:
        return await self.provider.generate_async(messages, **kwargs)

    def __call__(
        self,
        messages: Sequence[ModelMessage | Mapping[str, Any]],
        **kwargs: Any,
    ) -> GenerationResult | str:
        return self.invoke(messages, **kwargs)


__all__ = ["LangChainChatAdapter", "build_langchain_messages"]
