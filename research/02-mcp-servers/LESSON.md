# MCP Servers — Lesson

## What is MCP

**Model Context Protocol**: open spec from Anthropic for connecting LLM agents to tools and data sources. JSON-RPC 2.0 over a transport (stdio or HTTP+SSE). Defines `tools/list`, `tools/call`, `resources/list`, `prompts/list`.

Why MCP and not plain function calling: MCP servers are **process-isolated, language-agnostic, distributable**. The PRD's strategic point (§6.3 + v1.0 roadmap) is that customer-side agents can consume our MCP servers as a distribution channel. So building real MCP servers is a forward investment, not just architectural cosplay.

## FastMCP

`mcp` Python package with `FastMCP` class — decorator API for defining tools. The path of least resistance.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

if __name__ == "__main__":
    mcp.run()  # stdio transport, default
```

That's a working MCP server. Type annotations + docstring become the JSON schema MCP exposes.

## The Anthropic SDK gap

Anthropic's `messages.create()` accepts a `tools=[...]` parameter — but that's their native tool format. The SDK has an `mcp_servers=[...]` beta parameter — but it expects **HTTP-reachable MCP URLs**, not local stdio processes.

Two paths bridge this gap:

### Path A — HTTP transport + ngrok (NOT chosen)
- Run server with `mcp.run(transport="http", port=8000)`
- Expose with `ngrok http 8000`
- Pass URL to `mcp_servers` with beta header
- Issues: ngrok auth, public exposure of dev API keys, +network roundtrip cost

### Path B — FastMCP Client + stdio (chosen)
- FastMCP ships a `Client` class that knows how to spawn a server subprocess and speak MCP over stdio
- Use `Client(server_path)` → `await client.list_tools()` → convert each tool's schema to Anthropic format
- On `tool_use` block from Claude, proxy to `await client.call_tool(name, args)`
- All in-process, no network, no public URL

Code shape:

```python
from fastmcp import Client

async def setup_mcp_tools():
    client = Client("src/servers/fda_shortage_server.py")
    await client.__aenter__()
    mcp_tools = await client.list_tools()
    anthropic_tools = [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        for t in mcp_tools
    ]
    return client, anthropic_tools
```

Then in agent loop:
```python
if block.type == "tool_use":
    result = await client.call_tool(block.name, block.input)
    tool_result = {"type": "tool_result", "tool_use_id": block.id, "content": result.content[0].text}
```

## Three servers (PRD §12.3)

| Server | Tools | Wraps |
|--------|-------|-------|
| `fda_shortage_server.py` | `get_current_shortages()`, `get_shortage_detail(rxcui)` | openFDA shortages JSON |
| `drug_label_server.py` | `get_drug_label_sections(rxcui, sections)`, `search_labels_by_indication(query)` | openFDA labels JSON |
| `rxnorm_server.py` | `normalize_drug_name(name)`, `get_therapeutic_alternatives(rxcui)` | RxNorm + RxClass |

If H2 falls behind: drop `rxnorm_server`, fold both tools into `drug_label_server`. Saves a `Client(...)` + bridge wiring.

## Streamlit + async

FastMCP Client uses `asyncio`. Streamlit runs synchronous. Use `asyncio.run(coro)` inside the cached function:

```python
@st.cache_resource
def get_mcp_clients():
    return asyncio.run(setup_mcp_tools())
```

`@st.cache_resource` (NOT `cache_data`) for client objects — `cache_data` tries to serialize the return value, which doesn't work for async-context objects.

## Auditability (NFR-4)

Every MCP tool call logs: timestamp, server, tool, args, response, duration_ms. Wrap `call_tool` in a logger that appends to BriefingRun.tool_calls[]. This is what FR-5 (drill-down agent traces) renders.

## What can go wrong

- **Server crashes silently**: `subprocess.Popen(stderr=subprocess.PIPE)`, log stderr. Or use `Client(..., debug=True)`.
- **Tool name collision**: 3 servers each have unique tool names. Check at startup.
- **Schema mismatch**: MCP tool schema uses `inputSchema` (camelCase). Anthropic expects `input_schema` (snake). Bridge converts.
- **Async leak**: forget `await client.__aexit__(...)` → orphaned subprocess. Use `try/finally`.
- **Empty tool result**: MCP returns `[TextContent(...)]`. If empty list, agent gets no tool_result and loops. Always return at least an error string.
