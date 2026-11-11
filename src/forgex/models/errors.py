"""Model-layer exceptions for FORGEX."""

from __future__ import annotations

from forgex.core.exceptions import ConfigurationError, ForgexError, ModelError


class ModelProviderError(ModelError):
    """Raised when a local model provider fails."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        merged = dict(details or {})
        if provider:
            merged["provider"] = provider
        super().__init__(message, details=merged)
        self.provider = provider


class ModelConfigurationError(ConfigurationError):
    """Raised for invalid model configuration."""


class ModelNotFoundError(ModelProviderError):
    """Raised when a requested model is unavailable locally."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        merged = dict(details or {})
        if model:
            merged["model"] = model
        super().__init__(message, provider=provider, details=merged)
        self.model = model


class ModelInferenceError(ModelProviderError):
    """Raised when local inference fails."""


class ModelDownloadError(ForgexError):
    """Raised when model weight download fails."""

    def __init__(
        self,
        message: str,
        *,
        repo_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        merged = dict(details or {})
        if repo_id:
            merged["repo_id"] = repo_id
        super().__init__(message, code="MODEL_DOWNLOAD_ERROR", details=merged)
        self.repo_id = repo_id


class ModelRoutingError(ModelError):
    """Raised when no suitable model/provider route can be selected."""


__all__ = [
    "ModelProviderError",
    "ModelConfigurationError",
    "ModelNotFoundError",
    "ModelInferenceError",
    "ModelDownloadError",
    "ModelRoutingError",
]
