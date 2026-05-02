# UX/Workflow Audit — Rx Shortage Intelligence

## Verdict

The dashboard serves Marcus Patel's primary triage task adequately for a v0.1 prototype — the severity-ordered card list, one-sentence summaries, and recommended actions are the right structure. However, three issues prevent day-one trust for Karen Chen: citations are hidden behind an expander (violating PRD's explicit "citation-first, visible by default" requirement), the Override button logs a bare action string with no override text input (clinically unsafe — there is no record of what the pharmacist actually decided instead), and the page is visually noisy with emoji used as both functional severity indicators and decorative chrome, which the PRD explicitly forbids. The formulary visualization capability does not yet exist. Fixing the P0 items brings this to a shippable demo state; the P1 items are pre-customer-demo polish.

---

## Primary flow walkthrough (Flow 1 simulation)

Marcus opens the dashboard at 7:00 AM.

**Step 1 — First paint (0-3s).** The title renders with a pill emoji and the briefing card list appears. The stats bar shows "Critical: 1, Watch: 1, Resolved: 0." This is correct. Time to orient: under 5 seconds. No friction here.

**Step 2 — Identify the critical item (<30s target).** The first card reads "CRITICAL — Cisplatin" in bold with a red circle emoji. The one-sentence summary and recommended action are immediately visible. Target met. However, Marcus notices "Latency: 0s / Tokens used: 0" in the stats bar — this looks broken even though it isn't (the cached JSON has 0 in those fields). His trust ticks down slightly.

**Step 3 — Assess confidence without drilling.** The confidence badge (`medium`) is visible in the collapsed card top-right. Good. But Marcus cannot see any citation in the collapsed view, so he cannot verify the claim "currently in FDA shortage" without clicking. PRD says citations visible by default. He must expand.

**Step 4 — Drill to citation (1-click target).** Marcus clicks "Agent reasoning + citations." The expander opens. Citations appear as a bullet: "Cisplatin currently in FDA shortage — [source]." One click, link visible. The click target is the full-width expander bar, easy to hit. Flow 2 target is met structurally, but the expander label "Agent reasoning + citations" is jargon-heavy for a clinical pharmacist — Marcus cares about the citation, not the "agent reasoning" label.

**Step 5 — Review the alternative.** Carboplatin is listed with RxCUI `40048`, confidence `medium`, route match confirmed. Rationale is one sentence. Scannable. However, the RxCUI code renders as inline monospace text directly next to the drug name with no label — Marcus sees "Carboplatin (RxCUI 40048)" and may not know what to do with that number. It is audit metadata, not clinical scan content.

**Step 6 — Accept the recommendation.** The Accept/Override/Escalate buttons are inside the expander — Marcus must have the drill-down open to act. This is an extra cognitive step. More critically, clicking "Override" logs the string `"override"` to the JSON with no free-text field for what the override decision actually is (`main.py` line 138). This is a clinical safety gap: an audit log that says only "override" with no reason is not defensible to P&T.

**Step 7 — Move to Watch item.** Marcus collapses Cisplatin and scans Methotrexate. Same flow. Total elapsed: under 3 minutes for 2 items. PRD target met.

**Step 8 — Close.** No confirmation, no "briefing complete" state. The page just sits with two cards showing action badges. No signal that Marcus's work session is finished.

---

## Findings — grouped by section

### First-paint / above-the-fold

- **[P1]** Pill emoji in H1 title and as page_icon (`main.py` line 21, 209). PRD explicitly bans "AI sparkle" iconography. Fix: remove emoji from title and page_icon.
- **[P1]** No date context on the page. Fix: render `st.subheader(f"Morning Briefing — {date_label}")` under page title.
- **[P2]** "Customer: memorial-health-450" raw system ID rendered in caption (line 258). Fix: use display name or omit.

### Stats bar / summary metrics

- **[P0]** "Latency: 0s" / "Tokens used: 0" render when cached JSON has 0 in those fields. Fix: render "—" when zero.
- **[P1]** Severity metric labels use colored circle emoji (lines 247-249). WCAG 1.4.1 fail. Fix: text labels + CSS.
- **[P2]** "Tokens used" is engineering debug field, not clinical. Fix: remove from pharmacist-facing bar.

### Synthetic data banner trust

- **[P1]** Uses `st.warning()` (yellow, alarming). Synthetic data is informational disclosure, not warning. Fix: `st.info()`.
- **[P2]** Banner copy includes "v0.1 demo" — internal versioning. Fix: remove version reference.

### Briefing item — collapsed scan state

- **[P1]** Confidence visually equivalent weight to severity. Fix: subordinate confidence — smaller/lighter or move inside expander.
- **[P1]** "Agent reasoning + citations" expander label leads with "Agent" — describes tech not content. Fix: "Details + citations" or "Details."
- **[P2]** Recommended action renders as `st.caption` (lowest contrast). Fix: `st.markdown` with bolder treatment.

### Briefing item — expanded drill-down

- **[P0]** HITL action buttons inside expander. Fix: move to collapsed card view, outside expander.
- **[P0]** Override records `"override"` string with no reason capture. Fix: text input/area for reason before logging.
- **[P1]** RxCUI renders inline next to every alternative. Fix: tooltip or copy button, remove from scan text.
- **[P1]** Alternatives list has no rank indicator. Fix: prefix with "(1)" or "Preferred:" / "Alternative:".

### Citations placement (PRD demands visible-by-default)

- **[P0]** Citations inside expander, hidden by default. Direct PRD violation. Fix: render primary `[source]` link in collapsed card.

### Tool call trace (PRD: transparency IS the trust UX)

- **[P1]** "Tool call trace" label is dev-language. Fix: rename to "Audit trail (N API calls)."
- **[P2]** Args truncated at 120 chars — may obscure drug names. Fix: 300 chars or formatted key-value.

### HITL action buttons (Accept / Override / Escalate)

- **[P0]** Buttons hidden inside expander.
- **[P0]** Override has no reason-capture input.
- **[P1]** After acceptance, `st.success("✓ accept")` shows raw action string. Fix: map to "Accepted" / "Overridden" / "Escalated to P&T".
- **[P1]** No undo affordance. Fix: `st.caption("To undo, re-run briefing.")`.
- **[P2]** Escalate has no downstream target. Fix: `st.toast("Escalation flagged in audit log.")`.

### Empty states + loading states

- **[P1]** No-briefing empty state positions tool as not ready. Fix: "No briefing for today yet. Click Re-run briefing to fetch the latest FDA shortage data — takes about 45 seconds."
- **[P1]** Re-run uses `st.spinner` for 30-60s wait. Fix: `st.status()` streaming step labels (matches PRD "tool calls stream in").
- **[P1]** Zero-items empty state uses "may" — uncertainty in reassuring state. Fix: "No formulary drugs affected by current FDA shortages as of [timestamp]. Next re-run scheduled for tomorrow morning."

### Eval tab (admin/internal flow)

- **[P1]** No orientation framing for non-engineering viewers. Fix: header "Internal quality scoring — for pharmacy operations review, not clinical use."
- **[P1]** "Case results" dataframe not rendering — likely `if results:` falls through to stale session. Fix: explicit `else:` with `st.caption` fallback.
- **[P2]** Bar chart emoji in title. Fix: plain text.

### Anti-pattern audit (PRD §10.4)

- **Multi-tab hierarchies**: Currently 2 nav items — acceptable. Adding Formulary as 3rd peer would violate.
- **Search-first**: Not present. Compliant.
- **Show-everything**: Correctly filtered. Compliant.
- **Modal stacks**: Not present. Compliant.
- **Conversational chatbot**: Not present. Compliant.
- **Feature-first nav**: Partial violation — "Re-run briefing" button equal-weight with title. Demote to caption row.

### AI tells (emoji audit)

| Location | Emoji | Verdict |
|---|---|---|
| `main.py:21` `page_icon` | "💊" | Remove |
| `main.py:30` `SEVERITY_COLOR` | "🔴🟡🟢" | Replace with text badges |
| `main.py:31` `CONFIDENCE_COLOR` | "🟢🟡🔴" | Replace with text |
| `main.py:209` H1 title | "💊" | Remove |
| `main.py:209` Re-run button | "🔄" | Remove |
| `main.py:134` Accept button | "✓" | Keep — checkmark functional |
| `main.py:137` Override button | "✎" | Remove — pencil stylistic |
| `main.py:140` Escalate button | "⚠" | Acceptable — clinical meaning |
| `main.py:147` Eval title | "📊" | Remove |
| `main.py:212` Synthetic banner | "⚠️" | Remove (redundant with `st.warning` icon, banner being replaced anyway) |

Copywriting tells:
- "Agent reasoning + citations" → "Details + citations"
- "Tool call trace" → "Audit trail"

---

## Formulary visualization design

### Where it lives

**Recommendation**: expandable section at bottom of Briefing tab, NOT new top-level tab.

`st.expander("Formulary overview — 30 drugs", expanded=False)` below briefing item list.

**Rationale**: PRD anti-pattern "multi-tab hierarchy" violated the moment Formulary becomes peer to Briefing. Marcus's 5-min triage should never require leaving briefing view. Expandable section = "one click deeper" without breaking scan-first flow. Cross-links from individual briefing items bring formulary view into context exactly when needed.

For v0.2: if formulary becomes heavy use case, promote to sidebar tab BUT make Briefing the default landing.

### View 1 — browse and filter

Compact `st.dataframe`, 5 columns: Drug Name, Class, Route, Formulary Status, Shortage Status. Filter widgets above: 3 `st.multiselect` (Class, Route, Status).

Formulary status: preferred / restricted / non-preferred / non-formulary — colored text (no emoji).
Shortage status: pull from current briefing JSON — Critical / Watch in red/amber, Clear in neutral.

`therapeutic_class` currently "TBD" — note as "Class data pending" until populated.

Default sort: Shortage Status descending (Critical first), then alphabetical.

### View 2 — overlap with shortages

**Status matrix, not heatmap.** 30 drugs × small daily shortage set (2-10 overlaps) — heatmap adds complexity without information.

Two-column layout: "Affected drugs" left (in both formulary + current shortage feed, severity-badged), "Clear drugs" right (count only, collapsed). Faster to scan than matrix. Directly answers "which of my drugs are a problem today?"

### View 3 — single-drug drill-down

Click row in View 1 → formulary section shows single-drug panel, two columns:

**Left**: Formulary record — name, RxCUI, route, class, formulary status, restriction criteria, last P&T review date, preferred alternatives with confidence.

**Right**: Operational context — active order count (last 30 days), departments ordering, current shortage status with FDA source link, any briefing item for this drug from today's run (cross-referenced by RxCUI).

Inline replacement, not modal. One click to here, one click back. Satisfies "max 1 click to source" + "inline expansion."

### Integration with briefing flow

Each briefing item card includes inline link below drug name: "View in formulary." Click sets `st.session_state.selected_formulary_drug = rxcui` and scrolls/expands formulary section with drug pre-selected in View 3.

Closes most important workflow gap: Marcus reads Cisplatin Critical item → wants formulary context (carboplatin on formulary? restriction criteria?) → one click without leaving briefing view.

---

## Priority improvement list

### P0 — Ship blockers (PRD non-negotiables violated)

1. Citations hidden in expander — violates "citation-first, visible by default." Add primary citation link to collapsed card.
2. HITL buttons inside expander — pharmacist cannot accept without drilling. Move outside expander.
3. Override logs no reason — clinically indefensible audit trail. Add reason capture.
4. "Latency: 0s / Tokens: 0" reads as broken. Render "—" when zero/missing.

### P1 — Pre-demo polish

5. Replace all decorative emoji with text/icon alternatives.
6. Human-formatted date header: "Morning Briefing — May 1, 2026."
7. Rename "Agent reasoning + citations" → "Details + citations"; "Tool call trace" → "Audit trail."
8. Synthetic data banner: `st.info` not `st.warning`, remove "v0.1 demo."
9. Re-run: `st.status()` streaming, not spinner.
10. Zero-items empty state: remove "may," add timestamp.
11. Action post-state: map strings to "Accepted" / "Overridden" / "Escalated to P&T."
12. Recommended action: promote from `st.caption` to `st.markdown`.
13. Eval tab: explicit empty fallback, fix dataframe rendering.
14. Remove "Tokens used" from pharmacist-facing stats.
15. Remove "Customer: memorial-health-450" raw ID.

### P2 — Nice-to-have

16. Post-briefing completion state.
17. RxCUI: tooltip or copy affordance.
18. Escalate: `st.toast` confirmation.
19. Override: undo affordance.
20. Re-run button: demote visual prominence.
21. **Formulary visualization** (per design above).
22. Eval tab: orientation header.
