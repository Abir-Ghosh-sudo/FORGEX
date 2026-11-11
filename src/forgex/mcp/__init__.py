"""MCP (Model Context Protocol) integration for FORGEX.

Provides MCP client, server, tool discovery, registration, and
permission-aware integration with the FORGEX security system.
"""

from forgex.mcp.client import MCPClient
from forgex.mcp.server import MCPServer
from forgex.mcp.tool_registry import MCPToolRegistry

__all__ = ["MCPClient", "MCPServer", "MCPToolRegistry"]
