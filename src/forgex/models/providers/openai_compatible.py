"""OpenAI-compatible model provider for FORGEX (vLLM, SGLang, LM Studio, OpenAI)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from forgex.models.base import (
    BaseModelProvider,
    GenerationResult,
    ModelCapabilities,
)
from forgex.models.errors import ModelProviderError

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseModelProvider):
    """Provider connecting to standard OpenAI-compatible API servers."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8000/v1",
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "EMPTY"
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.request_timeout_seconds,
            )
        return self._client

    @property
    def async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.request_timeout_seconds,
            )
        return self._async_client

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            supports_streaming=True,
            supports_chat=True,
            supports_completion=True,
            supports_tool_calling=True,
            supports_system_prompt=True,
            multimodal=False,
            recommended_max_tokens=self.max_output_tokens,
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> GenerationResult:
        payload = self._build_payload(messages, **kwargs)
        try:
            response = self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data)
        except Exception as exc:
            logger.exception("OpenAI-compatible generation request failed.")
            raise ModelProviderError(
                f"OpenAI-compatible request failed: {exc}",
                provider="openai_compatible",
                model=self.model_name,
            ) from exc

    async def generate_async(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> GenerationResult:
        payload = self._build_payload(messages, **kwargs)
        try:
            response = await self.async_client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data)
        except Exception as exc:
            logger.exception("Async OpenAI-compatible generation request failed.")
            raise ModelProviderError(
                f"Async OpenAI-compatible request failed: {exc}",
                provider="openai_compatible",
                model=self.model_name,
            ) from exc

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "model": self.model_name or "default",
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "max_tokens": kwargs.get("max_output_tokens", self.max_output_tokens),
            "stream": False,
        }

    def _parse_response(self, data: dict[str, Any]) -> GenerationResult:
        choices = data.get("choices") or []
        content = ""
        finish_reason = "stop"
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            finish_reason = choices[0].get("finish_reason") or "stop"

        usage = data.get("usage") or {}
        return GenerationResult(
            text=content,
            finish_reason=finish_reason,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
            metadata={"raw": data},
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._async_client is not None:
            # Sync close of async client resources
            self._async_client = None


__all__ = ["OpenAICompatibleProvider"]

