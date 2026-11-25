# MCP

The server communicates through MCP stdio transport.

Typical agent configuration conceptually resembles:

```json
{
  "mcpServers": {
    "code-index": {
      "command": "code-index-mcp",
      "args": []
    }
  }
}
