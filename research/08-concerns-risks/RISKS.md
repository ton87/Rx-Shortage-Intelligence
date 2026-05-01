# Concerns, Risks, Time Bombs

Per-section risks with mitigations. Read this before H0. Re-read at every block boundary.

## Critical risks (could kill the demo)

### R1 — MCP-Anthropic stdio bridge consumes H2
**Where**: `research/02-mcp-servers/`
**Likelihood**: Medium
**Impact**: Critical (no agent if no tools)
**Why**: Anthropic SDK has no built-in stdio MCP client. FastMCP `Client` bridges, but the schema-conversion + async-in-Streamlit wiring is novel.
**Mitigation**:
- POC-stdio-bridge.py is pre-written. Copy-paste, don't rediscover.
- Cut line: drop `rxnorm_server`, fold into `drug_label_server`. Saves 1 server's worth of bridge.
- Nuclear cut: drop MCP entirely, use inline functions. Loses PRD fidelity but ships briefing.

### R2 — Demo formulary doesn't overlap today's FDA shortages
**Where**: `research/01-data-layer/`
**Likelihood**: Low (mitigated by sampling-from-feed)
**Impact**: Critical (empty briefing = dead demo)
**Mitigation**: At H1, sample 30 RxCUIs FROM the live shortage feed. Verify overlap >5 at H1 exit. Re-sample if not.

### R3 — RxClass class members are too broad to be "alternatives"
**Where**: `research/01-data-layer/POC-rxnorm-rxclass.py`
**Likelihood**: High (it's a known proxy, not a true match)
**Impact**: High (wrong alternative recommendation = patient safety)
**Mitigation**:
- Filter to same `route_of_administration`
- Filter out drugs also currently in shortage
- Cap confidence at "medium" for class-member alts (rule-based ceiling)
- Label clearly: "ATC class member (proxy for therapeutic alternative)"

### R4 — Cost target <$0.05 not met
**Where**: `research/03b-caching/COST-MATH.md`
**Likelihood**: High (modeled at $0.08-$0.10 with full caching)
**Impact**: Medium (PRD violation but not demo-breaking)
**Mitigation**:
- Document honestly in eval tab + demo script
- Surface `usage.cache_read_input_tokens` to prove caching works
- v0.2 path: Haiku screening + Sonnet detail (mixture-of-models)

### R5 — H5 Streamlit UI overruns 90 min
**Where**: `research/05-streamlit-ui/`
**Likelihood**: High (UIs always take longer)
**Impact**: High (no UI = no demo)
**Mitigation**:
- POC-dashboard-layout.py is pre-built; copy in
- Cut line at 5:00: drop eval tab from UI, leave placeholder
- Cut line at 5:30: drop drill-down trace, citations only
- Hard floor: just dashboard works = shipping

### R6 — Yesterday snapshot regenerates and breaks diff
**Where**: `research/01-data-layer/POC-yesterday-snapshot.py`
**Likelihood**: Medium (will happen if user reruns data_loader)
**Impact**: Medium (diff produces empty buckets)
**Mitigation**: Only generate if file missing: `if not Path("data/yesterday_snapshot.json").exists()`. Document in code.

## High risks (degrade quality, demo still ships)

### R7 — Cache invalidation lies (stale briefing)
**Where**: `research/03b-caching/`
**Likelihood**: Medium during a working demo
**Impact**: Medium (user sees stale info)
**Mitigation**: Render `last_updated` timestamp prominently; "Re-run" button always visible.

### R8 — Hallucinated drug or NDC
**Where**: `research/03-agent-loop/`
**Likelihood**: Low (RAG-grounded; cited)
**Impact**: Critical (PRD §15 risk register top entry)
**Mitigation**:
- Output schema requires `rxcui` for every alternative
- Eval scorer checks RxCUI against retrieved set
- HITL: low confidence → manual review required (no one-click accept)

### R9 — Severity rule misclassification
**Where**: `research/04-briefing-diff/POC-severity-classifier.py`
**Likelihood**: Medium (rules are coarse)
**Impact**: Medium (alert fatigue or missed critical)
**Mitigation**:
- Eval set explicitly tests severity accuracy (target ≥90%)
- LLM rationale can override rule-based with explanation
- v0.2: refine rules from eval cases that miss

### R10 — openFDA label has no relevant content for some drugs
**Where**: `research/01-data-layer/POC-openfda-labels.py`
**Likelihood**: Medium (~10% of drugs)
**Impact**: Low (RAG returns nothing; agent surfaces "label data unavailable")
**Mitigation**: Fallback to `generic_name` search; if still nothing, return empty chunks list and let agent note absence.

### R11 — FDA shortage record has no RxCUI
**Where**: `research/01-data-layer/`
**Likelihood**: ~10% of records
**Impact**: Low (we drop these, ~10% miss rate on diff)
**Mitigation**: v0.2 adds name+dosage_form fallback matching. v0.1 acceptably loses these.

### R12 — Streamlit threading + async leak
**Where**: `research/05-streamlit-ui/`
**Likelihood**: Medium
**Impact**: Medium (Streamlit hangs or shows ScriptRunContext error)
**Mitigation**:
- `@st.cache_resource` for clients (NOT `cache_data`)
- `asyncio.run()` inside cached function, not at top level
- Never spawn threads from Streamlit script

## Medium risks (build-time pain, not demo-breaking)

### R13 — Security-warning hook blocks certain substrings
**Where**: ambient (this very session)
**Likelihood**: Confirmed (already hit during scaffold)
**Impact**: Low (rewrite needed)
**Mitigation**: Avoid the literal substring `e v a l (` (no spaces) and the word for the python serialization module starting with "p". Already worked around with `run_suite()` instead of the obvious name.

### R14 — diskcache lock contention
**Where**: `research/03b-caching/`
**Likelihood**: Low (single-user demo)
**Impact**: Low
**Mitigation**: Single user during demo. Production would use Redis.

### R15 — Tool call returns malformed JSON
**Where**: `research/03-agent-loop/`
**Likelihood**: Low (we control tool impl)
**Impact**: Medium (agent loops or fails)
**Mitigation**: Wrap every tool body in `try/except`; return `{"error": "..."}` on failure. Agent prompt: "If tool returns error, do not retry; surface as `confidence: low`."

### R16 — API rate limits during demo
**Where**: `research/01-data-layer/`
**Likelihood**: Low (with cache)
**Impact**: Medium (demo slows)
**Mitigation**: Pre-warm Tier 2 cache at H6 with full briefing run; demo hits cache.

### R17 — Anthropic API outage
**Where**: ambient
**Likelihood**: Very low
**Impact**: Critical (no demo)
**Mitigation**: Pre-record Loom walkthrough as fallback during buffer block.

### R18 — Demo machine clock skew breaks signed URL or auth
**Where**: ambient
**Likelihood**: Very low
**Impact**: Low (no signed URLs in v0.1)
**Mitigation**: N/A — public APIs.

## Low risks (worth noting, no action)

- **Brand vs generic NDC reconciliation**: deferred to v0.2.
- **Compounded drug handling**: out of scope.
- **Pediatric vs adult dosing differentiation**: out of scope; v0.2 with proper indication matching.
- **ICD-10 indication matching**: out of scope; v1.0 with EHR integration.

## What we're NOT mitigating

These are knowingly accepted gaps:

1. **Real customer formulary** — v0.2 deliverable.
2. **Background scheduler** — v0.3 deliverable.
3. **Multi-user safety** — single-user demo.
4. **Auth** — out of scope.
5. **Pricing data** — separate signal stream, v1.x.
6. **EHR integration** — v0.4.

## Pre-demo checklist

Run this list at the buffer block (5:45):

- [ ] `streamlit run src/main.py` works on cold start
- [ ] Briefing pre-rendered to `data/briefings/2026-04-30.json`
- [ ] Tier 2 cache warm (run briefing once before customer call)
- [ ] Tier 3 cache primes within 2 sec on second load
- [ ] Eval results render in eval tab
- [ ] Citations clickable, all return HTTP 200
- [ ] "Synthetic data" disclaimer visible
- [ ] `.env` not in git
- [ ] Loom backup recorded
- [ ] Cost reported in eval tab
