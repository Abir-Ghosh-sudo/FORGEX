
"""TOML configuration loader for FORGEX runtime."""

from __future__ import annotations

import logging
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from forgex.runtime.runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)


class RuntimeConfigError(RuntimeError):
    """Raised when runtime configuration cannot be loaded or saved."""


class RuntimeConfigLoader:
    """Load and persist validated FORGEX runtime configuration."""

    SECTION = "runtime"

    _ALLOWED_KEYS = {
        "default_timeout",
        "shutdown_timeout",
        "termination_grace_period",
        "max_concurrent_processes",
        "max_output_bytes",
        "output_chunk_size",
        "encoding",
        "inherit_environment",
        "shell_enabled",
        "shell_approval_required",
        "process_tree_termination",
        "capture_stdout",
        "capture_stderr",
        "allowed_environment_variables",
        "blocked_environment_variables",
        "workspace",
        "platform",
        "metadata",
    }

    def __init__(
        self,
        config_path: Path | str | None = None,
    ) -> None:
        self.config_path = (
            Path(config_path).expanduser().resolve()
            if config_path is not None
            else None
        )

    def load(self, *, strict: bool = True) -> RuntimeConfig:
        """Load runtime configuration from TOML."""

        if self.config_path is None:
            return RuntimeConfig()

        if not self.config_path.exists():
            return RuntimeConfig()

        if not self.config_path.is_file():
            raise RuntimeConfigError(
                f"Configuration path is not a file: {self.config_path}"
            )

        try:
            with self.config_path.open("rb") as file:
                document = tomllib.load(file)

            section = document.get(self.SECTION, {})

            if not isinstance(section, dict):
                raise RuntimeConfigError(
                    "The [runtime] section must be a TOML table."
                )

            unknown = set(section) - self._ALLOWED_KEYS

            if strict and unknown:
                raise RuntimeConfigError(
                    f"Unknown runtime settings: {', '.join(sorted(unknown))}"
                )

            values = {
                key: value
                for key, value in section.items()
                if key in self._ALLOWED_KEYS
            }

            if "workspace" in values and values["workspace"] is not None:
                workspace = Path(values["workspace"]).expanduser()

                if not workspace.is_absolute():
                    workspace = self.config_path.parent / workspace

                values["workspace"] = workspace.resolve()

            return RuntimeConfig(**values)

        except RuntimeConfigError:
            raise

        except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeConfigError(
                f"Failed to load runtime configuration: {exc}"
            ) from exc

    def save(self, config: RuntimeConfig) -> Path:
        """Atomically save runtime configuration as TOML."""

        if self.config_path is None:
            raise RuntimeConfigError(
                "A configuration path is required for saving."
            )

        if not isinstance(config, RuntimeConfig):
            raise TypeError("config must be a RuntimeConfig instance.")

        path = self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)

        document = {
            self.SECTION: self._serialize(config)
        }

        content = self._to_toml(document)

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                file.write(content)
                file.flush()
                os.fsync(file.fileno())

            os.replace(temporary_path, path)

            return path

        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

            raise RuntimeConfigError(
                f"Failed to save runtime configuration: {exc}"
            ) from exc

    @staticmethod
    def _serialize(config: RuntimeConfig) -> dict[str, Any]:
        """Convert RuntimeConfig into TOML-compatible values."""

        values = {
            "default_timeout": config.default_timeout,
            "shutdown_timeout": config.shutdown_timeout,
            "termination_grace_period": config.termination_grace_period,
            "max_concurrent_processes": config.max_concurrent_processes,
            "max_output_bytes": config.max_output_bytes,
            "output_chunk_size": config.output_chunk_size,
            "encoding": config.encoding,
            "inherit_environment": config.inherit_environment,
            "shell_enabled": config.shell_enabled,
            "shell_approval_required": config.shell_approval_required,
            "process_tree_termination": config.process_tree_termination,
            "capture_stdout": config.capture_stdout,
            "capture_stderr": config.capture_stderr,
            "allowed_environment_variables": list(
                config.allowed_environment_variables
            ),
            "blocked_environment_variables": list(
                config.blocked_environment_variables
            ),
            "platform": config.platform,
            "metadata": config.metadata,
        }

        if config.workspace is not None:
            values["workspace"] = str(config.workspace)

        return values

    @staticmethod
    def _to_toml(document: dict[str, Any]) -> str:
        """Serialize supported values into TOML without dependencies."""

        lines = ["[runtime]"]

        for key, value in document["runtime"].items():
            lines.append(
                f"{key} = {RuntimeConfigLoader._format_value(value)}"
            )

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_value(value: Any) -> str:
        """Format a Python value as a TOML literal."""

        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, int):
            return str(value)

        if isinstance(value, float):
            return repr(value)

        if isinstance(value, str):
            escaped = (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'

        if isinstance(value, list):
            return "[" + ", ".join(
                RuntimeConfigLoader._format_value(item)
                for item in value
            ) + "]"

        if isinstance(value, dict):
            return "{ " + ", ".join(
                f"{RuntimeConfigLoader._format_value(str(key))} = "
                f"{RuntimeConfigLoader._format_value(item)}"
                for key, item in value.items()
            ) + " }"

        raise TypeError(
            f"Unsupported TOML value type: {type(value).__name__}"
        )


__all__ = ["RuntimeConfigLoader", "RuntimeConfigError"]
