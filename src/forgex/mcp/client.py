"""MCP client for connecting to MCP servers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MCPClientError(RuntimeError):
    """Raised when MCP client operations fail."""


class MCPClient:
    """Client for connecting to Model Context Protocol servers."""

    def __init__(
        self,
        *,
        server_command: list[str] | None = None,
        server_url: str | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        self.server_command = list(server_command or [])
        self.server_url = server_url
        self.cwd = Path(cwd).expanduser().resolve() if cwd else None
        self._session: Any = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to an MCP server."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:
            raise MCPClientError(
                "mcp package is not installed. Install 'mcp' to use MCP clients."
            ) from exc

        if not self.server_command and not self.server_url:
            raise MCPClientError("Either server_command or server_url must be provided.")

        try:
            if self.server_command:
                params = StdioServerParameters(
                    command=self.server_command[0],
                    args=self.server_command[1:],
                    cwd=str(self.cwd) if self.cwd else None,
                )
                read, write = await stdio_client(params).__aenter__()
                self._session = ClientSession(read, write)
                await self._session.__aenter__()
                await self._session.initialize()
            else:
                raise MCPClientError("Streamable HTTP MCP client not yet implemented.")
            self._connected = True
            logger.info("MCP client connected.")
        except MCPClientError:
            raise
        except Exception as exc:
            raise MCPClientError(f"Failed to connect to MCP server: {exc}") from exc

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        if not self._connected or self._session is None:
            raise MCPClientError("MCP client is not connected.")
        try:
            result = await self._session.list_tools()
            tools = []
            for tool in result.tools or []:
                tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema or {},
                    }
                )
            return tools
        except Exception as exc:
            raise MCPClientError(f"Failed to list MCP tools: {exc}") from exc

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        if not self._connected or self._session is None:
            raise MCPClientError("MCP client is not connected.")
        try:
            result = await self._session.call_tool(name, arguments)
            return result
        except Exception as exc:
            raise MCPClientError(f"MCP tool call '{name}' failed: {exc}") from exc

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                logger.debug("MCP session close error.", exc_info=True)
            self._session = None
        self._connected = False

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()


__all__ = ["MCPClient", "MCPClientError"]
