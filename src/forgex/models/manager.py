"""High-level model manager for FORGEX."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from forgex.config import get_settings
from forgex.config.settings import ModelSettings
from forgex.models.base import BaseModelProvider, GenerationResult
from forgex.models.context_budget import ContextBudgeter
from forgex.models.downloader import DownloadResult, HuggingFaceDownloader
from forgex.models.errors import ModelConfigurationError, ModelProviderError
from forgex.models.router import ModelRoute, ModelRouter

logger = logging.getLogger(__name__)


class ModelManager:
    """Creates providers, manages downloads, and exposes a unified generate API."""

    def __init__(
        self,
        settings: ModelSettings | None = None,
        *,
        router: ModelRouter | None = None,
        downloader: HuggingFaceDownloader | None = None,
    ) -> None:
        self.settings = settings or get_settings().model
        self.router = router or ModelRouter()
        self.downloader = downloader or HuggingFaceDownloader(
            local_files_only=self.settings.local_files_only
        )
        self._provider: BaseModelProvider | None = None
        self._route: ModelRoute | None = None

    @property
    def route(self) -> ModelRoute | None:
        return self._route

    @property
    def provider(self) -> BaseModelProvider | None:
        return self._provider

    def resolve(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        model_path: str | Path | None = None,
    ) -> ModelRoute:
        route = self.router.resolve(
            self.settings,
            provider_override=provider,
            model_override=model,
            model_path_override=model_path,
        )
        self._route = route
        return route

    def get_provider(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        model_path: str | Path | None = None,
        force_new: bool = False,
    ) -> BaseModelProvider:
        route = self.resolve(
            provider=provider,
            model=model,
            model_path=model_path,
        )

        if (
            not force_new
            and self._provider is not None
            and self._route is not None
            and self._route.provider == route.provider
            and self._route.model_name == route.model_name
            and self._route.model_path == route.model_path
        ):
            return self._provider

        if self._provider is not None:
            try:
                self._provider.close()
            except Exception:
                logger.debug("Failed to close previous provider.", exc_info=True)

        self._provider = self._create_provider(route)
        self._route = route
        return self._provider

    def generate(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> GenerationResult | str:
        """Unified generation entrypoint compatible with agent roles."""
        provider = self.get_provider(
            provider=kwargs.pop("provider", None),
            model=kwargs.pop("model", None),
            model_path=kwargs.pop("model_path", None),
            force_new=bool(kwargs.pop("force_new_provider", False)),
        )

        budgeter = ContextBudgeter(
            context_window=provider.context_window,
            reserved_output_tokens=min(
                provider.max_output_tokens,
                kwargs.get("max_output_tokens", provider.max_output_tokens),
            ),
        )
        fitted, _budget = budgeter.fit_messages(provider.normalize_messages(messages))
        result = provider.generate([m.to_dict() for m in fitted], **kwargs)
        return result

    async def generate_async(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> GenerationResult:
        provider = self.get_provider(
            provider=kwargs.pop("provider", None),
            model=kwargs.pop("model", None),
            model_path=kwargs.pop("model_path", None),
            force_new=bool(kwargs.pop("force_new_provider", False)),
        )
        budgeter = ContextBudgeter(
            context_window=provider.context_window,
            reserved_output_tokens=min(
                provider.max_output_tokens,
                kwargs.get("max_output_tokens", provider.max_output_tokens),
            ),
        )
        fitted, _budget = budgeter.fit_messages(provider.normalize_messages(messages))
        return await provider.generate_async([m.to_dict() for m in fitted], **kwargs)

    def download(
        self,
        repo_id: str,
        *,
        revision: str | None = None,
        allow_patterns: list[str] | tuple[str, ...] | None = None,
        ignore_patterns: list[str] | tuple[str, ...] | None = None,
        filename: str | None = None,
        local_dir: str | Path | None = None,
        local_files_only: bool = False,
    ) -> DownloadResult:
        """Download model weights from Hugging Face Hub (no hosted inference).

        By default, explicit downloads allow fetching remote models even if
        inference settings default to offline local files only.
        """
        return self.downloader.download_model(
            repo_id,
            revision=revision,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
            filename=filename,
            local_dir=local_dir,
            local_files_only=local_files_only,
        )

    def list_ollama_models(self) -> list[str]:
        try:
            from forgex.models.providers.ollama import OllamaProvider

            return OllamaProvider.list_local_models(self.settings.ollama_base_url)
        except Exception as exc:
            raise ModelProviderError(
                f"Unable to list Ollama models: {exc}",
                provider="ollama",
            ) from exc

    def pull_ollama_model(self, model_name: str) -> tuple[bool, str]:
        try:
            from forgex.models.providers.ollama import OllamaProvider

            return OllamaProvider.pull_model(
                model_name,
                base_url=self.settings.ollama_base_url,
            )
        except Exception as exc:
            raise ModelProviderError(
                f"Unable to pull Ollama model: {exc}",
                provider="ollama",
            ) from exc

    def close(self) -> None:
        if self._provider is not None:
            try:
                self._provider.close()
            except Exception:
                logger.debug("Provider close failed.", exc_info=True)
            self._provider = None

    def _create_provider(self, route: ModelRoute) -> BaseModelProvider:
        common: dict[str, Any] = {
            "model_name": route.model_name,
            "model_path": str(route.model_path) if route.model_path else None,
            "context_window": route.context_window,
            "max_output_tokens": route.max_output_tokens,
            "temperature": route.temperature,
            "top_p": route.top_p,
            "request_timeout_seconds": route.request_timeout_seconds,
        }

        if route.provider == "ollama":
            from forgex.models.providers.ollama import OllamaProvider

            return OllamaProvider(
                base_url=self.settings.ollama_base_url,
                **common,
            )
        if route.provider == "llama_cpp":
            from forgex.models.providers.llama_cpp import LlamaCppProvider

            return LlamaCppProvider(**common)
        if route.provider == "transformers":
            from forgex.models.providers.transformers import TransformersProvider

            return TransformersProvider(
                trust_remote_code=self.settings.trust_remote_code,
                local_files_only=self.settings.local_files_only,
                **common,
            )

        if route.provider in {"openai_compatible", "vllm", "sglang", "openai"}:
            from forgex.models.providers.openai_compatible import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                base_url=self.settings.ollama_base_url
                if "11434" not in self.settings.ollama_base_url
                else "http://localhost:8000/v1",
                **common,
            )

        raise ModelConfigurationError(f"Unsupported provider: {route.provider}")

    async def aclose(self) -> None:
        self.close()


__all__ = ["ModelManager"]
