"""Plugin loader for FORGEX.

Loads plugins from entry points, directories, or manifests.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from forgex.plugins.base import Plugin

logger = logging.getLogger(__name__)


class PluginLoader:
    """Loads FORGEX plugins from various sources."""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def load_from_entry_points(self, group: str = "forgex.plugins") -> int:
        """Load plugins from installed entry points."""
        count = 0
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group=group)
            for ep in eps:
                try:
                    plugin_class = ep.load()
                    self.registry.register(plugin_class)
                    count += 1
                except Exception:
                    logger.exception("Failed to load plugin from entry point %s.", ep.name)
        except Exception:
            logger.debug("Entry point loading not available.")
        return count

    def load_from_directory(self, directory: str | Path) -> int:
        """Load plugins from a directory of Python modules."""
        count = 0
        plugin_dir = Path(directory).expanduser().resolve()
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            return count
        for p in plugin_dir.glob("*.py"):
            if p.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"forgex_plugin_{p.stem}", p
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, Plugin)
                            and attr is not Plugin
                        ):
                            self.registry.register(attr)
                            count += 1
            except Exception:
                logger.exception("Failed to load plugin from %s.", p)
        return count

    def load_from_module(self, module_path: str) -> int:
        """Load plugins from a Python module path."""
        count = 0
        try:
            module = importlib.import_module(module_path)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, Plugin) and attr is not Plugin:
                    self.registry.register(attr)
                    count += 1
        except Exception:
            logger.exception("Failed to load plugins from module %s.", module_path)
        return count


__all__ = ["PluginLoader"]
