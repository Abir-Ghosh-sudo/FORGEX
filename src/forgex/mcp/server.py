"""MCP server for exposing FORGEX tools as MCP endpoints."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MCPServerError(RuntimeError):
    """Raised when MCP server operations fail."""


class MCPServer:
    """Minimal MCP server wrapper for FORGEX tool exposure."""

    def __init__(self, name: str = "forgex") -> None:
        self.name = name
        self._tools: dict[str, dict[str, Any]] = {}
        self._started = False

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Any,
    ) -> None:
        """Register a tool handler."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema or {},
            "handler": handler,
        }

    def list_registered_tools(self) -> list[dict[str, Any]]:
        """Return registered tool definitions."""
        return [
            {k: v for k, v in tool.items() if k != "handler"}
            for tool in self._tools.values()
        ]

    async def start(self) -> None:
        """Start the MCP server (placeholder for full stdio/HTTP implementation)."""
        if self._started:
            return
        try:
            pass
        except Exception:
            logger.warning("mcp package not installed; MCP server will be a stub.")
            self._started = True
            return
        self._started = True
        logger.info("MCP server %s started.", self.name)

    async def stop(self) -> None:
        """Stop the MCP server."""
        self._started = False

    async def __aenter__(self) -> MCPServer:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()


__all__ = ["MCPServer", "MCPServerError"]
