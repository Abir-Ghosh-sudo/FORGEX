"""llama.cpp local inference provider for FORGEX."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from forgex.models.base import (
    BaseModelProvider,
    GenerationResult,
    ModelCapabilities,
    ModelMessage,
    ModelProviderInfo,
)
from forgex.models.errors import (
    ModelConfigurationError,
    ModelInferenceError,
    ModelNotFoundError,
)

logger = logging.getLogger(__name__)


class LlamaCppProvider(BaseModelProvider):
    """Local GGUF inference via llama-cpp-python."""

    provider_name = "llama_cpp"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._llm: Any = None
        self._n_ctx = self.context_window
        self._n_threads = self.options.get("n_threads")
        self._n_gpu_layers = self.options.get("n_gpu_layers", -1)

    @property
    def info(self) -> ModelProviderInfo:
        return ModelProviderInfo(
            name="llama_cpp",
            display_name="llama.cpp",
            local=True,
            supports_download=False,
            description="Local GGUF model inference via llama-cpp-python.",
        )

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            streaming=False,
            tool_calling=False,
            json_mode=True,
            max_context_tokens=self.context_window,
            local_only=True,
        )

    def _resolve_model_path(self) -> Path:
        path = Path(self.model_path or self.model_name).expanduser().resolve()
        if not path.exists():
            raise ModelNotFoundError(
                f"llama.cpp model not found: {path}",
                provider=self.provider_name,
                model=str(path),
            )
        if path.is_dir():
            ggufs = sorted(path.glob("*.gguf"))
            if not ggufs:
                raise ModelNotFoundError(
                    f"No GGUF file found in directory: {path}",
                    provider=self.provider_name,
                    model=str(path),
                )
            path = ggufs[0]
        if path.suffix.lower() != ".gguf":
            raise ModelConfigurationError(f"llama.cpp provider requires a .gguf model file: {path}")
        return path

    def _load(self) -> Any:
        if self._llm is not None:
            return self._llm
        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as exc:
            raise ModelInferenceError(
                "llama-cpp-python is not installed.",
                provider=self.provider_name,
            ) from exc

        model_path = self._resolve_model_path()
        kwargs: dict[str, Any] = {
            "model_path": str(model_path),
            "n_ctx": int(self._n_ctx),
            "verbose": False,
        }
        if self._n_threads is not None:
            kwargs["n_threads"] = int(self._n_threads)
        if self._n_gpu_layers is not None:
            kwargs["n_gpu_layers"] = int(self._n_gpu_layers)

        try:
            self._llm = Llama(**kwargs)
            return self._llm
        except Exception as exc:
            raise ModelInferenceError(
                f"Failed to load GGUF model '{model_path}': {exc}",
                provider=self.provider_name,
            ) from exc

    def _generate_sync(
        self,
        messages: list[ModelMessage],
        **kwargs: Any,
    ) -> GenerationResult:
        llm = self._load()
        payload = [m.to_dict() for m in messages]
        max_tokens = int(kwargs.get("max_output_tokens", self.max_output_tokens))
        temperature = float(kwargs.get("temperature", self.temperature))
        top_p = float(kwargs.get("top_p", self.top_p))

        try:
            response = llm.create_chat_completion(
                messages=payload,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
        except Exception as exc:
            try:
                prompt = self._messages_to_prompt(messages)
                response = llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    echo=False,
                )
                text = ""
                choices = response.get("choices") or []
                if choices:
                    text = str(choices[0].get("text", ""))
                return GenerationResult(
                    text=text,
                    model=self.model_name,
                    provider=self.provider_name,
                    finish_reason=str(choices[0].get("finish_reason")) if choices else None,
                    raw=response,
                )
            except Exception:
                raise ModelInferenceError(
                    f"llama.cpp inference failed: {exc}",
                    provider=self.provider_name,
                ) from exc

        choices = response.get("choices") or []
        text = ""
        finish = None
        if choices:
            msg = choices[0].get("message") or {}
            text = str(msg.get("content", ""))
            finish = choices[0].get("finish_reason")
        usage = response.get("usage") or {}
        return GenerationResult(
            text=text,
            model=str(response.get("model", self.model_name)),
            provider=self.provider_name,
            finish_reason=str(finish) if finish else None,
            prompt_tokens=self._safe_int(usage.get("prompt_tokens")),
            completion_tokens=self._safe_int(usage.get("completion_tokens")),
            total_tokens=self._safe_int(usage.get("total_tokens")),
            raw=response,
        )

    @staticmethod
    def _messages_to_prompt(messages: list[ModelMessage]) -> str:
        parts = [f"{m.role.upper()}:\n{m.content}" for m in messages]
        parts.append("ASSISTANT:")
        return "\n\n".join(parts)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except Exception:
            return None

    def is_available(self) -> bool:
        try:
            import llama_cpp  # noqa: F401

            self._resolve_model_path()
            return True
        except Exception:
            return False

    def close(self) -> None:
        self._llm = None
        super().close()


__all__ = ["LlamaCppProvider"]
