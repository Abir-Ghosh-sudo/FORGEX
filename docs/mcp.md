# FORGEX MCP Documentation

## Model Context Protocol (MCP)

FORGEX supports MCP client and server integration for connecting external tools.

### MCP Client

Connect to MCP servers to discover and call tools:

```python
from forgex.mcp.client import MCPClient

async with MCPClient(server_command=["npx", "@modelcontextprotocol/server-filesystem", "/path"]) as client:
    tools = await client.list_tools()
    result = await client.call_tool("read_file", {"path": "/path/to/file.txt"})
```

### MCP Server

Expose FORGEX tools as MCP endpoints:

```python
from forgex.mcp.server import MCPServer

server = MCPServer("forgex")
server.register_tool(
    name="forgex_read_file",
    description="Read a file from the workspace",
    input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
    handler=my_handler,
)
await server.start()
```

### Tool Registry

Register MCP tools with permission checks:

```python
from forgex.mcp.tool_registry import MCPToolRegistry
from forgex.security.permissions import PermissionManager

registry = MCPToolRegistry(permission_manager=perm_manager)
registry.register_tool(
    name="terminal_run",
    description="Run a terminal command",
    input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
    permission_required="terminal.execute",
)
```

### Optional Dependency

```bash
pip install "forgex-ai[mcp]"
```
