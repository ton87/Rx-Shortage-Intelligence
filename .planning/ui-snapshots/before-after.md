# UI before/after — verify pass

Baseline: `01-briefing-top.png`, `02-briefing-full.png`, `03-briefing-expanded.png`, `04-sidebar-open.png`, `05-eval-tab.png`
After:    `after-01-briefing.png` … `after-09-override-flow.png`

## P0 fixes verified

| # | Issue | Before | After |
|---|-------|--------|-------|
| 1 | No theme tokens — default Streamlit | `01` plain default | `after-02` clinical neutral palette, sans-serif system stack |
| 2 | Citations hidden in expander | `02` no citation visible | `after-02` `Source: FDA shortage record` link inline on collapsed card |
| 3 | HITL buttons inside expander | `03` had to expand to act | `after-02` Accept/Override/Escalate on collapsed card |
| 4 | Override logged bare string | n/a | `after-09` Override → text area required → Confirm logs reason |
| 5 | Severity emoji-only signal | `🔴 CRITICAL` | `after-02` red `CRITICAL` text badge + red card left-border |
| 6 | Confidence emoji-only signal | `🟡 medium` | `after-02` yellow `MED` pill |
| 7 | Misleading green-up deltas | `05` green ↑ on hallucination | `after-05` deltas hidden via CSS, static target line below |
| 8 | `Latency: 0s` reads broken | `01` shows `0s` | `after-02` shows `—` |
| 9 | Nested expanders unreliable | `03` inner expander broken | drill-down uses `st.toggle` for audit trail |
| 10 | Eval dataframe not rendering | `05` blank/broken | `after-05` 15 rows render correctly |

## P1 fixes verified

- Top-level tabs replace sidebar nav (no chevron-click required) → `after-02` shows `Briefing | Formulary | Eval`
- Date header `Morning Briefing — May 01, 2026 · 08:00 UTC`
- Synthetic banner replaced with neutral `[DEMO]` chip + amber border (no `st.warning` alarm)
- Recommended action promoted from `caption` to bold `Action:` prefix
- Alternatives table: Rank | Drug | Confidence | RxCUI | Rationale (was prose blob)
- Empty/error states copy fixed
- "Tool call trace" → "Audit trail (N API calls)"
- "Agent reasoning + citations" → "Details + citations"
- Streamlit primaryColor = `#1D4ED8` (action blue) — Accept button + tab indicator no longer red

## Formulary tab (NEW)

`after-04-formulary-fixed.png`:
- Title + sub-caption ("Memorial Health System · 30 drugs · Cross-referenced against today's FDA shortage feed")
- 3 metric cards: Total formulary 30 · Affected today 1 · Critical 0
- 3 multiselect filters: Route · Formulary status · Shortage status
- Sortable dataframe: Drug | Route | Status | Restriction | Orders (30d) | Shortage today | RxCUI
- Default sort: Watch first (Methotrexate), then alphabetical
- Row select → inline drill-down (formulary record + operational context, two columns) — bounds-checked

Cross-ref engine: rxcui-list match + drug-name token fallback (necessary because briefing rxcui = openFDA concept level; formulary rxcui = RxNorm canonical level). Verified Methotrexate cross-ref hit.

## Bugs surfaced + fixed during verify

- Empty filtered dataframe + stale row selection raised `IndexError` on iloc. Added `selected_rows[0] < len(filtered)` bounds check.

## Out of scope this round (P2 — v0.2)

- Customer ID display name map
- RxClass therapeutic_class backfill
- Post-briefing completion state
- RxCUI tooltip/copy affordance
- Skeleton-loader Streamlit polyfill
