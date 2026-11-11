"""Configuration file management for FORGEX."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from forgex.config.settings import (
    ForgexSettings,
    get_settings,
)

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """Manage persistent FORGEX configuration files."""

    CONFIG_FILENAME = "config.json"

    def __init__(
        self,
        config_dir: str | Path,
        *,
        settings: ForgexSettings | None = None,
    ) -> None:
        self.config_dir = Path(config_dir).expanduser().resolve()
        self.config_file = self.config_dir / self.CONFIG_FILENAME
        self._settings = settings

    @property
    def settings(self) -> ForgexSettings:
        """Return the active settings instance."""

        if self._settings is None:
            self._settings = get_settings()

        return self._settings

    def ensure_config_directory(self) -> Path:
        """Create the configuration directory if necessary."""

        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"Cannot create configuration directory: {self.config_dir}") from exc

        return self.config_dir

    def exists(self) -> bool:
        """Check whether a persistent configuration file exists."""

        return self.config_file.is_file()

    def load(self) -> ForgexSettings:
        """Load settings from the persistent JSON configuration.

        Environment variables and explicit Pydantic settings sources
        retain their normal priority when constructing settings.
        """

        if not self.exists():
            logger.debug("Configuration file does not exist.")
            return self.settings

        try:
            with self.config_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                raise ValueError("Configuration root must be a JSON object.")

            self._settings = ForgexSettings.model_validate(data)

            logger.info(
                "Configuration loaded from %s",
                self.config_file,
            )

            return self._settings

        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise ValueError(f"Failed to load FORGEX configuration: {exc}") from exc

    def save(
        self,
        settings: ForgexSettings | None = None,
    ) -> Path:
        """Atomically save settings to the configuration file."""

        active_settings = settings or self.settings
        self.ensure_config_directory()

        payload = active_settings.model_dump(mode="json")

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.config_dir,
                prefix=".forgex-config-",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)

                json.dump(
                    payload,
                    file,
                    indent=4,
                    ensure_ascii=False,
                    sort_keys=True,
                )

                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(temporary_path, self.config_file)
            self._settings = active_settings

            logger.info(
                "Configuration saved to %s",
                self.config_file,
            )

            return self.config_file

        except (OSError, TypeError, ValueError) as exc:
            raise OSError(f"Failed to save FORGEX configuration: {exc}") from exc

        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove temporary configuration file: %s",
                        temporary_path,
                    )

    def update(
        self,
        updates: Mapping[str, Any],
    ) -> ForgexSettings:
        """Update configuration using nested dictionary values.

        Example:
            manager.update({
                "model": {
                    "provider": "ollama",
                    "model_name": "qwen2.5-coder:7b",
                }
            })
        """

        current_data = self.settings.model_dump(mode="python")

        merged_data = self._deep_merge(
            current_data,
            dict(updates),
        )

        try:
            updated_settings = ForgexSettings.model_validate(merged_data)
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration update: {exc}") from exc

        self.save(updated_settings)

        return updated_settings

    def reset(self) -> ForgexSettings:
        """Reset configuration to default and environment settings."""

        self._settings = ForgexSettings()
        self.save(self._settings)

        logger.info("FORGEX configuration reset to defaults.")

        return self._settings

    def delete(self) -> bool:
        """Delete the persistent configuration file."""

        if not self.exists():
            return False

        try:
            self.config_file.unlink()
        except OSError as exc:
            raise OSError(f"Failed to delete configuration file: {exc}") from exc

        logger.info("FORGEX configuration file deleted.")
        return True

    @staticmethod
    def _deep_merge(
        original: dict[str, Any],
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Recursively merge nested configuration dictionaries."""

        result = dict(original)

        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, Mapping):
                result[key] = ConfigurationManager._deep_merge(
                    result[key],
                    dict(value),
                )
            else:
                result[key] = value

        return result


__all__ = [
    "ConfigurationManager",
]
