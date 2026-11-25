"""LangChain Runnable integration for FORGEX model providers.

LangChain remains an optional integration: importing FORGEX does not require
langchain-core to be installed.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from forgex.models.base import BaseModelProvider, GenerationResult, ModelMessage

try:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
    from langchain_core.prompt_values import ChatPromptValue, StringPromptValue
    from langchain_core.runnables import Runnable
except ImportError:  # pragma: no cover - exercised in minimal installations
    AIMessage = BaseMessage = HumanMessage = SystemMessage = None  # type: ignore[assignment,misc]
    ChatPromptValue = StringPromptValue = None  # type: ignore[assignment,misc]
    Runnable = object  # type: ignore[assignment,misc]


def build_langchain_messages(
    messages: Sequence[ModelMessage | Mapping[str, Any] | Any],
) -> list[Any]:
    """Convert FORGEX messages to LangChain messages or provider mappings."""
    converted: list[Any] = []
    for item in messages:
        if isinstance(item, ModelMessage):
            msg = item
        elif isinstance(item, Mapping):
            msg = ModelMessage.from_mapping(item)
        elif BaseMessage is not None and isinstance(item, BaseMessage):
            role = getattr(item, "type", "user")
            role = {"human": "user", "ai": "assistant"}.get(role, role)
            content = item.content
            if not isinstance(content, str):
                content = str(content)
            msg = ModelMessage(role=role, content=content)
        else:
            raise TypeError(f"Unsupported chat message type: {type(item).__name__}")

        if AIMessage is None:
            converted.append(msg.to_dict())
        else:
            role = msg.role.lower()
            if role == "system":
                message_class = SystemMessage
            elif role in {"assistant", "ai"}:
                message_class = AIMessage
            else:
                message_class = HumanMessage
            converted.append(message_class(content=msg.content))
    return converted


def _provider_messages(value: Any) -> list[ModelMessage | Mapping[str, Any]]:
    if isinstance(value, str):
        return [ModelMessage(role="user", content=value)]
    if ChatPromptValue is not None and isinstance(value, ChatPromptValue):
        value = value.to_messages()
    elif StringPromptValue is not None and isinstance(value, StringPromptValue):
        value = value.text
    if isinstance(value, str):
        return [ModelMessage(role="user", content=value)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if not value:
            raise ValueError("At least one message is required.")
        messages: list[ModelMessage | Mapping[str, Any]] = []
        for item in value:
            if isinstance(item, (ModelMessage, Mapping)):
                messages.append(item)
                continue
            role = getattr(item, "type", "user")
            role = {"human": "user", "ai": "assistant"}.get(role, role)
            messages.append({"role": role, "content": getattr(item, "content", str(item))})
        return messages
    raise TypeError("Runnable input must be text, a message sequence, or a ChatPromptValue.")


class LangChainChatAdapter(Runnable):
    """Expose a FORGEX provider as a LangChain Runnable chat model."""

    def __init__(self, provider: BaseModelProvider) -> None:
        self.provider = provider

    def invoke(
        self,
        input: Any,
        config: Any = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        del config
        if stop:
            kwargs["stop"] = stop
        result = self.provider.generate(_provider_messages(input), **kwargs)
        text = result.text if isinstance(result, GenerationResult) else str(result)
        if AIMessage is None:
            return result
        metadata = result.to_dict() if isinstance(result, GenerationResult) else {}
        return AIMessage(content=text, response_metadata=metadata)

    async def ainvoke(
        self,
        input: Any,
        config: Any = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        del config
        if stop:
            kwargs["stop"] = stop
        result = await self.provider.generate_async(_provider_messages(input), **kwargs)
        if AIMessage is None:
            return result
        return AIMessage(content=result.text, response_metadata=result.to_dict())


__all__ = ["LangChainChatAdapter", "build_langchain_messages"]
