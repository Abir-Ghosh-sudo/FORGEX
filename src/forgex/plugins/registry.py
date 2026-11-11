"""Plugin registry for FORGEX."""

from __future__ import annotations

import logging
from typing import Any

from forgex.plugins.base import Plugin, PluginContext, PluginResult

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for FORGEX plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, type[Plugin]] = {}
        self._instances: dict[str, Plugin] = {}

    def register(self, plugin_class: type[Plugin]) -> None:
        """Register a plugin class."""
        if not issubclass(plugin_class, Plugin):
            raise TypeError(f"{plugin_class} is not a Plugin subclass.")
        name = getattr(plugin_class, "name", None) or plugin_class.__name__
        self._plugins[name] = plugin_class
        logger.info("Plugin registered: %s", name)

    def unregister(self, name: str) -> bool:
        """Unregister a plugin by name."""
        if name in self._plugins:
            del self._plugins[name]
            self._instances.pop(name, None)
            return True
        return False

    def list_plugins(self) -> list[str]:
        """List registered plugin names."""
        return sorted(self._plugins.keys())

    def get(self, name: str) -> type[Plugin] | None:
        """Get a plugin class by name."""
        return self._plugins.get(name)

    def create_instance(self, name: str, context: PluginContext) -> Plugin:
        """Create and initialize a plugin instance."""
        plugin_class = self.get(name)
        if plugin_class is None:
            raise ValueError(f"Plugin not registered: {name}")
        if name not in self._instances:
            instance = plugin_class()
            result = await_instance_init(instance, context)
            if not result.success:
                raise RuntimeError(f"Plugin {name} initialization failed: {result.error}")
            self._instances[name] = instance
        return self._instances[name]

    async def execute(
        self,
        name: str,
        action: str,
        params: dict[str, Any],
        context: PluginContext,
    ) -> PluginResult:
        """Execute a plugin action by name."""
        plugin = self.create_instance(name, context)
        try:
            return await plugin.execute(action, params)
        except Exception as exc:
            logger.exception("Plugin %s execution failed.", name)
            return PluginResult(success=False, output="", error=str(exc))

    async def shutdown_all(self) -> None:
        """Shutdown all plugin instances."""
        for name, instance in list(self._instances.items()):
            try:
                await instance.shutdown()
            except Exception:
                logger.exception("Plugin %s shutdown error.", name)
        self._instances.clear()


async def await_instance_init(instance: Plugin, context: PluginContext) -> PluginResult:
    """Helper to await plugin initialization."""
    return await instance.initialize(context)


__all__ = ["PluginRegistry"]
