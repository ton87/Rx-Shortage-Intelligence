# Streamlit UI — Lesson

## Anchor: PRD §10

The UI is the trust UX. Every documented competitor weakness is a deliberate inversion in our design (PRD §10.4).

| Legacy weakness | Our inversion |
|----------------|---------------|
| Multi-tab hierarchies | Single-screen scannable dashboard |
| Search-first | Briefing-first (no search) |
| Show-everything | Show only what affects this hospital |
| Feature-first nav | Outcome-first surface |
| Modal stacks | Inline expansion (max 1 click to source) |
| Conversational chatbot | Structured briefing — pharmacist scans, doesn't type |

## FR mapping

| FR | UI manifestation |
|----|------------------|
| FR-8 | Day-one usable: dashboard already populated on first load; empty state explains itself |
| FR-9 | Speed: <2s dashboard, <1s drill-down, <30s rerun — `@st.cache_data` does the heavy lift |
| FR-10 | Information density: scan order matters more than padding; one-sentence summaries |
| FR-11 | Visual scan order: top stats → severity-ordered list → expandable detail |

## Three pages, three responsibilities

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER   |   2026-04-30  |  Last run: 08:00 | [Re-run]     │
├─────────────────────────────────────────────────────────────┤
│  STATS:   ●● 2 Critical   ●● 3 Watch   ●● 1 Resolved        │
├─────────────────────────────────────────────────────────────┤
│  ● CRITICAL   Cisplatin                          [▼ expand] │
│              23 Oncology orders, no formulary alt           │
│              → Switch new orders to carboplatin pending P&T │
│              [Citations: 2]  [Confidence: high]             │
├─────────────────────────────────────────────────────────────┤
│  ● WATCH      Methotrexate                       [▼ expand] │
│              ...                                            │
└─────────────────────────────────────────────────────────────┘
```

Pages (Streamlit `pages/` dir or sidebar nav):
1. **Briefing** (default) — the dashboard above
2. **Drill-down** — agent reasoning trace (inline expansion, not separate page actually; see below)
3. **Eval** — admin-only, 15-case grid

Drill-down = inline expansion via `st.expander`, not a separate page. PRD §10.4: max 1 click to source.

## Implementation skeleton

```python
import streamlit as st
import json
from pathlib import Path

st.set_page_config(page_title="Rx Shortage Intelligence", layout="wide")

@st.cache_data(ttl=3600)
def load_briefing(date_iso: str) -> dict:
    path = Path(f"data/briefings/{date_iso}.json")
    return json.loads(path.read_text()) if path.exists() else None

def render_severity_badge(severity: str) -> str:
    colors = {"Critical": "🔴", "Watch": "🟡", "Resolved": "🟢"}
    return f"{colors.get(severity, '⚪')} **{severity.upper()}**"

briefing = load_briefing("2026-04-30")

# Header
col1, col2, col3 = st.columns([2, 1, 1])
col1.title("Rx Shortage Intelligence")
col2.markdown(f"**{briefing['run_timestamp']}**")
if col3.button("Re-run", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Stats
counts = {"Critical": 0, "Watch": 0, "Resolved": 0}
for it in briefing["items"]:
    counts[it["severity"]] += 1

s1, s2, s3, s4 = st.columns(4)
s1.metric("🔴 Critical", counts["Critical"])
s2.metric("🟡 Watch", counts["Watch"])
s3.metric("🟢 Resolved", counts["Resolved"])
s4.metric("Total tokens", briefing["total_tokens_used"])

# Severity-ordered items
order = {"Critical": 0, "Watch": 1, "Resolved": 2}
for item in sorted(briefing["items"], key=lambda x: order[x["severity"]]):
    with st.container(border=True):
        col_a, col_b = st.columns([3, 1])
        col_a.markdown(f"{render_severity_badge(item['severity'])} **{item['drug_name']}**")
        col_a.write(item["summary"])
        col_a.caption(f"→ {item['recommended_action']}")
        col_b.write(f"Confidence: {item['confidence']}")

        with st.expander("Show agent reasoning + citations"):
            st.markdown("**Rationale**")
            st.write(item["rationale"])
            st.markdown("**Alternatives**")
            for alt in item["alternatives"]:
                st.write(f"- {alt['name']} (RxCUI {alt['rxcui']}) — {alt['rationale']}")
                st.caption(f"[Source]({alt['source_url']})")
            st.markdown("**Citations**")
            for c in item["citations"]:
                st.markdown(f"- {c['claim']} — [source]({c['source_url']})")

            ac1, ac2, ac3 = st.columns(3)
            if ac1.button("✓ Accept", key=f"accept-{item['item_id']}"):
                _log_action(item["item_id"], "accept")
            if ac2.button("✎ Override", key=f"override-{item['item_id']}"):
                _log_action(item["item_id"], "override")
            if ac3.button("⚠ Escalate", key=f"escalate-{item['item_id']}"):
                _log_action(item["item_id"], "escalate")

# Synthetic data disclaimer (Principle 7, NFR-5)
st.caption("⚠ Synthetic formulary and active orders for v0.1 demo only. FDA + RxNorm data is live.")
```

## Re-run with streaming tool calls

`st.status` container streams updates while agent runs:

```python
with st.status("Running briefing...", expanded=True) as status:
    for tool_call in agent_run_iter(...):
        status.write(f"  → {tool_call['server']}.{tool_call['tool']}({tool_call['args']})")
    status.update(label="Briefing complete", state="complete")
```

Visible tool calls = part of the trust UX (PRD §10.3 "transparency itself is part of the trust UX").

## Eval tab

```
┌─────────────────────────────────────────────────────────────┐
│  EVAL — 15 cases × 5 dimensions                             │
├─────────────────────────────────────────────────────────────┤
│  Case ID | Input drug      | Severity (exp/act) | Hallucin? │
│  C-01    | cisplatin       | Crit / Crit ✓     | 0%        │
│  C-02    | methotrexate    | Crit / Watch ✗    | 0%        │
│  ...                                                        │
├─────────────────────────────────────────────────────────────┤
│  Aggregate: Clin appropriateness 87% | Citation acc 100%    │
│             Hallucination 0% | Severity acc 80%             │
│             Recall 100% | v1 vs v2: not run                 │
└─────────────────────────────────────────────────────────────┘
```

Implement as `st.dataframe` with conditional formatting on pass/fail.

## Streamlit gotchas

1. **`st.cache_data` returns same Python object across reruns** — don't mutate it. Treat as immutable.
2. **Async in Streamlit** — use `asyncio.run(coro)` inside `@st.cache_resource`. Don't use `st.experimental_async_*` (deprecated).
3. **Session state vs cache** — session_state for user input (which row clicked), cache for data.
4. **Reruns happen on every interaction** — top-level code runs every time. Put expensive work in cached functions.
5. **`st.button` returns `True` only once** — on the click rerun. State must persist via session_state if needed.
6. **Wide layout** is essential for power-user density: `st.set_page_config(layout="wide")`.
7. **No tab nav unless required** — PRD §10.4 inverts multi-tab. Use `st.sidebar` for admin-only pages (eval).

## Anti-patterns to avoid

- ❌ Modals (`st.modal` exists, don't use it for primary content)
- ❌ Bouncy animations
- ❌ Spinners — use `st.skeleton` or `st.status`
- ❌ Fake AI sparkles, gradients, rainbow colors
- ❌ Open-ended chat input as the main interface
- ❌ Multiple severity colors mixed (red/amber/green only)
- ❌ Hidden citations (must be visible by default per §10.3)
