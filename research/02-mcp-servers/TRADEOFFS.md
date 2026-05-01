# MCP Servers — Tradeoffs

## stdio vs HTTP transport

| Approach | Pro | Con |
|----------|-----|-----|
| **stdio + FastMCP Client bridge** (chosen) | Local, no network, no public URL, no auth dance | DIY bridge; SDK doesn't auto-wire |
| HTTP + ngrok + `mcp_servers` beta | SDK-native; cleanest agent code | Public exposure, ngrok install, network latency |
| HTTP localhost + `mcp_servers` beta | No public URL | SDK requires URL; localhost may not be reachable depending on Anthropic's connector implementation |

stdio chosen because hackathon = local-only demo and bridge code is ~30 LOC.

## Real MCP vs inline function tools

Decided in clarifying questions. Real MCP chosen for PRD fidelity.

**Drawbacks accepted**:
- +30-45 min build time vs inline functions
- Bridge code is novel (not in Anthropic docs)
- Async-in-Streamlit gotchas

**Wins accepted**:
- PRD §12.3, §6.3, v1.0 roadmap all reference MCP — signal not just plumbing
- Customer can plug servers into their own agents post-demo
- Process isolation = one server crash doesn't kill briefing
- Distributable: can ship as standalone `pip install` packages later

## 3 servers vs 1 server

| Approach | Pro | Con |
|----------|-----|-----|
| **3 servers (PRD-faithful)** (chosen) | Mirrors PRD §12.3; demonstrates fan-out pattern | 3× spawn overhead at startup |
| 1 server, 6 tools | Simpler, faster startup | Diverges from PRD; less clean separation |

3 servers is cosmetic but customer-facing (Anton wrote the PRD; let him see his architecture). If H2 falls behind, fold rxnorm into drug_label.

## Tool granularity

Each server exposes 2 tools, not 1. Why:
- `get_current_shortages()` (list) and `get_shortage_detail(rxcui)` (single) are different agent intents
- LLM picks correctly when descriptions are precise
- Smaller per-tool input schemas = better compliance from Claude

Avoid mega-tools with `mode: "list"|"detail"` flags. Claude handles many small tools better than few wide ones.

## Async vs sync server impl

FastMCP supports both. We use sync (`def`, not `async def`) for tool bodies because:
- httpx synchronous client is simpler
- Servers are stdio = single-threaded anyway
- One blocking I/O per tool call ≪ 60-sec budget

The Client side is async (FastMCP Client is async-only). That's fine — wrap in `asyncio.run()` from Streamlit.

## What we'd improve given more time

- Add MCP `resources/` for static files (e.g., synthetic formulary as resource)
- Pin specific MCP package version for reproducibility
- Server health check at startup before listing tools
- Streaming results for `get_current_shortages` if list >50 items
