# Rx Shortage Intelligence — Issues

> H0 + H1: ✅ Done (committed `22f1e872`)
> Current milestone: H2 — MCP Servers

---

## T-001: Implement fda_shortage_server.py ✅ Done (`c7a1b3b6`, 2026-05-01)

- **Block:** H2
- **Status:** Done
- **Files:** `src/servers/fda_shortage_server.py`
- **Acceptance criteria:**
  - [x] `FastMCP("fda-shortage")` server starts without error via `mcp.run()`
  - [x] `get_current_shortages(limit: int = 20) -> list[dict]` tool returns trimmed shortage records with `generic_name`, `status`, `rxcui` (list), `shortage_reason`, `source_url`
  - [x] `get_shortage_detail(rxcui: str) -> dict` tool returns single record or `{"error": "..."}` on miss
  - [x] All HTTP calls go through `src/cache.py` `cached_get()` with `TTL_FDA_SHORTAGES`
  - [x] Both tools wrap body in `try/except`, return `{"error": "..."}` on failure — never raise
  - [x] `status:Current` filter applied (Q1 decision — TBD excluded)
  - [x] `rxcui` preserved as list in returned records (Q2 decision)
  - [x] `source_url` field present on every record for citation support (query-specific URL)
- **Tests:** 50 passing (29 contract + 21 adversarial)

---

## T-002: Implement drug_label_server.py

- **Block:** H2
- **Status:** Backlog
- **Files:** `src/servers/drug_label_server.py`
- **Acceptance criteria:**
  - [ ] `FastMCP("drug-label")` server starts without error
  - [ ] `get_drug_label_sections(rxcui: str, sections: list[str]) -> dict` tool returns requested sections from openFDA label
  - [ ] Falls back to `openfda.generic_name` search when RxCUI lookup returns 404 or empty (Label RxCUI mismatch gotcha — RxNorm canonical `2555` vs Label-indexed `309311` for cisplatin)
  - [ ] `search_labels_by_indication(query: str) -> list[dict]` tool returns matching label summaries
  - [ ] Only the 7 relevant sections returned: `indications_and_usage`, `dosage_and_administration`, `contraindications`, `warnings`, `boxed_warning`, `drug_interactions`, `clinical_pharmacology`
  - [ ] All HTTP calls through `src/cache.py` with `TTL_OPENFDA_LABEL`
  - [ ] Both tools wrapped in `try/except`, return `{"error": "..."}` on failure
  - [ ] `source_url` field present on every returned record
- **Out of scope:** Full 30+ section label return, NDC reconciliation, compounded drugs, pricing
- **Source:** ROADMAP.md H2 + `research/02-mcp-servers/LESSON.md` + `research/01-data-layer/POC-openfda-labels.py`
- **Cut line ref:** n/a for this ticket

---

## T-003: Implement rxnorm_server.py

- **Block:** H2
- **Status:** Backlog
- **Files:** `src/servers/rxnorm_server.py`
- **Acceptance criteria:**
  - [ ] `FastMCP("rxnorm")` server starts without error
  - [ ] `normalize_drug_name(name: str) -> dict` tool returns `{"rxcui": "...", "name": "...", "source_url": "..."}` or `{"error": "..."}` on miss
  - [ ] `get_therapeutic_alternatives(rxcui: str) -> list[dict]` tool returns ATC class members filtered by: same route_of_administration excluded where possible, excludes self, caps at 10 results
  - [ ] All HTTP calls through `src/cache.py` with `TTL_RXNORM`
  - [ ] RxClass used for alternatives (not RxNorm `getRelatedByType` — that returns brand/generic variants only, not true alternatives)
  - [ ] Each alternative carries `rxcui`, `name`, `confidence: "class-member"` label
  - [ ] Both tools wrapped in `try/except`, return `{"error": "..."}` / `[]` on failure
- **Out of scope:** DrugBank, hand-curated equivalence tables, brand-vs-generic NDC reconciliation, route filtering beyond ATC class
- **Source:** ROADMAP.md H2 + `research/02-mcp-servers/LESSON.md` + `research/01-data-layer/POC-rxnorm-rxclass.py`
- **Cut line ref:** "drop rxnorm_server, fold normalize + alternatives into drug_label_server" — only if behind schedule

---

## T-004: Implement mcp_bridge.py

- **Block:** H2
- **Status:** Backlog
- **Files:** `src/mcp_bridge.py`
- **Acceptance criteria:**
  - [ ] `MCPBridge` class (or module-level functions) spawns all 3 servers via `fastmcp.Client`
  - [ ] `list_tools() -> list[dict]` returns exactly 6 Anthropic-format tool schemas: `[{"name": ..., "description": ..., "input_schema": ...}]`
  - [ ] `call_tool(name: str, args: dict) -> str` routes call to the correct server, returns text result
  - [ ] MCP `inputSchema` (camelCase) correctly converted to Anthropic `input_schema` (snake_case)
  - [ ] Each tool call logs: `{"ts": ..., "server": ..., "tool": ..., "args": ..., "result_preview": ..., "duration_ms": ...}` — appended to `tool_calls` list accessible to briefing.py (NFR-4 audit trail)
  - [ ] `python -m src.mcp_bridge` (module `__main__`) prints all 6 tool names and exits 0
  - [ ] Async context properly cleaned up via `try/finally` — no orphaned subprocesses
  - [ ] Tool name collision check at startup: raises `RuntimeError` if two servers expose same tool name
- **Out of scope:** HTTP transport, ngrok, Anthropic SDK `mcp_servers` beta, multi-tenancy, auth
- **Source:** ROADMAP.md H2 + `research/02-mcp-servers/POC-stdio-bridge.py` + `research/02-mcp-servers/LESSON.md`
- **Cut line ref:** n/a — bridge is the exit criterion for H2

---

## Completed

> H0 + H1 tickets tracked in `.planning/01-data-layer/PLAN.md` (pre-ISSUES.md workflow)
