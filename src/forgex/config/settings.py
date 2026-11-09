"""Validated application settings for FORGEX.

Configuration can be supplied through environment variables,
nested environment variables, and an optional .env file.

Example:
    FORGEX_DEBUG=true
    FORGEX_MODEL__PROVIDER=ollama
    FORGEX_MODEL__MODEL_NAME=qwen2.5-coder:7b
    FORGEX_RUNTIME__MAX_CONCURRENCY=1
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from platformdirs import user_cache_dir, user_data_dir
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    """General application configuration."""

    name: str = "FORGEX"
    version: str = "1.0.0"
    environment: Literal["development", "testing", "production"] = (
        "development"
    )
    debug: bool = False
    workspace: Path | None = None

    @field_validator("workspace")
    @classmethod
    def normalize_workspace(
        cls,
        value: Path | None,
    ) -> Path | None:
        if value is None:
            return None
        return value.expanduser().resolve()


class ModelSettings(BaseSettings):
    """Local language-model configuration.

    Hugging Face Hub is intended for downloading model files only.
    Model inference must run locally.
    """

    provider: Literal[
        "auto",
        "ollama",
        "llama_cpp",
        "transformers",
    ] = "auto"

    model_name: str = "qwen2.5-coder:7b"
    model_path: Path | None = None

    ollama_base_url: str = "http://127.0.0.1:11434"

    context_window: int = Field(default=8192, ge=512, le=131072)
    max_output_tokens: int = Field(default=2048, ge=128, le=32768)

    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)

    request_timeout_seconds: float = Field(
        default=300.0,
        gt=0.0,
        le=3600.0,
    )

    trust_remote_code: bool = False
    local_files_only: bool = True

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model_name cannot be empty.")
        return value

    @field_validator("model_path")
    @classmethod
    def normalize_model_path(
        cls,
        value: Path | None,
    ) -> Path | None:
        if value is None:
            return None
        return value.expanduser().resolve()


class RuntimeSettings(BaseSettings):
    """Execution and resource-management configuration."""

    max_concurrency: int = Field(default=1, ge=1, le=32)

    command_timeout_seconds: float = Field(
        default=120.0,
        gt=0.0,
        le=3600.0,
    )

    shutdown_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
    )

    max_command_output_chars: int = Field(
        default=50000,
        ge=1000,
        le=1000000,
    )

    max_context_files: int = Field(default=100, ge=1, le=10000)

    sequential_agents: bool = True


class SecuritySettings(BaseSettings):
    """Security and permission configuration."""

    require_command_approval: bool = True
    require_file_write_approval: bool = False

    allow_destructive_commands: bool = False
    allow_network_access: bool = False

    restrict_workspace_access: bool = True

    allowed_workspace_roots: list[Path] = Field(
        default_factory=list
    )

    @field_validator("allowed_workspace_roots")
    @classmethod
    def normalize_allowed_roots(
        cls,
        values: list[Path],
    ) -> list[Path]:
        return [
            path.expanduser().resolve()
            for path in values
        ]


class StorageSettings(BaseSettings):
    """Persistent storage configuration."""

    data_dir: Path = Field(
        default_factory=lambda: Path(
            user_data_dir("FORGEX", "FORGEX")
        )
    )

    database_name: str = "forgex.db"

    enable_backups: bool = True

    backup_retention_count: int = Field(
        default=10,
        ge=1,
        le=1000,
    )

    @field_validator("data_dir")
    @classmethod
    def normalize_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def database_path(self) -> Path:
        """Return the absolute SQLite database path."""

        return self.data_dir / self.database_name


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"

    console_enabled: bool = True
    file_enabled: bool = True

    log_dir: Path = Field(
        default_factory=lambda: Path(
            user_cache_dir("FORGEX", "FORGEX")
        ) / "logs"
    )

    max_file_size_mb: int = Field(default=10, ge=1, le=500)
    backup_count: int = Field(default=5, ge=0, le=100)

    @field_validator("log_dir")
    @classmethod
    def normalize_log_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class MCPSettings(BaseSettings):
    """Model Context Protocol configuration."""

    enabled: bool = False

    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=600.0,
    )

    max_connections: int = Field(default=5, ge=1, le=100)


class TelemetrySettings(BaseSettings):
    """Optional anonymous telemetry configuration."""

    enabled: bool = False
    collect_errors: bool = False
    collect_performance: bool = False


class ForgexSettings(BaseSettings):
    """Root configuration model for the FORGEX application."""

    model_config = SettingsConfigDict(
        env_prefix="FORGEX_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
    )

    app: ApplicationSettings = Field(
        default_factory=ApplicationSettings
    )

    model: ModelSettings = Field(
        default_factory=ModelSettings
    )

    runtime: RuntimeSettings = Field(
        default_factory=RuntimeSettings
    )

    security: SecuritySettings = Field(
        default_factory=SecuritySettings
    )

    storage: StorageSettings = Field(
        default_factory=StorageSettings
    )

    logging: LoggingSettings = Field(
        default_factory=LoggingSettings
    )

    mcp: MCPSettings = Field(
        default_factory=MCPSettings
    )

    telemetry: TelemetrySettings = Field(
        default_factory=TelemetrySettings
    )


@lru_cache(maxsize=1)
def get_settings() -> ForgexSettings:
    """Return the cached application settings instance."""

    return ForgexSettings()


def load_settings(**overrides: object) -> ForgexSettings:
    """Create a fresh settings instance with explicit overrides."""

    return ForgexSettings(**overrides)


def clear_settings_cache() -> None:
    """Clear the cached settings instance.

    Useful after configuration changes and in isolated tests.
    """

    get_settings.cache_clear()


__all__ = [
    "ApplicationSettings",
    "ModelSettings",
    "RuntimeSettings",
    "SecuritySettings",
    "StorageSettings",
    "LoggingSettings",
    "MCPSettings",
    "TelemetrySettings",
    "ForgexSettings",
    "get_settings",
    "load_settings",
    "clear_settings_cache",
]