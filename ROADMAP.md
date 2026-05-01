# Rx Shortage Intelligence — 6-Hour Hackathon Roadmap

**Goal**: ship v0.1 prototype matching PRD §9.1 in **6 hours hard**. Local Streamlit demo, real public APIs, real MCP servers, claude-sonnet-4-6.

**Pre-read before H0**: every section's `research/0X-*/LESSON.md` for the upcoming block. Each block has cut lines — ship beats perfect.

---

## H0 — Setup (0:00 → 0:15)

**Pre-read**: `research/07-tech-stack-tradeoffs/DECISIONS.md`

**Do**:
```bash
cd /Users/ragglesoft/Desktop/rx-shortage-intelligence
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# fallback if requirements.txt missing:
# pip install anthropic "mcp[cli]" "fastmcp>=2.0" httpx diskcache streamlit python-dotenv
mkdir -p src data cache/api
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env  # use ANTHROPIC_API_KEY exactly — SDK reads this name
```

**Note**: `mcp[cli]` is the official package (server side). `fastmcp` is the separate third-party package providing the `Client` used by the bridge. Both required.

**Repo skeleton**:
```
src/
  main.py                    # entry: `streamlit run src/main.py`
  agent.py                   # tool use loop
  mcp_bridge.py              # FastMCP Client wrapper for Anthropic SDK
  briefing.py                # generate_briefing(), diff logic
  cache.py                   # diskcache wrapper
  servers/
    fda_shortage_server.py
    drug_label_server.py
    rxnorm_server.py
  data_loader.py             # synthetic formulary + active orders + yesterday snapshot
  eval/
    runner.py
    cases.json
data/
  synthetic_formulary.json
  active_orders.json
  yesterday_snapshot.json
  briefings/                 # YYYY-MM-DD.json artifacts
cache/api/                   # diskcache disk
```

**Exit criteria**: `python -c "import anthropic, mcp, streamlit, diskcache; print('ok')"` prints `ok`.

**Cut line**: none — must finish in 15 min or kill project.

---

## H1 — Data layer (0:15 → 1:00, 45 min)

**Pre-read**: `research/01-data-layer/LESSON.md`

**Do**:
1. `data_loader.py` — fetch live FDA shortages once, sample 30 RxCUIs as synthetic formulary base.
2. Write `data/synthetic_formulary.json` (30 drugs, formulary_status, route_of_admin, preferred_alternatives).
3. Write `data/active_orders.json` (random 5-50 orders/drug, last_30_days, departments).
4. Write `data/yesterday_snapshot.json` — copy of FDA feed minus 2 records (→ resolved), 2 status flips (→ critical), rest identical.
5. Smoke test: `python -m src.data_loader` prints counts.

**Exit criteria**: 3 JSON files exist, formulary overlaps live shortage feed by ≥5 drugs.

**Cut line**: skip yesterday-snapshot diversity — keep just 2 hand-picked diffs.

---

## H2 — MCP servers (1:00 → 2:00, 60 min)

**Pre-read**: `research/02-mcp-servers/LESSON.md` + POC-stdio-bridge.py

**Do**:
1. `src/servers/fda_shortage_server.py` — FastMCP, tools: `get_current_shortages()`, `get_shortage_detail(rxcui)`. Wraps openFDA shortages JSON via `cache.py`.
2. `src/servers/drug_label_server.py` — tools: `get_drug_label_sections(rxcui, sections[])`, `search_labels_by_indication(query)`. Wraps openFDA labels.
3. `src/servers/rxnorm_server.py` — tools: `normalize_drug_name(name)`, `get_therapeutic_alternatives(rxcui)`. Wraps RxNorm + RxClass.
4. `src/mcp_bridge.py` — uses `fastmcp.Client` to spawn each server, list tools, convert schemas to Anthropic `{name, description, input_schema}`, expose `call_tool(name, args)` proxy.
5. Smoke test: `python -m src.mcp_bridge` lists 6 tools across 3 servers.

**Exit criteria**: 3 MCP servers start without error, bridge returns 6 tool schemas.

**Cut line**: drop `rxnorm_server`, fold normalize + alternatives into `drug_label_server`. Saves ~15 min.

---

## H3 — Agent loop (2:00 → 3:00, 60 min)

**Pre-read**: `research/03-agent-loop/LESSON.md` + `research/03b-caching/LESSON.md` + `research/03-agent-loop/SYSTEM-PROMPTS.md`

**Do**:
1. `src/agent.py` — function `run_agent(system_prompt, user_message, tools)` implementing while-loop on `stop_reason=="tool_use"`.
2. Copy `ROLE_AND_RULES` + `SEVERITY_RUBRIC` blocks from `research/03-agent-loop/SYSTEM-PROMPTS.md` (token-verified, cache-eligible). Apply `cache_control: {"type": "ephemeral"}` on each.
3. Wire `mcp_bridge.call_tool()` as the tool executor.
4. RAG = `chunk_label_json()` in `briefing.py` — 7 sections × ~800 tokens each, BM25-keyword retrieve top-3.
5. Smoke test: end-to-end run on one drug (e.g., RxCUI 11124 = cisplatin) returns a `BriefingItem` JSON with `severity`, `summary`, `alternatives`, `citations`.

**Exit criteria**: one BriefingItem produced with ≥1 citation linking to source URL.

**Cut line**: drop RAG, pass full label JSON as text. Eats ~3K tokens but unblocks loop.

---

## H4 — Briefing + diff (3:00 → 3:45, 45 min)

**Pre-read**: `research/04-briefing-diff/LESSON.md`

**Do**:
1. `src/briefing.py` — `compute_diff(today, yesterday)` returns `{new[], changed[], resolved[]}`.
2. `generate_briefing(customer_id, date)` — for each diff item: severity classify, retrieve label chunks, run agent, collect BriefingItem. Returns BriefingRun.
3. Persist to `data/briefings/{date}.json`.
4. Smoke test: full run produces ~5-10 BriefingItems across severity buckets.

**Exit criteria**: BriefingRun JSON written, contains items with rationale + citations + confidence.

**Cut line**: hardcode 5 demo drugs instead of looping all 30. Skip resolved bucket if behind.

---

## H5 — Streamlit UI (3:45 → 5:15, 90 min)

**Pre-read**: `research/05-streamlit-ui/LESSON.md`

**Architecture**: Pattern B per CLAUDE.md. Streamlit stays 100% sync — no `fastmcp`, no `asyncio`, no `@st.cache_resource`. Briefing CLI writes JSON, Streamlit reads JSON.

**Do**:
1. `src/main.py` — page layout: top stats bar, severity-ordered briefing list, expandable rows (FR-11). Pure sync.
2. Dashboard reads latest `data/briefings/*.json` via `json.loads(path.read_text())`. No `@st.cache_data` needed (parse <5ms).
3. Drill-down panel: reads logged `tool_calls[]` from briefing JSON (not live). Citation links + accept/override buttons.
4. Re-run button: `subprocess.run(["python", "-m", "src.briefing"], capture_output=True)` then re-read JSON. ~30-60s. Show spinner via `st.spinner()`.
5. Eval tab: reads `data/eval_results.json` (filled by H6), 15-case grid.

**Exit criteria**: `streamlit run src/main.py` shows working dashboard with real briefing. Re-run button regenerates without crashing Streamlit.

**Cut line**: drop eval tab — empty placeholder. Drop drill-down trace, show citations only. Saves ~30 min.

**v0.2 nice-to-have (skip for v0.1)**: `@st.cache_resource` for persistent in-process MCP client → faster Re-run via warm subprocess. See `research/03b-caching/POC-streamlit-cache.py` reference.

---

## H6 — Eval harness (5:15 → 5:45, 30 min)

**Pre-read**: `research/06-eval-harness/LESSON.md`

**Do**:
1. `src/eval/cases.json` — 15 hand-curated cases with input + expected output (already in `research/06-eval-harness/POC-eval-cases.json`, copy over).
2. `src/eval/runner.py` — load cases, run `generate_briefing` on each, score with Claude-as-judge across 5 dims.
3. Persist `data/eval_results.json`.
4. v2 hook: `prompt_version` arg on `generate_briefing()`, scaffolded but not exercised.

**Exit criteria**: 15 cases scored, results render in eval tab.

**Cut line**: drop to 5 cases, hardcode v2 placeholder scores.

---

## Buffer (5:45 → 6:00, 15 min)

- Write demo README.md (how to run, what to show, known gaps).
- Screen-record 2-min Loom walkthrough as fallback if live demo fails.
- Pre-warm caches: run briefing once before customer call so prompt cache + diskcache hit on demo.
- Verify `.env` not committed.

---

## Failure modes during build

| Symptom | Likely cause | 5-min fix |
|---------|--------------|-----------|
| FDA API 429 | rate limit hit | diskcache wrapper missing or TTL too short |
| MCP bridge hangs | server crashed silently | `subprocess.Popen(stderr=subprocess.PIPE)` + log to terminal |
| Agent loops forever | tool returns malformed JSON | wrap tool exec in try/except, return error string |
| Streamlit blank | uncaught exception in `cache_data` fn | check terminal; `st.cache_data.clear()` + rerun |
| Cost over budget | prompt cache not hitting | inspect `usage.cache_read_input_tokens` on response |
| Empty briefing | formulary doesn't overlap shortages | re-sample formulary from live feed |

## Demo script

1. Open dashboard: pre-rendered briefing visible in <2 sec (Tier 3 cache).
2. Point at "3 critical, 2 watch, 1 resolved" stats — note timestamp.
3. Click critical item → drill-down → show tool-call trace + citations.
4. Click citation → opens openFDA URL in new tab.
5. Hit "Re-run" → show streaming tool calls in `st.status`.
6. Eval tab: 15 cases, 5-dim scores, hallucination rate <2%.
7. Close: "v0.2 = real customer formulary integration. v1.0 = MCP exposure for customer-side AI."
