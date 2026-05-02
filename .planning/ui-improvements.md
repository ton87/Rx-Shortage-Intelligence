# UI Improvements — synthesized punch list

Merged from `ui-review-frontend.md` (design lens) + `ui-review-uxpm.md` (UX/clinical-flow lens). Both agents independently flagged the same 6 P0s — strong signal.

Auto-action policy: P0 + P1 implemented this round. P2 deferred to v0.2.

---

## Group 1 — Theme + tokens (foundational, do first)

**G1.1 [P0]** No custom CSS injected. Currently indistinguishable from default Streamlit app. PRD demands clinical-professional reduced palette + sans-serif system stack + monospace for codes.
→ Inject `<style>` block with design tokens (palette, type scale, spacing, badge/pill specs from frontend audit).

**G1.2 [P0]** Page favicon `page_icon="💊"` and H1 `"💊 Rx Shortage Intelligence"`.
→ `page_icon=None` (or `:material/medication:`). Plain text title.

---

## Group 2 — AI tells removal (mandatory PRD §10.3 compliance)

**G2.1 [P0]** Severity color emoji as sole signal: `🔴🟡🟢⚪`. Fails WCAG 1.4.1.
→ CSS-styled text badges (CRITICAL / WATCH / RESOLVED) with severity color + card left-border.

**G2.2 [P0]** Confidence emoji: `🟢🟡🔴⚪`.
→ Text pills (HIGH / MED / LOW) with background fill.

**G2.3 [P0]** Re-run button `"🔄 Re-run briefing"`, eval title `"📊 Eval"`, accept `"✓"`, override `"✎"`, escalate `"⚠"`.
→ Plain text buttons + titles. Drop emojis. (Keep `⚠` on Escalate per UX agent — clinical established meaning. Drop pencil + checkmark — keep functional checkmark optional. Final call: drop ALL for consistency.)

**G2.4 [P1]** Synthetic banner emoji `⚠️`.
→ Drop emoji. Banner becomes neutral `[DEMO]` chip with amber left-border, white background. Use `st.info`-style block with custom CSS (NOT `st.warning` — wrong semantic).

**G2.5 [P1]** Copy tells: `"Agent reasoning + citations"`, `"Tool call trace"`.
→ Rename → `"Details + citations"`, `"Audit trail"`.

---

## Group 3 — Stats bar (top of page)

**G3.1 [P0]** `st.metric` delta strings render targets as green up-arrows. Misleading on hallucination metric especially.
→ Drop `delta=` entirely. Show targets as static caption row below metrics.

**G3.2 [P0]** `Latency: 0s` / `Tokens used: 0` reads as broken when cached briefing has zero in those fields.
→ Render `—` when value is 0 or missing.

**G3.3 [P1]** Severity metric labels still emoji.
→ Plain text + colored value via CSS class.

**G3.4 [P1]** Run timestamp ISO 8601 `2026-05-01T08:00:00Z` not human-scannable.
→ Format `May 1, 2026 · 08:00 UTC`.

**G3.5 [P2]** Customer ID `memorial-health-450` raw.
→ Display name `Memorial Health System` (deferred — needs lookup map; v0.2).

**G3.6 [P2]** "Tokens used" is engineering debug.
→ Move to expandable Run details / drop. (Action: drop from main stats, keep in audit trail.)

---

## Group 4 — Synthetic data banner

**G4.1 [P1]** `st.warning` semantic wrong (alarm not info).
→ Replace with custom HTML banner: amber left-border, neutral bg, small `[DEMO]` chip, no emoji.

**G4.2 [P2]** Copy includes "v0.1 demo" — internal versioning leaks.
→ Drop version. Keep "FDA shortage feed and RxNorm are live public data."

---

## Group 5 — Briefing item card

**G5.1 [P0]** Citations hidden in expander (PRD §10.3 violation).
→ Render primary citation `[FDA source]` link in collapsed card, below summary.

**G5.2 [P0]** HITL action buttons inside expander.
→ Move Accept/Override/Escalate to compact action row in collapsed card. Keep expander for rationale + alts + tool trace.

**G5.3 [P0]** Override records bare `"override"` string. Audit-indefensible.
→ When Override clicked, reveal `st.text_area("Override reason — required")` + Confirm button. Reason logged with timestamp.

**G5.4 [P0]** Severity emoji-only signal (G2.1) + cards visually identical regardless of severity.
→ Card left-border 4px in severity color. Severity text badge top-left.

**G5.5 [P1]** Confidence visually equal weight to severity in collapsed card.
→ Subordinate confidence: smaller pill, top-right, not bold.

**G5.6 [P1]** Recommended action in `st.caption` (lowest contrast).
→ `st.markdown` with `font-weight: 500`, prefix `Action:`.

**G5.7 [P1]** `st.success("✓ accept")` post-action shows raw string.
→ Map: `accept → Accepted`, `override → Overridden`, `escalate → Escalated to P&T`. Render as inline text badge, not `st.success` box.

---

## Group 6 — Drill-down (expander contents)

**G6.1 [P0]** Nested expander for tool trace — Streamlit doesn't support reliably.
→ Replace inner expander with `st.toggle("Show audit trail")` + conditional render.

**G6.2 [P1]** Alternatives list dense prose: `**Carboplatin** (RxCUI \`40048\`) 🟡 \`medium\` — ...`.
→ Compact tabular layout: Name | Confidence | Route | Rationale. RxCUI moves to small caption beneath name.

**G6.3 [P1]** Alternatives have no rank / preference indicator.
→ Prefix first as `Preferred:`, others as `Alternative:`.

---

## Group 7 — Eval tab

**G7.1 [P0]** `st.dataframe(rows)` not rendering — case results table missing, briefing items bleed through.
→ Cast to `pd.DataFrame(rows)` explicit + add `else: st.caption("No case results yet.")` fallback. Wrap whole tab in `st.container()` with explicit `st.empty()` to flush stale state.

**G7.2 [P0]** Misleading green deltas on metrics (G3.1 same fix here).

**G7.3 [P1]** No orientation framing.
→ Sub-caption: "Internal quality scoring — for pharmacy operations review, not clinical use."

**G7.4 [P2]** Subheader has no legend for `✓` / `✗` columns.
→ Add caption legend.

---

## Group 8 — Empty + loading states

**G8.1 [P1]** Spinner for 30-60s re-run = bad UX.
→ `st.status("Running briefing...", expanded=True)` with phase markers ("Fetching FDA shortage data... ✓", "Resolving RxNorm... ✓", "Generating briefing..."). Streams visible progress.

**G8.2 [P1]** No-briefing empty state copy positions tool as not ready.
→ "No briefing for today yet. Click Re-run briefing to fetch the latest FDA shortage data — takes about 45 seconds."

**G8.3 [P1]** Zero-items uses "may" = uncertainty.
→ "No formulary drugs affected by current FDA shortages as of [timestamp]."

---

## Group 9 — Sidebar / nav

**G9.1 [P1]** `initial_sidebar_state="collapsed"` hides Eval nav on first paint.
→ Switch to `st.tabs(["Briefing", "Formulary", "Eval"])` at top level. Always visible. (Note: per UX agent, Formulary as 3rd tab risks multi-tab hierarchy violation. Resolution: tabs are NOT a sidebar hierarchy — top-level tabs are PRD-allowed since they're a single horizontal scan, not nested navigation. Briefing remains default. Formulary is reference-only, briefing-first preserved.)

---

## Group 10 — Formulary visualization (NEW capability)

User explicitly requested. Three views, top-level tab placement (per G9.1 resolution).

**G10.1 [P1]** **View 1 — Browse + filter**
- 30-drug `st.dataframe` with columns: Drug | Class | Route | Status | Shortage Today
- Three `st.multiselect` filter widgets above: Class, Route, Status
- Status = preferred/restricted/non-preferred/non-formulary, colored text
- Shortage Today = cross-ref against latest briefing items
- Sort: Shortage status desc, then alphabetical

**G10.2 [P1]** **View 2 — Overlap with shortages**
- Status matrix (NOT heatmap per UX agent rationale — too few data points)
- Two-col: "Affected drugs today" (severity-badged) | "Clear drugs" (count summary)
- Above the matrix: 3 metric cards (Total formulary, Affected today, Clear)

**G10.3 [P1]** **View 3 — Single-drug drill-down**
- Triggered by row click in View 1 (`st.dataframe` selection mode `on_select="rerun"`)
- Two-column inline panel: formulary record (left) | operational context (right)
- "Back to formulary" button restores View 1
- Cross-links from briefing items: "View in formulary" → preselect rxcui in session state

**G10.4 [P2]** therapeutic_class is "TBD" in synthetic data
→ Backfill via RxClass server (deferred — out of scope this round).

---

## Action plan (auto-action this session)

### Implementation order

1. **Theme injection** (G1) — design tokens CSS block. Foundation for everything else.
2. **Helpers** — `severity_badge(s)`, `confidence_pill(c)`, `format_timestamp(iso)`, `display_metric(label, val, target)`. Pure functions, easy to test.
3. **Strip emoji + rename labels** (G2) — mass find/replace.
4. **Stats bar** (G3) — drop deltas, fix zero rendering, format timestamp.
5. **Synthetic banner** (G4) — custom HTML inline banner.
6. **Briefing item card** (G5) — restructure: badge + summary + citation + action row in collapsed; expander for details.
7. **Drill-down** (G6) — flatten nested expander, tabulate alternatives.
8. **Eval tab** (G7) — explicit empty fallback, drop deltas, add framing.
9. **Empty/loading states** (G8) — `st.status` streaming, copy fixes.
10. **Top-level tabs** (G9) — replace sidebar radio.
11. **Formulary tab** (G10) — three views.

### What stays as code structure

- `src/main.py` keeps single-file structure (PRD architecture).
- All theme tokens injected via `st.markdown("<style>", unsafe_allow_html=True)` at top.
- Helpers stay inline (no new modules — v0.1 single-file constraint).

### Out of scope this round

- G3.5 (display name map) — no lookup data, defer.
- G10.4 (therapeutic_class backfill) — needs RxClass tool wiring, defer.
- Animation / skeletons (PRD prefers, but Streamlit skeletons not first-class — `st.status` streaming is closest acceptable substitute, already in plan).
