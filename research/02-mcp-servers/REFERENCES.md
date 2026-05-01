# MCP Servers — References

## MCP protocol

- MCP spec: https://modelcontextprotocol.io/
- Architecture: https://modelcontextprotocol.io/docs/concepts/architecture
- Transports (stdio + HTTP): https://modelcontextprotocol.io/docs/concepts/transports

## Python SDKs

- **mcp** PyPI: https://pypi.org/project/mcp/
  - `pip install "mcp[cli]"`
- **fastmcp** PyPI: https://pypi.org/project/fastmcp/
  - High-level wrapper; ships `Client` for talking to servers
  - `pip install fastmcp`
- FastMCP docs: https://gofastmcp.com/

## Anthropic + MCP

- Anthropic MCP connector docs: https://docs.anthropic.com/claude/docs/mcp
- `mcp_servers` beta parameter: https://docs.anthropic.com/en/api/messages-create
- Beta header: `mcp-client-2025-04-04`

## Anthropic SDK

- Python SDK: https://github.com/anthropics/anthropic-sdk-python
- Tool use docs: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- Model ID `claude-sonnet-4-6`: https://www.anthropic.com/news/claude-sonnet-4-6

## PRD anchors

- §12.3 MCP servers (which 3, which tools)
- §12.4 "MCP over function-calling: demonstrates future-state distribution architecture"
- §6.3 Strategic value: MCP-distribution surface
- v1.0 roadmap: MCP server exposure for customer-side AI

## Internal POCs

- `POC-fastmcp-skeleton.py` — bare server, run as standalone
- `POC-stdio-bridge.py` — Anthropic SDK ↔ FastMCP Client end-to-end demo
- `POC-fda-shortage-server.py` — real server stub, copies into `src/servers/` at H2
