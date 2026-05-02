# Rx Shortage Intelligence — Restructure Design

**Date**: 2026-05-01
**Author**: brainstorming session
**Status**: approved, ready for implementation plan

## Goal

Cut AI-slop from `src/main.py` (958 LOC, 30 funcs) and `src/briefing.py` (821 LOC, 13 funcs + 250 LOC of inline prompts). Replace fat files with layered modules. Eliminate magic numbers. Preserve all behavior, JSON shapes, CLI commands, and lock file paths.

## Non-goals

- No new features.
- No behavior changes.
- No touching `src/servers/*`, `src/cache.py`, `src/mcp_bridge.py`, `src/eval/runner.py`.
- No restructure of agent loop logic itself (only relocation).

## Architecture — layered

Four layers, strict dependency direction (`ui` → `domain`/`io`/`agent`; `domain` → nothing; `io` → `domain`; `agent` → `domain`):

```
src/
  main.py                   ~40 LOC: render_theme(), tabs, dispatch
  briefing.py               ~30 LOC: CLI entry → calls agent + store

  ui/
    theme.css               extracted as-is from THEME_CSS literal
    theme.py                load + inject css (st.markdown w/ unsafe_allow_html)
    components.py           severity_badge, confidence_pill, card, banner, citation_link
    formatters.py           format_timestamp, format_int_or_dash, format_latency_or_dash
    briefing_view.py        render_briefing_tab + collapsed_card + action_row + drilldown
    formulary_view.py       render_formulary_tab + drug_drilldown
    eval_view.py            render_eval_tab
    actions.py              log_action (HITL persistence)
    runner.py               run_briefing_cli, run_briefing_with_status, lock helpers

  domain/                   pure functions, zero I/O, zero streamlit
    severity.py             class Severity(StrEnum); SEVERITY_RANK
    confidence.py           class Confidence(StrEnum); pill labels
    fda.py                  class FDAStatus(StrEnum) — Current/TBD/Resolved
    diff.py                 compute_diff, _status_rank, _idx
    indexing.py             index_formulary, index_orders
    matching.py             normalize_drug_name, find_shortage_match, build_shortage_index
    constants.py            DEFAULT_CANDIDATE_CAP, FDA_FETCH_LIMIT, BRIEFING_TIMEOUT_S, LOCK_STALE_S

  agent/                    no streamlit
    loop.py                 (was src/agent.py) run_agent, MAX_ITERATIONS
    prompts.py              load_prompt(name), build_system_blocks, build_user_message, parse_briefing_item
    prompts/
      role_and_rules.md
      severity_rubric.md
      examples.md
      output_schema.md

  io/                       filesystem only
    briefing_store.py       load_briefing, find_latest_briefing, write_briefing, list_briefings
    data_loader.py          (moved from src/data_loader.py)

  servers/                  unchanged
  eval/runner.py            unchanged
  cache.py                  unchanged
  mcp_bridge.py             unchanged
```

### Dependency rules

- `domain/` imports from stdlib only.
- `io/` imports from stdlib + `domain/`.
- `agent/` imports from stdlib + `domain/` + anthropic SDK + `mcp_bridge`.
- `ui/` imports from streamlit + `domain/` + `io/`. Never `agent/` directly.
- `main.py` only wires `ui/` tabs.
- `briefing.py` (CLI) only wires `agent/` + `io/` + `mcp_bridge`.
- `subprocess` calls live in `ui/runner.py` exclusively.

## Constants + enums (Q4: B+C)

Per-module placement, type-safe enums:

- `domain/severity.py`:
  ```python
  class Severity(StrEnum):
      CRITICAL = "Critical"
      WATCH = "Watch"
      RESOLVED = "Resolved"

  SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.WATCH: 1, Severity.RESOLVED: 2}
  ```
- `domain/confidence.py`:
  ```python
  class Confidence(StrEnum):
      HIGH = "high"
      MEDIUM = "medium"
      LOW = "low"

  CONFIDENCE_LABELS = {Confidence.HIGH: "HIGH", Confidence.MEDIUM: "MED", Confidence.LOW: "LOW"}
  ```
- `domain/fda.py`:
  ```python
  class FDAStatus(StrEnum):
      CURRENT = "Current"
      TBD = "To Be Discontinued"
      RESOLVED = "Resolved"
  ```
- `domain/constants.py`:
  ```python
  DEFAULT_CANDIDATE_CAP = 5
  FDA_FETCH_LIMIT = 100
  BRIEFING_TIMEOUT_S = 600
  LOCK_STALE_S = 900
  ```

JSON serialization: enums must round-trip as their string values (`"Critical"` etc.). Existing `data/briefings/*.json` files load unchanged.

## CSS handling (Q5: A+C)

- `src/ui/theme.css` — verbatim copy of current `THEME_CSS` body (no `<style>` tags in file; tags wrap when injected).
- `src/ui/theme.py`:
  ```python
  CSS_PATH = Path(__file__).parent / "theme.css"

  @st.cache_resource
  def _load_css() -> str:
      return CSS_PATH.read_text()

  def render_theme() -> None:
      st.markdown(f"<style>{_load_css()}</style>", unsafe_allow_html=True)
  ```
- `src/ui/components.py` — small HTML emitters, only know class names from CSS:
  - `severity_badge(severity: Severity) -> str`
  - `confidence_pill(conf: Confidence) -> str`
  - `card(severity, body_html) -> str`
  - `demo_banner() -> str`
  - `citation_link(url, text) -> str`
  - `status_chip(status: str) -> str`

## Agent prompts (Q6: B/C)

Static text → markdown files in `src/agent/prompts/`. Loader:

```python
PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()
```

Files:
- `role_and_rules.md` — current ROLE_AND_RULES block from `_system_blocks()`
- `severity_rubric.md` — severity rules + cut-line table from briefing.py:163-285
- `examples.md` — few-shot examples from briefing.py:240-285
- `output_schema.md` — JSON output schema description

`build_system_blocks()` composes loaded text into Anthropic cache-eligible blocks. Snapshot test asserts byte-equality with current literal at migration commit (R2 mitigation).

## Data flow

```
CLI: python -m src.briefing
  briefing.py
    → io.data_loader (formulary, orders, yesterday)
    → domain.indexing (build idx)
    → mcp_bridge → fetch FDA
    → domain.diff (compute_diff)
    → agent.loop.run_agent(prompts.build_system_blocks, prompts.build_user_message)
    → agent.prompts.parse_briefing_item
    → io.briefing_store.write_briefing → data/briefings/YYYY-MM-DD.json

UI: streamlit run src/main.py
  main.py
    → ui.theme.render_theme()
    → tabs:
        ui.briefing_view ── io.briefing_store.find_latest_briefing → load_briefing
                          ── ui.actions.log_action (HITL)
                          ── ui.runner.run_briefing_with_status (Re-run button)
        ui.formulary_view ── io.data_loader.load_formulary
                           ── domain.matching.build_shortage_index, find_shortage_match
        ui.eval_view ── reads data/eval_results.json
```

## Migration order

Each step ends with `pytest` green and a commit. No step proceeds until predecessor green.

1. Verify baseline test status (R3 — `test_h5_ui_helpers.py` already imports nonexistent symbols). Document which tests currently pass; restoration is part of step 6.
2. Extract constants + StrEnums → `domain/{severity,confidence,fda,constants}.py`. Update call sites.
3. Extract pure logic → `domain/{diff,indexing,matching}.py`.
4. Extract io layer → `io/briefing_store.py`; move `data_loader.py` → `io/data_loader.py`.
5. Extract agent layer → `agent/loop.py` (move `src/agent.py`), `agent/prompts.py` + `agent/prompts/*.md`. Snapshot test for prompt byte-equality.
6. Extract ui layer → `ui/{theme.css, theme.py, components.py, formatters.py, actions.py, runner.py, briefing_view.py, formulary_view.py, eval_view.py}`. Shrink `main.py` to dispatcher.
7. Update tests for new import paths; fix already-drifted imports in `test_h5_ui_helpers.py`. Add smoke tests: `test_domain_severity.py`, `test_domain_matching.py`, `test_ui_components.py`.
8. End-to-end verification: pytest full, `python -m src.briefing` with synthetic data, `streamlit run src/main.py` manual check (briefing tab loads, formulary cross-ref renders, eval renders).

## Test mapping

| Old test | New imports |
|----------|-------------|
| `test_h3_h4_briefing.py` | `domain.diff.compute_diff`, `domain.indexing.{index_formulary, index_orders}`, `agent.prompts.{build_user_message, parse_briefing_item}`, `agent.loop.{run_agent, MAX_ITERATIONS}` |
| `test_h5_ui_helpers.py` | Fix: `io.briefing_store.{find_latest_briefing, load_briefing}`, `ui.actions.log_action`, `domain.severity.SEVERITY_RANK` (replace nonexistent `SORT_ORDER`). Drop streamlit monkey-patch. |
| `test_data_layer.py` | `io.data_loader.*` |
| `test_h2_*` | unchanged |
| `test_h6_eval.py` | unchanged |

New smoke tests (≤5 LOC each):
- `tests/test_domain_severity.py` — enum values match expected strings; ranks correct
- `tests/test_domain_matching.py` — normalize, build_index, find_match basics
- `tests/test_ui_components.py` — pure HTML output snippets escape correctly

## Behavior preservation guarantees

- Severity enum string values match current literals (`"Critical"`, `"Watch"`, `"Resolved"`).
- Briefing JSON schema unchanged (eval runner + UI both depend on shape).
- Existing `data/briefings/*.json` load without migration.
- Lock path unchanged: `/tmp/rx_briefing.lock`.
- CLI invocation unchanged: `python -m src.briefing`.
- UI invocation unchanged: `streamlit run src/main.py`.
- All current public symbols re-importable at their new paths (tests update imports, don't shim).
- Agent prompt cache key unchanged via prompt byte-equality snapshot test.

## Risks

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | CSS file re-read every rerun | `@st.cache_resource` on loader; accept ~1ms cost otherwise |
| R2 | Markdown prompts drift from Python literals → cache invalidation | Snapshot test compares loaded markdown to current literal at migration commit |
| R3 | Tests already drifted (`test_h5_ui_helpers.py` imports nonexistent symbols), suggesting CI may not run them | Step 1: document baseline test status before changes; restore as part of step 7 |
| R4 | Subprocess CLI command path embeds module path string | `cmd = f"{sys.executable} -u -m src.briefing ..."` — module path unchanged, no risk |
| R5 | Streamlit `@st.cache_data` decorators on `load_formulary`/`load_orders_index` move with the functions | Re-decorate in `io/` modules; ui layer wraps if needed |

## Out of scope (deferred)

- Splitting `src/data_loader.py` (389 LOC) further — it's a one-shot bootstrap script.
- Tier-3 caching (per CLAUDE.md, deferred to v0.2).
- Breaking up MCP servers.
- Eval runner rewrite.
- New features.
