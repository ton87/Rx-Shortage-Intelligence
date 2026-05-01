"""
POC: bridge a FastMCP stdio server into the Anthropic SDK tool format.

Run: python research/02-mcp-servers/POC-stdio-bridge.py
Requires: ANTHROPIC_API_KEY env var; the skeleton server in this folder.

Demonstrates:
- FastMCP Client spawns the server subprocess
- list_tools() returns MCP-format tool schemas
- Convert MCP schemas → Anthropic tool schemas
- One-shot Claude call where Claude invokes echo()
- Tool call proxied back to MCP server
- Final response printed
"""

import asyncio
import os
from pathlib import Path

import anthropic
from fastmcp import Client

SERVER_PATH = Path(__file__).parent / "POC-fastmcp-skeleton.py"
MODEL = "claude-sonnet-4-6"


def mcp_tool_to_anthropic(t) -> dict:
    """Convert an MCP Tool object to an Anthropic tool schema dict."""
    return {
        "name": t.name,
        "description": t.description or "",
        "input_schema": t.inputSchema,
    }


async def run():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY in env first.")
        return

    async with Client(str(SERVER_PATH)) as mcp_client:
        # Discover tools
        mcp_tools = await mcp_client.list_tools()
        anthropic_tools = [mcp_tool_to_anthropic(t) for t in mcp_tools]
        print(f"Discovered {len(anthropic_tools)} tools:")
        for t in anthropic_tools:
            print(f"  - {t['name']}: {t['description'][:60]}")

        # One-shot Claude call
        client = anthropic.Anthropic()
        messages = [{"role": "user", "content": "Use the echo tool to say: hello world"}]

        while True:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=512,
                tools=anthropic_tools,
                messages=messages,
            )
            print(f"\nstop_reason={resp.stop_reason}")

            if resp.stop_reason == "end_turn":
                # Print final assistant text
                for block in resp.content:
                    if block.type == "text":
                        print(f"\nAssistant: {block.text}")
                break

            if resp.stop_reason == "tool_use":
                # Append assistant turn
                messages.append({"role": "assistant", "content": resp.content})
                tool_results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        print(f"  → tool_use: {block.name}({block.input})")
                        result = await mcp_client.call_tool(block.name, block.input)
                        text = result.content[0].text if result.content else "(empty)"
                        print(f"  ← tool_result: {text}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": text,
                        })
                messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    asyncio.run(run())
