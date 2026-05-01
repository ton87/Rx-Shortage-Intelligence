"""FastMCP Client bridge: spawns 3 MCP servers, exposes 6 tools to the agent loop."""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import Client

_ROOT = Path(__file__).parent.parent  # project root (for PYTHONPATH)
_SERVERS_DIR = Path(__file__).parent / "servers"

# Subprocesses need the project root on PYTHONPATH so `from src.cache import ...` works.
_ENV = {**os.environ, "PYTHONPATH": str(_ROOT)}

CONFIG = {
    "mcpServers": {
        "fda_shortage": {
            "command": sys.executable,
            "args": [str(_SERVERS_DIR / "fda_shortage_server.py")],
            "env": _ENV,
        },
        "drug_label": {
            "command": sys.executable,
            "args": [str(_SERVERS_DIR / "drug_label_server.py")],
            "env": _ENV,
        },
        "rxnorm": {
            "command": sys.executable,
            "args": [str(_SERVERS_DIR / "rxnorm_server.py")],
            "env": _ENV,
        },
    }
}


def _mcp_to_anthropic(tool) -> dict:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema,
    }


def _extract_text(result) -> str:
    # fastmcp v3: list/complex returns come via structured_content
    if result.structured_content:
        payload = result.structured_content.get("result", result.structured_content)
        return json.dumps(payload)
    # Simple text returns
    if result.content:
        c = result.content[0]
        return c.text if hasattr(c, "text") else str(c)
    return ""


def _server_for_tool(tool_name: str) -> str:
    for key in CONFIG["mcpServers"]:
        if tool_name.startswith(key + "_"):
            return key
    return "unknown"


class MCPBridge:
    def __init__(self):
        self._client: Client | None = None
        self._tools: list[dict] = []
        self._tool_names: set[str] = set()
        self.tool_calls: list[dict] = []

    async def __aenter__(self):
        self._client = Client(CONFIG)
        try:
            await self._client.__aenter__()
            mcp_tools = await self._client.list_tools()
            for t in mcp_tools:
                if t.name in self._tool_names:
                    raise RuntimeError(f"Tool name collision: '{t.name}'")
                self._tool_names.add(t.name)
                self._tools.append(_mcp_to_anthropic(t))
        except Exception:
            await self._client.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *exc):
        if self._client is not None:
            await self._client.__aexit__(*exc)

    def list_tools(self) -> list[dict]:
        return list(self._tools)

    async def call_tool(self, name: str, args: dict) -> str:
        if name not in self._tool_names:
            raise ValueError(f"Unknown tool: '{name}'")
        t0 = time.monotonic()
        result = await self._client.call_tool(name, args)
        duration_ms = int((time.monotonic() - t0) * 1000)
        text = _extract_text(result)
        self.tool_calls.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "server": _server_for_tool(name),
            "tool": name,
            "args": args,
            "result_preview": text[:200],
            "duration_ms": duration_ms,
        })
        return text


async def _smoke():
    async with MCPBridge() as bridge:
        tools = bridge.list_tools()
        print(f"Discovered {len(tools)} tools:")
        for t in tools:
            print(f"  - {t['name']}")


if __name__ == "__main__":
    asyncio.run(_smoke())
