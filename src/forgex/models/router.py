"""Hardware-aware model routing for FORGEX."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forgex.config.settings import ModelSettings
from forgex.models.errors import ModelRoutingError
from forgex.models.hardware import HardwareProfile, detect_hardware


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """Resolved provider/model selection."""

    provider: str
    model_name: str
    model_path: Path | None
    context_window: int
    max_output_tokens: int
    temperature: float
    top_p: float
    request_timeout_seconds: float
    reason: str
    hardware: HardwareProfile

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "model_path": str(self.model_path) if self.model_path else None,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "request_timeout_seconds": self.request_timeout_seconds,
            "reason": self.reason,
            "hardware": self.hardware.to_dict(),
        }


class ModelRouter:
    """Selects a local provider/model route based on config and hardware."""

    def __init__(self, hardware: HardwareProfile | None = None) -> None:
        self._hardware = hardware

    @property
    def hardware(self) -> HardwareProfile:
        if self._hardware is None:
            self._hardware = detect_hardware()
        return self._hardware

    def resolve(
        self,
        settings: ModelSettings,
        *,
        provider_override: str | None = None,
        model_override: str | None = None,
        model_path_override: str | Path | None = None,
    ) -> ModelRoute:
        provider = (provider_override or settings.provider or "auto").strip().lower()
        model_name = (model_override or settings.model_name or "").strip()
        model_path = model_path_override or settings.model_path
        if isinstance(model_path, str) and model_path.strip():
            model_path = Path(model_path).expanduser().resolve()
        elif isinstance(model_path, Path):
            model_path = model_path.expanduser().resolve()
        else:
            model_path = None

        if provider == "auto":
            provider = self._select_provider(settings, model_path=model_path)

        provider = self._normalize_provider(provider)
        self._validate_provider(provider)

        if not model_name and not model_path:
            raise ModelRoutingError("No model configured. Set a model name or local model path.")

        context_window = int(settings.context_window)
        if settings.context_window == 8192 and provider in {"llama_cpp", "transformers"}:
            context_window = min(context_window, self.hardware.recommended_context_window)

        route = ModelRoute(
            provider=provider,
            model_name=model_name or (model_path.name if model_path else "local-model"),
            model_path=model_path,
            context_window=context_window,
            max_output_tokens=int(settings.max_output_tokens),
            temperature=float(settings.temperature),
            top_p=float(settings.top_p),
            request_timeout_seconds=float(settings.request_timeout_seconds),
            reason=self._reason(provider, model_path),
            hardware=self.hardware,
        )
        return route

    def _select_provider(
        self,
        settings: ModelSettings,
        *,
        model_path: Path | None,
    ) -> str:
        if model_path:
            suffix = model_path.suffix.lower()
            if (suffix == ".gguf" or model_path.is_file()) and suffix == ".gguf":
                return "llama_cpp"
            if model_path.is_dir():
                return "transformers"
        if shutil.which("ollama"):
            return "ollama"
        if self._module_available("llama_cpp") and model_path:
            return "llama_cpp"
        if self._module_available("transformers"):
            return "transformers"
        if shutil.which("ollama"):
            return "ollama"
        raise ModelRoutingError(
            "No local model provider available. Install/start Ollama, "
            "or install llama-cpp-python/transformers with a local model."
        )

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        aliases = {
            "llamacpp": "llama_cpp",
            "llama-cpp": "llama_cpp",
            "llama.cpp": "llama_cpp",
            "hf": "transformers",
            "huggingface": "transformers",
            "local": "transformers",
            "vllm": "openai_compatible",
            "sglang": "openai_compatible",
            "openai": "openai_compatible",
            "openai-compatible": "openai_compatible",
            "openai_api": "openai_compatible",
            "lm_studio": "openai_compatible",
        }
        return aliases.get(provider, provider)

    @staticmethod
    def _validate_provider(provider: str) -> None:
        allowed = {"ollama", "llama_cpp", "transformers", "openai_compatible"}
        if provider not in allowed:
            raise ModelRoutingError(
                f"Unsupported local provider '{provider}'. "
                f"Supported providers: {', '.join(sorted(allowed))}."
            )

    @staticmethod
    def _reason(provider: str, model_path: Path | None) -> str:
        if model_path and provider == "llama_cpp":
            return "Selected llama.cpp for local GGUF/model path."
        if model_path and provider == "transformers":
            return "Selected Transformers for local model directory."
        if provider == "ollama":
            return "Selected Ollama for local managed model inference."
        if provider == "transformers":
            return "Selected Transformers local inference."
        if provider == "openai_compatible":
            return "Selected OpenAI-compatible API (vLLM, SGLang, LM Studio, or OpenAI)."
        return f"Selected provider '{provider}'."

    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            __import__(name)
            return True
        except Exception:
            return False


__all__ = ["ModelRoute", "ModelRouter"]
