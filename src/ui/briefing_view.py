"""Briefing tab renderer — Pattern B: 100% sync."""

import html
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.domain.severity import Severity, SEVERITY_RANK
from src.domain.matching import primary_citation_url
from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.ui.actions import log_action
from src.ui.components import demo_banner
from src.ui.formatters import format_timestamp
from src.ui.runner import run_briefing_with_status

# ACTION_LABELS — displayed pill text after the user takes an action.
# Backwards-compatible: legacy "override" entries still render as "Dismissed".
ACTION_LABELS = {
    "accept":   "Reviewed",
    "override": "Dismissed",   # legacy — kept for items written before the rename
    "dismiss":  "Dismissed",
    "escalate": "Flagged for P&T",
}

# ── Design tokens ──────────────────────────────────────────────────────────────
_NAVY       = "#002045"   # used for body text/links — stays dark for legibility
_PRIMARY_BG = "#a8c5e8"   # pastel blue for the Accept button background
_PRIMARY_FG = "#0d1c2e"   # dark navy text on pastel button
_SLATE      = "#74777f"
_ON_SURFACE = "#0d1c2e"
_ON_VARIANT = "#43474e"
_WHITE      = "#ffffff"
_BORDER     = "#c4c6cf"

_SEV_ACCENT   = {"Critical": "#ba1a1a", "Watch": "#b45309", "Resolved": "#15803d"}
_SEV_BADGE_BG = {"Critical": "#ffdad6", "Watch": "#fffbeb", "Resolved": "#dcfce7"}
_SEV_BADGE_FG = {"Critical": "#93000a", "Watch": "#92400e", "Resolved": "#166534"}
_CONF_BG = {"High": "#dcfce7", "Medium": "#dce9ff", "Low": "#fee2e2"}
_CONF_FG = {"High": "#166534", "Medium": "#43474e", "Low": "#991b1b"}

# FDA status badge palette — neutral slate so it doesn't compete with Impact colour.
_FDA_BADGE_BG = "#eef2f7"
_FDA_BADGE_FG = "#1f2937"


# ── Display label helpers ──────────────────────────────────────────────────────

def _impact_label(severity: str | None) -> str:
    """Internal severity -> pharmacist-facing impact label."""
    return {
        "Critical": "High",
        "Watch":    "Monitor",
        "Resolved": "Resolved",
    }.get(severity or "", "Monitor")


def _fda_status_label(status: str | None) -> str:
    """FDA canonical status -> pharmacist-facing wording."""
    return {
        "Current":             "Current shortage",
        "To Be Discontinued":  "To be discontinued",
        "Resolved":            "Resolved by FDA",
    }.get(status or "", "FDA status unknown")


def _evidence_label(confidence: str | None) -> str:
    """Agent confidence -> evidence wording (Title-cased)."""
    return (confidence or "low").title()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _lbl(text: str) -> str:
    return (
        f'<div style="font-size:10px;font-weight:600;letter-spacing:0.07em;'
        f'text-transform:uppercase;color:{_SLATE};margin-bottom:4px;">'
        f'{html.escape(text)}</div>'
    )


def _metric_tile(label: str, value: str, accent: str) -> str:
    return (
        f'<div style="background:{_WHITE};border:1px solid {_BORDER};border-radius:2px;'
        f'padding:16px 20px;position:relative;overflow:hidden;'
        f'box-shadow:0 1px 3px rgba(13,28,46,0.06);min-width:0;">'
        f'<div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:{accent};"></div>'
        f'<div style="font-size:11px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.05em;color:{_SLATE};margin-bottom:8px;">{html.escape(label)}</div>'
        f'<div style="font-size:24px;font-weight:500;color:{accent};'
        f'line-height:1.33;letter-spacing:-0.01em;">{html.escape(str(value))}</div>'
        f'</div>'
    )


# ── Drilldown ──────────────────────────────────────────────────────────────────

def render_drilldown(item: dict) -> None:
    # ── FDA details ────────────────────────────────────────────────────────
    status              = item.get("status")
    shortage_reason     = item.get("shortage_reason")
    related_info        = item.get("related_info")
    availability        = item.get("availability")
    company_name        = item.get("company_name")
    presentation        = item.get("presentation")
    dosage_form         = item.get("dosage_form")
    update_date         = item.get("update_date")
    initial_date        = item.get("initial_posting_date")
    estimated_resolution = item.get("estimated_resolution")

    rxcui = item.get("rxcui")

    fda_rows = []
    fda_rows.append(("FDA status",       _fda_status_label(status)))
    fda_rows.append(("FDA reason",       shortage_reason or "Not provided by FDA"))
    fda_rows.append(("FDA availability", availability or "Not provided by FDA"))
    if related_info:
        fda_rows.append(("Manufacturer note", related_info))
    if company_name:
        fda_rows.append(("Manufacturer", company_name))
    if presentation:
        fda_rows.append(("Presentation", presentation))
    if dosage_form:
        fda_rows.append(("Dosage form", dosage_form))
    if rxcui:
        fda_rows.append(("RxCUI", rxcui))
    if initial_date:
        fda_rows.append(("First posted", initial_date))
    if update_date:
        fda_rows.append(("Last updated", update_date))
    if estimated_resolution:
        fda_rows.append(("Estimated resolution", estimated_resolution))

    if fda_rows:
        st.markdown("**FDA details**")
        for label, value in fda_rows:
            st.markdown(
                f'<div style="display:flex;gap:8px;font-size:13px;margin-bottom:4px;">'
                f'<span style="color:#6B7280;min-width:160px;font-weight:500;">{html.escape(label)}</span>'
                f'<span style="color:#1F2937;">{html.escape(str(value))}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown("---")

    rationale = item.get("rationale", "")
    if rationale:
        st.markdown("**Rationale**")
        st.write(rationale)

    alts = item.get("alternatives", []) or []
    if alts:
        st.markdown("**Potential therapeutic alternatives**")
        st.caption("RxNorm/RxClass suggestions; clinical review required.")
        rows = [
            {
                "Option":   f"Option {i + 1}",
                "Drug":     a.get("name", ""),
                "Evidence": (a.get("confidence", "") or "").title(),
                "RxCUI":    a.get("rxcui", ""),
                "Notes":    a.get("rationale", ""),
            }
            for i, a in enumerate(alts)
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    cites = item.get("citations", []) or []
    if cites:
        st.markdown("**All citations**")
        for c in cites:
            url = c.get("url") or c.get("source_url", "")
            claim = c.get("claim", "")
            st.markdown(f"- {html.escape(claim)} — [source]({url})" if url else f"- {html.escape(claim)}")

    tool_calls = item.get("tool_call_log", []) or []
    if tool_calls:
        item_id = item.get("item_id", "")
        if st.toggle(f"Show audit trail ({len(tool_calls)} API calls)", key=f"trace-{item_id}"):
            for tc in tool_calls:
                args_str = json.dumps(tc.get("args", {}))[:300]
                preview  = str(tc.get("result_preview", ""))[:300]
                st.code(f"{tc.get('tool', '')}({args_str})\n→ {preview}", language="text")


# ── Dismiss form ───────────────────────────────────────────────────────────────

def _render_dismiss_form(item_id: str, briefing_path) -> None:
    dismiss_key = f"dismiss-open-{item_id}"
    reason = st.text_area(
        "Dismiss reason (required)",
        key=f"dismiss-reason-{item_id}",
        placeholder="Why is this not actionable for this briefing?",
        height=80,
    )
    c1, c2 = st.columns(2)
    if c1.button("Dismiss alert", key=f"dismiss-confirm-{item_id}",
                 type="primary", use_container_width=True):
        if reason and reason.strip():
            log_action(briefing_path, item_id, "dismiss", reason.strip())
            st.session_state[dismiss_key] = False
            st.rerun()
        else:
            st.warning("Reason required.")
    if c2.button("Cancel", key=f"dismiss-cancel-{item_id}", use_container_width=True):
        st.session_state[dismiss_key] = False
        st.rerun()


# ── Alert card ─────────────────────────────────────────────────────────────────

_AVAIL_STYLE = {
    "Available":   ("#166534", "#dcfce7", "#bbf7d0"),
    "Unavailable": ("#991b1b", "#fee2e2", "#fecaca"),
}

def _avail_chip(availability: str | None) -> str:
    if not availability:
        return ""
    label = availability.strip()
    # Normalise long availability strings to a short chip label
    if "unavailable" in label.lower() or "not available" in label.lower():
        key = "Unavailable"
    elif "available" in label.lower():
        key = "Available"
    else:
        key = "Available"   # fallback — show as neutral green
    fg, bg, border = _AVAIL_STYLE.get(key, ("#374151", "#f3f4f6", "#d1d5db"))
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {border};'
        f'font-size:10px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'
        f'padding:3px 9px;border-radius:2px;">{html.escape(label)}</span>'
    )


def render_collapsed_card(item: dict, briefing_path, card_idx: int = 0) -> None:
    severity     = item.get("severity", "Watch")
    drug         = item.get("drug_name", "Unknown")
    summary      = item.get("summary", "")
    action       = item.get("recommended_action", "")
    cite_url     = primary_citation_url(item)
    user_action  = item.get("user_action")
    item_id      = item.get("item_id", "")
    dismiss_key  = f"dismiss-open-{item_id}"

    # ── FDA factual fields ──────────────────────────────────────────────────
    fda_status      = item.get("status")
    availability    = item.get("availability")
    shortage_reason = item.get("shortage_reason")
    update_date     = item.get("update_date")

    # ── Two primary status labels: FDA / Impact ─────────────────────────────
    # (Evidence pill removed per UX simplification — internal confidence
    # signal is not pharmacist-facing.)
    impact          = _impact_label(severity)
    fda_status_text = _fda_status_label(fda_status)

    badge_bg = _SEV_BADGE_BG.get(severity, "#e5eeff")
    badge_fg = _SEV_BADGE_FG.get(severity, _NAVY)

    def _pill(label: str, bg: str, fg: str) -> str:
        return (
            f'<span style="background:{bg};color:{fg};font-size:11px;'
            f'font-weight:600;letter-spacing:0.02em;'
            f'padding:3px 9px;border-radius:2px;white-space:nowrap;">'
            f'{html.escape(label)}</span>'
        )

    badges_html = (
        _pill(f"FDA: {fda_status_text}", _FDA_BADGE_BG, _FDA_BADGE_FG)
        + "&nbsp;"
        + _pill(f"Impact: {impact}", badge_bg, badge_fg)
    )

    # ── FDA facts row: Reason · Availability · Updated ──────────────────────
    reason_text = shortage_reason or "Not provided by FDA"
    fact_parts = [f'<b style="color:{_ON_VARIANT};">Reason:</b> {html.escape(reason_text)}']
    if availability:
        fact_parts.append(
            f'<b style="color:{_ON_VARIANT};">Availability:</b> {html.escape(availability)}'
        )
    if update_date:
        fact_parts.append(
            f'<b style="color:{_ON_VARIANT};">Updated:</b> {html.escape(update_date)}'
        )
    facts_html = (
        f'<div style="font-size:12px;color:{_SLATE};margin:8px 0 12px 0;'
        f'line-height:1.6;">{" &nbsp;·&nbsp; ".join(fact_parts)}</div>'
    )

    source_html = (
        f'<div style="margin-top:14px;">{_lbl("Source")}'
        f'<a href="{html.escape(cite_url)}" target="_blank" '
        f'style="font-size:12px;color:{_NAVY};text-decoration:none;'
        f'border-bottom:1px solid {_BORDER};">∞ FDA Drug Shortage Record</a></div>'
    ) if cite_url else ""

    # ── Bordered card container ──────────────────────────────────────────────
    with st.container(border=True):
        col_content, col_btns = st.columns([6, 1.6])

        # LEFT — text content
        with col_content:
            st.markdown(
                f'<div style="padding:4px 4px 4px 8px;">'
                # Header row: drug name + badges
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:flex-start;margin-bottom:6px;gap:12px;flex-wrap:wrap;">'
                f'<div style="font-size:17px;font-weight:600;color:{_ON_SURFACE};'
                f'letter-spacing:-0.01em;line-height:1.3;">{html.escape(drug)}</div>'
                f'<div style="display:flex;gap:6px;padding-top:2px;flex-shrink:0;'
                f'flex-wrap:wrap;">{badges_html}</div>'
                f'</div>'
                # FDA facts row: Reason · Availability · Updated
                f'{facts_html}'
                # 2-col grid: why it matters | recommended next step
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">'
                f'<div>{_lbl("Why it matters")}'
                f'<div style="font-size:13px;color:{_ON_VARIANT};line-height:1.6;">'
                f'{html.escape(summary) if summary else "—"}</div></div>'
                f'<div>{_lbl("Recommended next step")}'
                f'<div style="font-size:13px;color:{_ON_VARIANT};line-height:1.6;">'
                f'{html.escape(action) if action else "—"}</div></div>'
                f'</div>'
                f'{source_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # RIGHT — button stack
        with col_btns:
            if user_action:
                fg2, bg2 = (
                    ("#166534", "#dcfce7") if user_action == "accept" else
                    ("#92400e", "#fffbeb") if user_action in ("override", "dismiss") else
                    ("#93000a", "#ffdad6")
                )
                label = ACTION_LABELS.get(user_action, user_action.title())
                st.markdown(
                    f'<div style="margin-top:12px;font-size:12px;font-weight:600;'
                    f'color:{fg2};background:{bg2};padding:8px 12px;border-radius:2px;'
                    f'text-align:center;">{html.escape(label)}</div>',
                    unsafe_allow_html=True,
                )
            elif st.session_state.get(dismiss_key):
                _render_dismiss_form(item_id, briefing_path)
            else:
                if st.button(
                    "Mark reviewed",
                    key=f"accept-{item_id}",
                    type="primary",
                    use_container_width=True,
                    help="Record that this alert has been reviewed; the app takes no clinical action.",
                ):
                    log_action(briefing_path, item_id, "accept")
                    st.rerun()
                if st.button(
                    "Dismiss",
                    key=f"dismiss-{item_id}",
                    use_container_width=True,
                    help="Record why this alert is not actionable for this briefing.",
                ):
                    st.session_state[dismiss_key] = True
                    st.rerun()

        # Drilldown expander INSIDE the card
        with st.expander("Details + citations"):
            render_drilldown(item)


# ── Briefing tab ───────────────────────────────────────────────────────────────

def render_briefing_tab() -> None:
    # ── CSS: button styles only ────────────────────────────────────────────────
    # NOTE: stVerticalBlockBorderWrapper does NOT exist in Streamlit 1.57.
    # The bordered container is data-testid="stVerticalBlock" with Emotion CSS.
    # Background colour is forced via JS below (computed style detection).
    st.markdown(
        f"""<style>
        /* Primary (Accept) button = pastel blue with dark text */
        .stButton button[kind="primaryButton"],
        button[data-testid="baseButton-primary"] {{
          background-color: {_PRIMARY_BG} !important;
          border-color:     {_PRIMARY_BG} !important;
          color:            {_PRIMARY_FG} !important;
          font-weight: 600 !important;
        }}
        .stButton button[kind="primaryButton"]:hover {{
          background-color: #93b6dc !important;
          border-color:     #93b6dc !important;
          color:            {_PRIMARY_FG} !important;
        }}
        .stButton button[kind="primaryButton"] p,
        button[data-testid="baseButton-primary"] p {{
          color: {_PRIMARY_FG} !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )

    # ── JS: force white on bordered stVerticalBlock elements ──────────────────
    # stVerticalBlockBorderWrapper does NOT exist in Streamlit 1.57.
    # Bordered containers render as stVerticalBlock with Emotion-generated CSS.
    # We detect which ones have a border via getComputedStyle and paint them white.
    components.html(
        """
        <script>
        (function() {
          function applyWhiteCards() {
            try {
              var pdoc = window.parent.document;
              var blocks = pdoc.querySelectorAll('[data-testid="stVerticalBlock"]');
              blocks.forEach(function(el) {
                var cs = window.parent.getComputedStyle(el);
                var bw = parseFloat(cs.borderLeftWidth || cs.borderWidth || '0');
                if (bw > 0) {
                  // This is a bordered card container — force white fill
                  el.style.setProperty('background-color', '#ffffff', 'important');
                }
              });
            } catch(e) { /* cross-origin guard, shouldn't fire on localhost */ }
          }

          // Run immediately, then again after short delays to catch late renders
          applyWhiteCards();
          setTimeout(applyWhiteCards, 200);
          setTimeout(applyWhiteCards, 800);

          // Re-apply on every DOM mutation (button clicks trigger Streamlit re-renders)
          var obs = new MutationObserver(function() { applyWhiteCards(); });
          obs.observe(window.parent.document.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        height=1,
    )

    running = st.session_state.get("briefing_running", False)

    hcol1, hcol2 = st.columns([4, 1])
    with hcol1:
        st.markdown(
            f'<h1 style="font-size:28px;font-weight:700;color:{_ON_SURFACE};'
            f'letter-spacing:-0.02em;margin-bottom:0;">'
            f'Rx Shortage Intelligence</h1>',
            unsafe_allow_html=True,
        )
    with hcol2:
        rerun_clicked = st.button(
            "Running…" if running else "Re-run briefing",
            use_container_width=True,
            disabled=running,
        )

    st.markdown(demo_banner(), unsafe_allow_html=True)

    if rerun_clicked and not running:
        st.session_state["briefing_running"] = True
        try:
            ok = run_briefing_with_status()
        finally:
            st.session_state["briefing_running"] = False
        if ok:
            st.rerun()
        return

    path = find_latest_briefing()
    if path is None:
        st.info("No briefing yet — click **Re-run briefing** to fetch FDA shortage data.")
        return

    run   = load_briefing(path)
    items = run.get("items", []) or []

    if run.get("fetch_error"):
        st.error(f"FDA feed error: {run['fetch_error']}.")

    counts = {s: 0 for s in Severity}
    for it in items:
        sev = it.get("severity", Severity.WATCH)
        if sev in counts:
            counts[sev] += 1

    run_ts = format_timestamp(run.get("run_timestamp", ""))

    sh_left, sh_right = st.columns([3, 2])
    with sh_left:
        st.markdown(
            f'<div style="font-size:18px;font-weight:600;color:{_ON_SURFACE};'
            f'padding-top:8px;letter-spacing:-0.01em;">Shortage Briefing</div>',
            unsafe_allow_html=True,
        )
    with sh_right:
        st.markdown(
            f'<div style="text-align:right;font-size:13px;color:{_SLATE};'
            f'padding-top:12px;">{html.escape(run_ts)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<hr style="border:none;border-top:1px solid {_BORDER};margin:6px 0 12px 0;">',
        unsafe_allow_html=True,
    )

    t1, t2, t3 = st.columns(3)
    t1.markdown(_metric_tile("High Impact", str(counts[Severity.CRITICAL]), _SEV_ACCENT["Critical"]), unsafe_allow_html=True)
    t2.markdown(_metric_tile("Monitor",     str(counts[Severity.WATCH]),    _SEV_ACCENT["Watch"]),    unsafe_allow_html=True)
    t3.markdown(_metric_tile("Resolved",    str(counts[Severity.RESOLVED]), _SEV_ACCENT["Resolved"]), unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-size:12px;color:{_SLATE};margin-top:6px;margin-bottom:4px;">'
        f'Impact reflects local formulary use, active orders, route, departments, and substitute availability. · '
        f'{run.get("items_reviewed", 0)} drugs reviewed · '
        f'{run.get("items_surfaced", 0)} items surfaced</div>',
        unsafe_allow_html=True,
    )

    if not items:
        st.info(f"No formulary drugs affected by current FDA shortages as of {run_ts}.")
        return

    st.markdown(
        f'<div style="font-size:18px;font-weight:600;color:{_ON_SURFACE};'
        f'margin-top:24px;margin-bottom:12px;padding-bottom:8px;'
        f'border-bottom:1px solid {_BORDER};letter-spacing:-0.01em;">'
        f'Active Alerts</div>',
        unsafe_allow_html=True,
    )

    sorted_items = sorted(items, key=lambda x: SEVERITY_RANK.get(x.get("severity", "Watch"), 1))
    for idx, item in enumerate(sorted_items):
        render_collapsed_card(item, path, card_idx=idx)
