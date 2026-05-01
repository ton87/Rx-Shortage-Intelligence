"""
POC: minimal FastMCP server skeleton.

Run: python research/02-mcp-servers/POC-fastmcp-skeleton.py

Speaks MCP over stdio. Use a client (FastMCP Client or Claude Desktop) to invoke.
Ctrl+C to stop.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("rx-shortage-skeleton")


@mcp.tool()
def echo(message: str) -> str:
    """Echo back the input message. For wiring tests."""
    return f"echo: {message}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    # stdio transport is the default; reads JSON-RPC from stdin, writes to stdout
    mcp.run()
