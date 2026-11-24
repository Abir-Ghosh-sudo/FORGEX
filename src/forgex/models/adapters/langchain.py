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
    """Convert FORGEX mappings/messages or LangChain messages to provider mappings."""
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
            cls = SystemMessage if role == "system" else AIMessage if role in {"assistant", "ai"} else HumanMessage
            converted.append(cls(content=msg.content))
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
        return [
            item if isinstance(item, (ModelMessage, Mapping)) else
            {"role": {"human": "user", "ai": "assistant"}.get(getattr(item, "type", "user"), getattr(item, "type", "user")),
             "content": getattr(item, "content", str(item))}
            for item in value
        ]
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
