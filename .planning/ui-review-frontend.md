# Frontend Design Audit — Rx Shortage Intelligence

## Verdict

The UI ships functional but reads as a rough prototype, not clinical software. The core information architecture is sound — severity ordering, inline expansion, and the one-click HITL action pattern all align with PRD intent. However the visual treatment violates multiple non-negotiable PRD principles: emoji are used as the sole severity/confidence signal throughout (color-only fallback at screen scale, AI-tell aesthetic), `st.metric` delta strings display target thresholds as green upward deltas (misleading for a metric like Hallucination where 0% is the goal), citations are hidden behind an expander instead of visible by default, and the eval tab's "Case results" section renders the briefing item cards instead of the expected case-by-case dataframe. These are not polish gaps — several are P0 blockers against the PRD and trust requirements.

---

## Findings — grouped by section

### Theme + tokens

- [P0] No custom CSS injected; all typography, spacing, and color fall back to Streamlit's default light theme. The PRD specifies a clinical-professional reduced palette with reserved red/amber/green and a sans-serif system stack. Currently indistinguishable from any default Streamlit app. — `main.py` (entire file, no `st.markdown("<style>...")`) — Inject a minimal `<style>` block via `st.markdown(..., unsafe_allow_html=True)` defining CSS custom properties: severity colors, neutral scale, type scale, and monospace rule for code elements.

- [P1] No spacing scale defined. Card padding, section gaps, and stats bar margins are all Streamlit defaults (16px container padding). The resulting vertical rhythm is loose between the stats bar and the first card (~48px dead space visible in screenshot 01, header region). — `screenshot 01`, gap between stats caption row and first item card — Define a 4pt base spacing scale (4 / 8 / 12 / 16 / 24 / 32px) and use `st.markdown` spacers or CSS margin overrides at section boundaries.

- [P2] `page_icon="💊"` sets a pill emoji as the browser tab favicon. — `main.py:23` — Replace with a plain text abbreviation (`"Rx"`) or a served SVG favicon via `st.set_page_config`.

---

### Header + stats bar

- [P0] `st.metric` delta strings show targets as positive green deltas on every metric including Hallucination — `main.py:170–174`, `screenshot 05`. `delta="target <2%"` renders as a green upward arrow on the Hallucination metric, implying higher is better. This is clinically misleading. — Remove all delta strings from `st.metric` calls. Target thresholds belong in a static caption row below the metrics, not as deltas. Set `delta_color="off"` if delta must stay.

- [P1] `st.metric` labels use emoji prefixes: `"🔴 Critical"`, `"🟡 Watch"`, `"🟢 Resolved"` — `main.py:247–249`, `screenshot 01` stats bar. Emoji render inconsistently across OS (macOS vs Windows vs Linux) and are the primary AI-tell the PRD explicitly rejects. — Replace with text-only labels: `"Critical"`, `"Watch"`, `"Resolved"`. Apply severity color to the metric value or a small colored left-border block via injected CSS.

- [P1] Re-run button uses `"🔄 Re-run briefing"` label — `main.py:209`. Spinning-arrow emoji is redundant with the spinner that appears on click. — Label should be `"Re-run briefing"`. Use `st.spinner` text only for loading state; no emoji in button label.

- [P1] `hcol1.title("💊 Rx Shortage Intelligence")` — `main.py:208`, `screenshot 01` header. The pill emoji renders at heading scale (~40px) in Streamlit's h1. It dominates the header and is the definition of "AI sparkle" per PRD §10.3. — Remove emoji. Use plain `st.title("Rx Shortage Intelligence")`. Brand differentiation should come from a wordmark or typographic treatment, not emoji.

- [P2] Run timestamp renders as raw ISO 8601: `"2026-05-01T08:00:00Z"` — `main.py:253`, `screenshot 01` caption row. Clinical users scan; ISO strings require parsing. — Format with `datetime.fromisoformat(...).strftime("%b %d, %Y %H:%M UTC")`.

- [P2] Stats bar shows "Tokens used: 0" and "Latency: 0s" when the briefing was pre-loaded from yesterday's cached JSON — `screenshot 01`. Zero reads as broken, not "cached". — Either hide these metrics when zero/null, or label as "Latency: cached" / "Tokens: —".

---

### Synthetic data banner

- [P1] `st.warning` with `icon=None` still renders Streamlit's default yellow warning background. The PRD requires this banner to be permanently visible as a trust marker, not styled like an error state. A yellow alert-box pattern signals "something is wrong" rather than "this is the demo mode label". — Replace with a neutral-toned inline banner: thin `border-left: 3px solid #B45309` (amber), white/light-gray background, small `DEMO` badge in amber. Do not use `st.warning`.

- [P1] `"⚠️ **SYNTHETIC DATA**"` — `main.py:213`. Emoji inside the warning compound the AI-tell problem at the most-visible element on the page. — Replace `⚠️` with a plain text `[DEMO]` label styled via CSS as a small uppercase badge.

---

### Briefing item card

- [P0] Severity signal is emoji-only: `"🔴 CRITICAL"`, `"🟡 WATCH"` — `main.py:30–31, 86`, `screenshots 01, 03`. On gray-scale print, projector, or for users with red-green color deficiency, emoji colored circles are the sole differentiator. No text-only or shape-based fallback exists. — Replace emoji with a CSS-styled severity badge: colored left border on the card + a text pill (`<span class="badge badge-critical">CRITICAL</span>`). The pill carries both color AND text shape signal.

- [P0] Confidence signal is emoji-only: `"🟢 high"`, `"🟡 medium"`, `"🔴 low"` rendered inline in the alternatives list — `main.py:102–105`, `screenshot 03`. Same accessibility failure as severity. — Replace with a text pill: `HIGH`, `MED`, `LOW` with background fill and sufficient contrast. No emoji.

- [P1] `st.container(border=True)` adds a 1px rounded-corner border (Streamlit default gray). All cards look identical regardless of severity. Critical items are visually indistinguishable from Watch items at a glance except for the red emoji dot — `screenshot 01`. — Add a severity-specific left-border (4px) via injected CSS: `#D92B2B` for Critical, `#B45309` for Watch, `#15803D` for Resolved.

- [P1] Action button labels use emoji: `"✓ Accept"`, `"✎ Override"`, `"⚠ Escalate"` — `main.py:134–142`, `screenshot 03`. These buttons are primary HITL controls — the most consequential interactions in the app. Emoji in action labels is inconsistent with clinical software conventions. — Use plain text labels: `"Accept"`, `"Override"`, `"Escalate"`. Differentiate by button variant: Accept = filled primary, Override = outlined secondary, Escalate = outlined destructive (red border, red text).

- [P1] `st.success(f"✓ {action_taken}")` for the action-taken state — `main.py:92`. `st.success` renders a green box with its own icon, clashing with the card layout. — Replace with a small inline text badge: `"Accepted"` / `"Overridden"` / `"Escalated"` in a muted filled pill (no box, no icon).

- [P2] Recommended action line uses a raw Unicode arrow: `"→ {recommended_action}"` — `main.py:87`. At default body font size this is a weak visual signal for what is the most actionable line in the card. — Visually elevate: slightly heavier weight (`font-weight: 500`), use CSS `::before` pseudo-element instead of character arrow, or prefix with a text label `"Action:"`.

---

### Expanded drill-down (rationale, alts, citations, tool trace, action buttons)

- [P0] Citations are hidden inside the `"Agent reasoning + citations"` expander — `main.py:94, 113–119`, `screenshot 03`, PRD §10.3 "Citation-first — citations visible by default, NOT in tooltips/expanders." This is a direct violation of a PRD non-negotiable. — Move the citations block outside the expander. Render citations at the card level, collapsed by default only for tool-call traces, not for citations.

- [P0] Nested expanders: tool call trace is a `st.expander` nested inside the `"Agent reasoning + citations"` `st.expander` — `main.py:123`. Streamlit 1.x does not support nested expanders reliably; behavior is undefined and visually broken (the inner expander's chevron does not render in screenshots). PRD anti-pattern: "Modal stacks / nested menus." — Replace the inner expander with a `st.toggle` or a conditionally-rendered `st.code` block keyed to a session-state boolean. Keep tool trace collapsed but not nested.

- [P1] Expander label `"Agent reasoning + citations"` conflates two distinct content types — `main.py:94`. Users who want only citations must open the full reasoning block. — Rename to `"Reasoning + tool trace"`. Move citations outside as noted above.

- [P2] RxCUI values in the alternatives list render inline in backtick code spans: `RxCUI \`40048\`` — `main.py:104`, `screenshot 03`. The monospace rendering is correct per PRD, but the surrounding prose sentence is hard to parse at scan speed. — Consider a compact tabular layout for alternatives: Name | RxCUI | Confidence | Route | Rationale, using `st.dataframe` with hidden index or a manual HTML table via `st.markdown`.

---

### Eval tab

- [P0] `st.title("📊 Eval — 15-case scoring")` — `main.py:147`. Bar-chart emoji in H1 heading. Same AI-tell violation as the briefing tab title. — Remove emoji. `st.title("Eval — 15-case scoring")`.

- [P0] `st.dataframe(rows, use_container_width=True)` at line 194 is not rendering the case-results table — `screenshot 05` shows the briefing item cards rendered instead of a dataframe. The `rows` list is a list of dicts; this is valid input for `st.dataframe`, but the screenshot shows no table. The likely cause: `render_eval_tab()` calls `st.dataframe(rows)` but the eval tab's visible content shows the briefing cards from the global `render_item` call path — suggesting the page routing condition (`if page == "Eval": render_eval_tab(); return`) may be bypassed. Needs investigation. — Confirm the early `return` at `main.py:204` is not being short-circuited. Also pass `pd.DataFrame(rows)` explicitly rather than a raw list to avoid Streamlit version-specific dict-list handling.

- [P1] All five `st.metric` delta strings in the eval tab show green upward arrows on targets — `main.py:170–174`, `screenshot 05`. Hallucination `delta="target <2%"` with a green up-arrow is actively misleading in an eval quality context. — Same fix as the briefing stats bar: remove deltas or use `delta_color="off"` with static captions.

- [P2] `st.subheader("Case results")` is followed immediately by the broken dataframe section — `main.py:181`. No explanation of what columns mean or how to read pass/fail. For a QA-oriented view used by the P&T committee, column headers like `"Severity ✓"` need a legend. — Add a one-line `st.caption` below the subheader: `"✓ = matched expected · ✗ = mismatch or not found"`.

---

### Sidebar navigation

- [P1] `st.sidebar.radio("Navigation", ["Briefing", "Eval"])` with `initial_sidebar_state="collapsed"` — `main.py:201, 25`. The sidebar is collapsed by default, making navigation invisible on first load. There is no visible affordance to switch to the Eval tab. — Either set `initial_sidebar_state="expanded"` so the nav is visible, or replace sidebar radio with top-level `st.tabs(["Briefing", "Eval"])` which is always visible without a hamburger click.

- [P2] No active-state styling on the sidebar radio. Streamlit default radio is adequate but the selected state is a small filled circle with no text weight change — hard to confirm at a glance. — Acceptable for v0.1; note for v0.2.

---

### Iconography / AI tells

- [P0] Full inventory of emoji in the codebase used as UI signals:
  - `💊` — page_icon and h1 title (`main.py:23, 208`)
  - `🔴 🟡 🟢 ⚪` — severity and confidence indicators (`main.py:30–32, 86, 102`)
  - `⚠️` — synthetic data banner (`main.py:213`)
  - `🔄` — re-run button (`main.py:209`)
  - `✓` — accept button + action-taken state (`main.py:92, 134`)
  - `✎` — override button (`main.py:137`)
  - `⚠` — escalate button (`main.py:141`)
  - `📊` — eval tab title (`main.py:147`)

  Every one of these is an AI-tell per PRD §10.3 "No AI sparkle iconography." In aggregate they make the product look like a ChatGPT wrapper, not a clinical decision support tool trusted by P&T committees. This is a P0 because it directly undermines the trust positioning that the product is built on.

  Fix strategy: eliminate all emoji. Use CSS-styled text badges for severity/confidence. Use plain text labels for buttons. Use no icon at all for the title — the product name is sufficient. If icons are required (v0.2), use a single consistent SVG icon library (Heroicons or similar, 16px, stroke style).

---

### Accessibility

- [P1] All severity and confidence signals rely on emoji colored circles as the only differentiator — `main.py:30–32`. No `aria-label`, no text fallback, no shape variation. Fails WCAG 1.4.1 (Use of Color). — Text badges with both color and label text resolve this.

- [P1] Three HITL action buttons (`Accept`, `Override`, `Escalate`) are visually identical — same Streamlit default outlined button style, same size, equal columns — `main.py:132–142`, `screenshot 03`. No hierarchy signals which is the safe/default action vs the destructive one. A pharmacist under time pressure should not have to read labels to avoid misclicking Escalate. — Primary button style for Accept, secondary for Override, and a distinct (red outline or red text) destructive style for Escalate.

- [P2] `st.caption` is used for run metadata — `main.py:253`. Streamlit renders captions at ~12px / 0.75rem with reduced contrast. The run timestamp and customer ID are operationally important for confirming freshness; they should not be at caption size. — Use `st.text` or small `st.markdown` with `font-size: 13px; color: #374151` rather than the faded caption style.

- [P2] No keyboard focus indicator customization. Streamlit's default focus ring is thin and browser-dependent. For HITL actions, a visible focus ring (2px solid, offset 2px) on the Accept/Override/Escalate buttons is required for keyboard-only users. — Add via injected CSS: `button:focus-visible { outline: 2px solid #1D4ED8; outline-offset: 2px; }`.

---

## Recommended design tokens (concrete)

### Color palette (hex)

```
Neutral-50   #F9FAFB   Page background
Neutral-100  #F3F4F6   Card background
Neutral-200  #E5E7EB   Card border, dividers
Neutral-600  #4B5563   Secondary text (caption, metadata)
Neutral-800  #1F2937   Primary text
Neutral-900  #111827   Headings

Critical     #D92B2B   Badge fill, card left-border
Critical-bg  #FEF2F2   Card background tint (optional, v0.2)
Watch        #B45309   Badge fill, card left-border
Watch-bg     #FFFBEB   Card background tint (optional, v0.2)
Resolved     #15803D   Badge fill, card left-border
Resolved-bg  #F0FDF4   Card background tint (optional, v0.2)

Action-primary   #1D4ED8   Accept button fill
Action-secondary #374151   Override button border/text
Action-danger    #D92B2B   Escalate button border/text

Banner-border    #B45309   Demo mode banner left-border
```

### Type scale

```
Heading-1   24px / 1.5rem   font-weight: 700   Page title
Heading-2   18px / 1.125rem font-weight: 600   Section header, drug name
Body        14px / 0.875rem font-weight: 400   Summary text, rationale
Body-sm     13px / 0.8125rem font-weight: 400  Metadata, recommended action
Caption     12px / 0.75rem  font-weight: 400   Run timestamp, source links
Mono        13px / 0.8125rem font-family: 'ui-monospace', 'Cascadia Code', monospace
```

### Spacing scale (4pt base)

```
4px   xs   Inline badge padding (horizontal)
8px   sm   Badge padding (vertical), button inner gap
12px  md   Card inner padding top/bottom
16px  lg   Card inner padding left/right, column gap
24px  xl   Between cards
32px  2xl  Section separation (stats bar to first card)
```

### Severity badge spec (no emoji)

```html
<span class="badge badge-{severity}">CRITICAL</span>

CSS:
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.badge-critical { background: #D92B2B; color: #FFFFFF; }
.badge-watch    { background: #B45309; color: #FFFFFF; }
.badge-resolved { background: #15803D; color: #FFFFFF; }
```

Card left-border: `border-left: 4px solid {severity-color}; border-radius: 0 6px 6px 0;`

### Confidence pill spec (no emoji)

```html
<span class="pill pill-{confidence}">MED</span>

CSS:
.pill {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.pill-high   { background: #DCFCE7; color: #15803D; border: 1px solid #BBF7D0; }
.pill-medium { background: #FEF9C3; color: #A16207; border: 1px solid #FDE047; }
.pill-low    { background: #FEE2E2; color: #B91C1C; border: 1px solid #FECACA; }
```
