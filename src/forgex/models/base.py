"""Base types and interfaces for FORGEX model providers."""

from __future__ import annotations

import abc
import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from forgex.models.errors import ModelConfigurationError, ModelInferenceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """Normalized chat message passed to providers."""

    role: str
    content: str
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ModelMessage":
        role = str(value.get("role", "user")).strip() or "user"
        content = value.get("content", "")
        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)
        name = value.get("name")
        meta = value.get("metadata")
        return cls(
            role=role,
            content=content,
            name=str(name) if name is not None else None,
            metadata=dict(meta) if isinstance(meta, Mapping) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            data["name"] = self.name
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Declared capabilities of a model/provider route."""

    streaming: bool = False
    tool_calling: bool = False
    json_mode: bool = False
    vision: bool = False
    embeddings: bool = False
    max_context_tokens: int = 8192
    local_only: bool = True


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Normalized generation result."""

    text: str
    model: str
    provider: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.text

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """A single streamed generation chunk."""

    text: str
    done: bool = False
    raw: Any = None


@dataclass(frozen=True, slots=True)
class ModelProviderInfo:
    """Static provider metadata."""

    name: str
    display_name: str
    local: bool = True
    supports_download: bool = False
    description: str = ""


class BaseModelProvider(abc.ABC):
    """Abstract local model provider."""

    provider_name: str = "base"

    def __init__(
        self,
        *,
        model_name: str,
        model_path: str | None = None,
        context_window: int = 8192,
        max_output_tokens: int = 2048,
        temperature: float = 0.2,
        top_p: float = 0.95,
        request_timeout_seconds: float = 300.0,
        **options: Any,
    ) -> None:
        self.model_name = (model_name or "").strip()
        self.model_path = model_path
        self.context_window = int(context_window)
        self.max_output_tokens = int(max_output_tokens)
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.options = dict(options)
        self._closed = False
        self._validate_base_config()

    def _validate_base_config(self) -> None:
        if not self.model_name and not self.model_path:
            raise ModelConfigurationError(
                "Either model_name or model_path must be configured."
            )
        if self.context_window < 128:
            raise ModelConfigurationError("context_window must be >= 128.")
        if self.max_output_tokens < 1:
            raise ModelConfigurationError("max_output_tokens must be >= 1.")
        if not 0.0 <= self.temperature <= 2.0:
            raise ModelConfigurationError("temperature must be between 0 and 2.")
        if not 0.0 < self.top_p <= 1.0:
            raise ModelConfigurationError("top_p must be within (0, 1].")

    @property
    @abc.abstractmethod
    def info(self) -> ModelProviderInfo:
        """Return provider metadata."""

    @property
    @abc.abstractmethod
    def capabilities(self) -> ModelCapabilities:
        """Return model/provider capabilities."""

    @abc.abstractmethod
    def _generate_sync(
        self,
        messages: list[ModelMessage],
        **kwargs: Any,
    ) -> GenerationResult:
        """Synchronous generation implementation."""

    async def generate_async(
        self,
        messages: Sequence[Mapping[str, Any] | ModelMessage],
        **kwargs: Any,
    ) -> GenerationResult:
        """Generate a response asynchronously."""
        normalized = self.normalize_messages(messages)
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None,
                lambda: self._generate_sync(normalized, **kwargs),
            )
        except Exception as exc:
            if isinstance(exc, ModelInferenceError):
                raise
            raise ModelInferenceError(
                f"{self.provider_name} generation failed: {exc}",
                provider=self.provider_name,
            ) from exc

    def generate(
        self,
        messages: Sequence[Mapping[str, Any] | ModelMessage],
        **kwargs: Any,
    ) -> GenerationResult | Any:
        """Synchronous generation API used by agent roles and callers."""
        normalized = self.normalize_messages(messages)
        try:
            return self._generate_sync(normalized, **kwargs)
        except Exception as exc:
            if isinstance(exc, ModelInferenceError):
                raise
            raise ModelInferenceError(
                f"{self.provider_name} generation failed: {exc}",
                provider=self.provider_name,
            ) from exc

    def stream(
        self,
        messages: Sequence[Mapping[str, Any] | ModelMessage],
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Optional streaming interface; defaults to single chunk."""
        result = self.generate(messages, **kwargs)
        text = result.text if isinstance(result, GenerationResult) else str(result)
        yield StreamChunk(text=text, done=True, raw=result)

    async def aclose(self) -> None:
        """Release provider resources."""
        self.close()

    def close(self) -> None:
        """Release provider resources."""
        self._closed = True

    @staticmethod
    def normalize_messages(
        messages: Sequence[Mapping[str, Any] | ModelMessage],
    ) -> list[ModelMessage]:
        normalized: list[ModelMessage] = []
        for item in messages:
            if isinstance(item, ModelMessage):
                normalized.append(item)
            elif isinstance(item, Mapping):
                normalized.append(ModelMessage.from_mapping(item))
            else:
                raise ModelConfigurationError(
                    "Each message must be a mapping or ModelMessage."
                )
        if not normalized:
            raise ModelConfigurationError("At least one message is required.")
        return normalized

    @staticmethod
    def to_text(response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, GenerationResult):
            return response.text
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text
        if isinstance(response, Mapping):
            for key in ("text", "content", "output"):
                val = response.get(key)
                if isinstance(val, str):
                    return val
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0]
                if isinstance(msg, Mapping):
                    m = msg.get("message")
                    if isinstance(m, Mapping) and isinstance(m.get("content"), str):
                        return str(m["content"])
                    if isinstance(msg.get("text"), str):
                        return str(msg["text"])
        return str(response)

    async def health_check(self) -> bool:
        """Best-effort provider availability check."""
        try:
            check = getattr(self, "is_available", None)
            if callable(check):
                value = check()
                if inspect.isawaitable(value):
                    value = await value
                return bool(value)
            return True
        except Exception:
            return False


__all__ = [
    "BaseModelProvider",
    "GenerationResult",
    "ModelCapabilities",
    "ModelMessage",
    "ModelProviderInfo",
    "StreamChunk",
]
