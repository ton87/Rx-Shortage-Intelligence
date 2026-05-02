# Rx Shortage Intelligence

AI-assisted morning briefing for hospital pharmacy directors. Cross-references live FDA drug shortages against a hospital's formulary + active orders, classifies severity (Critical / Watch / Resolved), recommends therapeutic alternatives with citations. Replaces a ~20-min manual workflow per drug.

**Scope**: v0.1 hackathon prototype. 6-hour build window. Local Streamlit demo. Synthetic formulary + orders, real public APIs (FDA, openFDA, RxNorm).

**Source of truth**:
- `docs/Rx_Shortage_Intelligence_PRD_v2.md.pdf` — full PRD
- `ROADMAP.md` — H0 → H6 build plan with cut lines
- `QUESTIONS-FOR-ANTON.md` — open clarifying questions for customer
- `research/00-prd-summary/LESSON.md` — 1-page PRD distillation
- `research/00-prd-summary/KEY-CONSTRAINTS.md` — what cannot be cut
- `research/03-agent-loop/SYSTEM-PROMPTS.md` — paste-ready ROLE_AND_RULES + SEVERITY_RUBRIC for H3 agent (token-verified, cache-eligible)
- `research/07-tech-stack-tradeoffs/DECISIONS.md` — stack rationale
- `research/08-concerns-risks/RISKS.md` — risk register + mitigations

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| LLM | Anthropic Claude `claude-sonnet-4-6` | Native MCP, tool use, citations |
| Agent | Anthropic SDK native tool-use loop (~50 LOC) | Code IS the trace (FR-5) |
| Tools | 3 FastMCP stdio servers + bridge | PRD §12.3-faithful |
| RAG | BM25-lite over openFDA label JSON chunks | Zero infra |
| UI | Streamlit | Single-file, hours-to-ship |
| Persistence | Local JSON files | Demoable, diffable |
| API cache (Tier 2) | `diskcache` | Persists across runs |
| Prompt cache (Tier 1) | Anthropic ephemeral 5-min | 0.1× read cost |
| UI cache (Tier 3) | ~~`@st.cache_resource` + `@st.cache_data`~~ | **Deferred to v0.2** — see Architecture below |

## Architecture: briefing CLI + Streamlit reader (Pattern B)

v0.1 keeps Streamlit 100% sync. **No async, no MCP client, no subprocess management inside Streamlit.** This eliminates RISKS R12 (Streamlit + asyncio + stdio) entirely.

```
CLI:  python -m src.briefing
        ↓ (async, MCP, subprocesses live HERE)
        writes data/briefings/YYYY-MM-DD.json

UI:   streamlit run src/main.py
        ↓ (pure sync — json.loads, render)
        reads data/briefings/YYYY-MM-DD.json

Re-run button:
        subprocess.run(["python", "-m", "src.briefing"])
        then re-read JSON
```

Trade-offs accepted:
- Re-run takes ~30-60s (full subprocess startup vs warm in-process MCP)
- No live tool-call streaming in `st.status` (drill-down shows logged calls from JSON, not live)
- Per-rerun JSON parse is fast enough (<5ms for typical briefing) — no `@st.cache_data` needed for v0.1

Tier 3 caching (`@st.cache_resource` for persistent MCP client) = v0.2 nice-to-have. Reference design in `research/03b-caching/POC-streamlit-cache.py`. Adds ~50 LOC and re-introduces async/subprocess complexity in exchange for faster Re-run. Not worth it for v0.1 single-user demo.

## Repo layout

```
src/
  main.py                streamlit entry — tab dispatcher only
  briefing.py            CLI orchestrator
  mcp_bridge.py          FastMCP Client → Anthropic schema
  cache.py               diskcache wrapper
  domain/                pure logic — severity, confidence, fda, diff,
                         indexing, matching, constants
  agent/                 LLM concerns — loop.py, prompts.py, prefetch.py,
                         prompts/*.md (cache-eligible system blocks)
  io_/                   filesystem — briefing_store.py, data_loader.py
  ui/                    streamlit — theme.css + theme.py, components,
                         formatters, actions, runner, briefing_view,
                         formulary_view, eval_view
  servers/               three FastMCP stdio servers
  eval/
    runner.py
    cases.json
data/
  synthetic_formulary.json
  active_orders.json
  yesterday_snapshot.json
  briefings/YYYY-MM-DD.json
cache/api/               diskcache disk
research/                lessons + POCs (read before each block)
```

## Commands

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# or explicit:
# pip install anthropic "mcp[cli]" "fastmcp>=2.0" httpx diskcache streamlit python-dotenv

python -m src.io_.data_loader    # bootstrap synthetic data
python -m src.mcp_bridge         # smoke test: lists 6 tools
streamlit run src/main.py        # demo
python -m src.eval.runner        # run 15-case eval
```

**Two MCP packages required**: `mcp[cli]` ships server primitives (`mcp.server.fastmcp.FastMCP`); `fastmcp` is the third-party package providing the high-level `Client` used by `mcp_bridge.py`. Both must be installed.

## Non-negotiable principles (PRD §5)

1. Proactive over reactive
2. Speed = clinical safety (not UX preference)
3. Intuitive day one — no training
4. Customer-relevance over universal content
5. **Citation-first trust** — every claim → source URL
6. **Human-in-the-loop always** — agent never auto-acts
7. **Honest scope** — synthetic data labeled synthetic in UI

## Hard constraints (cannot drop)

- Real public API calls (FDA + openFDA + RxNorm), not mocks
- Model ID = `claude-sonnet-4-6`
- 3 MCP servers in Python (cut line: fold rxnorm into label server)
- 100% citation coverage on claims
- HITL accept/override on every BriefingItem
- Synthetic data banner visible in UI
- Cost <$0.05/briefing (currently modeled $0.08–$0.10 — document honestly)
- Latency <60 sec end-to-end
- Audit log: BriefingRun JSON includes `tool_calls[]`

## Out of scope for v0.1 (do NOT build)

Background scheduler, push notifications, real customer formulary, EHR/CDS Hooks, multi-tenancy, auth, drug pricing, prior auth, real inventory data. If you find yourself touching these, stop — v0.2+.

## Anti-patterns (PRD §10.4 — invert competitor failures)

- Multi-tab hierarchies → single scannable dashboard
- Search-first → briefing-first
- Show-everything → show-only-what-affects-this-hospital
- Modal stacks → inline expansion (max 1 click to source)
- Conversational chatbot → structured briefing (scan, don't type)

## Critical gotchas

- **MCP stdio bridge**: pre-written in `research/02-mcp-servers/POC-stdio-bridge.py` — copy, don't rediscover.
- **Formulary overlap**: sample 30 RxCUIs FROM live FDA shortage feed at H1. Verify ≥5 overlap before exit. Empty briefing = dead demo.
- **RxClass alts are a proxy**, not true equivalence. Filter same `route_of_administration`, exclude shortage-listed drugs, cap confidence at "medium", label as "ATC class member".
- **Yesterday snapshot regenerates**: only generate if file missing (`if not Path(...).exists()`). Otherwise diff goes empty.
- **Hallucinated drug/NDC** = top PRD risk. Schema requires `rxcui` per alternative. Eval scorer checks RxCUI against retrieved set. Low confidence → manual review, no one-click accept.
- **Streamlit stays sync**: per Pattern B above, Streamlit script never imports `fastmcp`, never calls `asyncio.run()`, never spawns threads. All async/MCP lives in `src/briefing.py` (CLI). Re-run button = `subprocess.run([...])`. Retires RISKS R12.
- **Tool errors**: wrap every tool body in `try/except`, return `{"error": "..."}`. Agent prompt: "do not retry; surface as `confidence: low`".
- **Hook-blocked substrings**: avoid the literal `e v a l (` (no spaces) and the python-serialization-module-starting-with-p word. Use `run_suite()` etc.
- **FDA `status` canonical values** (verified 2026-05-01): `Current` (1140), `To Be Discontinued` (498), `Resolved` (29). NOT `"Currently in Shortage"` — that string never existed in the API and breaks the search query (404). v0.1 fetches with `search=status:Current`. TBD handling = open Q (see QUESTIONS-FOR-ANTON.md Q1).
- **FDA `rxcui` is a list, not a scalar** (verified 2026-05-01). One generic = many products = many RxCUIs (methylphenidate ER returned 14). `_trim()` preserves list shape. `index_by_rxcui()` indexes by EVERY rxcui in the list so any formulary entry catches a match. ~10% of FDA records have empty rxcui list (R11) — acceptably dropped. Primary-RxCUI selection heuristic = open Q (see QUESTIONS-FOR-ANTON.md Q2).
- **openFDA Labels uses different RxCUIs than RxNorm canonical** (verified 2026-05-01). RxNorm "cisplatin" = `2555` (ingredient concept); openFDA Label = `309311` (clinical drug concept). When fetching labels by RxCUI fails, drug_label_server should fall back to `search=openfda.generic_name:"<name>"+AND+_exists_:openfda.rxcui` and return the first hit. Eval cases now use openFDA-indexed RxCUIs (originals preserved as `orig_rxcui_pre_2026_05_01`).

## Workflow rules

- **Pre-read before each block**: `research/0X-*/LESSON.md` for the block you're about to start. POCs are drop-in seeds, not specs.
- **Cut lines exist for a reason**: ROADMAP.md per-block "Cut line" tells you what to drop if behind. Ship beats perfect.
- **Don't add scope**. v0.2+ items are deliberately deferred — do not "while I'm here" them in.
- **Honest reporting**: if cost is $0.10 not $0.05, surface it in the eval tab. Honesty = trust per Principle 7.

## What "done" looks like (PRD §16)

Pharmacist opens dashboard → sees pre-rendered briefing in <2s → identifies top critical item in <30s → drills to agent reasoning + citations → accepts/overrides → closes. No docs read. Eval tab: 15 cases × 5 dims, hallucination <2%.
