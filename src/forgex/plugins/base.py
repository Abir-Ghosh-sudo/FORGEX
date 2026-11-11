"""Base plugin interface for FORGEX."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PluginContext:
    """Context passed to plugin lifecycle methods."""

    workspace: str
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PluginResult:
    """Result returned by a plugin operation."""

    success: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Plugin(ABC):
    """Abstract base class for FORGEX plugins."""

    name: str = "plugin"
    version: str = "1.0.0"
    description: str = ""
    permissions: list[str] = field(default_factory=list)

    @abstractmethod
    async def initialize(self, context: PluginContext) -> PluginResult:
        """Initialize the plugin."""

    @abstractmethod
    async def shutdown(self) -> PluginResult:
        """Shutdown the plugin."""

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> PluginResult:
        """Execute a plugin action."""

    def validate_permissions(self, required: list[str], granted: list[str]) -> bool:
        """Check if all required permissions are granted."""
        granted_set = set(granted)
        return all(p in granted_set for p in required)


__all__ = ["Plugin", "PluginContext", "PluginResult"]
