"""Plugin system for FORGEX.

Provides plugin interface, manifest, registry, loader, lifecycle,
and permission-aware execution.
"""

from forgex.plugins.base import Plugin, PluginContext, PluginResult
from forgex.plugins.loader import PluginLoader
from forgex.plugins.registry import PluginRegistry

__all__ = ["Plugin", "PluginContext", "PluginResult", "PluginRegistry", "PluginLoader"]
