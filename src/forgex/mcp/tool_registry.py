"""MCP tool registry for FORGEX.

Discovers, registers, and validates MCP tools with permission integration.
"""

from __future__ import annotations

import logging
from typing import Any

from forgex.security.permissions import PermissionManager

logger = logging.getLogger(__name__)


class MCPToolRegistry:
    """Registry for MCP tools with permission-aware execution."""

    def __init__(
        self,
        permission_manager: PermissionManager | None = None,
    ) -> None:
        self.permission_manager = permission_manager
        self._tools: dict[str, dict[str, Any]] = {}
        self._clients: dict[str, Any] = {}

    def register_client(self, name: str, client: Any) -> None:
        """Register an MCP client instance."""
        self._clients[name] = client

    async def discover_tools(self, client_name: str) -> list[dict[str, Any]]:
        """Discover tools from a registered MCP client."""
        client = self._clients.get(client_name)
        if client is None:
            raise ValueError(f"MCP client not registered: {client_name}")
        tools = await client.list_tools()
        for tool in tools:
            self._tools[tool["name"]] = {
                **tool,
                "client": client_name,
            }
        return tools

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        client: str | None = None,
        permission_required: str | None = None,
    ) -> None:
        """Register a tool with optional permission requirement."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema or {},
            "client": client,
            "permission_required": permission_required,
        }

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered MCP tools."""
        return [
            {k: v for k, v in tool.items() if k not in ("handler", "client")}
            for tool in self._tools.values()
        ]

    def get_tool(self, name: str) -> dict[str, Any] | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def requires_permission(self, name: str) -> str | None:
        """Return the permission required for a tool, if any."""
        tool = self._tools.get(name)
        if tool:
            return tool.get("permission_required")
        return None

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        actor: str | None = None,
    ) -> Any:
        """Call a registered MCP tool with permission check."""
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"MCP tool not registered: {name}")

        permission = tool.get("permission_required")
        if (
            permission
            and self.permission_manager is not None
            and not self.permission_manager.has_permission(actor or "system", permission)
        ):
            from forgex.security.errors import PermissionDeniedError

            raise PermissionDeniedError(
                f"Permission '{permission}' required for MCP tool '{name}'.",
                actor=actor or "system",
                permission=permission,
            )

        client_name = tool.get("client")
        if client_name and client_name in self._clients:
            client = self._clients[client_name]
            return await client.call_tool(name, arguments)

        handler = tool.get("handler")
        if handler:
            return handler(arguments)

        raise ValueError(f"No handler or client available for MCP tool '{name}'.")


__all__ = ["MCPToolRegistry"]
