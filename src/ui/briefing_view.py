"""Briefing tab renderer.

Owns render_collapsed_card, render_action_row, render_drilldown, render_briefing_tab.
Pattern B: 100% sync — reads pre-generated JSON, never imports async/MCP.
"""

import html
import json

import pandas as pd
import streamlit as st

from src.domain.severity import Severity, SEVERITY_RANK
from src.domain.matching import primary_citation_url
from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.ui.actions import log_action
from src.ui.components import severity_badge, confidence_pill, demo_banner, citation_link
from src.ui.formatters import format_timestamp, format_latency_or_dash
from src.ui.runner import run_briefing_with_status

ACTION_LABELS = {"accept": "Accepted", "override": "Overridden", "escalate": "Escalated to P&T"}

# ── Colour tokens ──────────────────────────────────────────────────────────────
_NAVY   = "#1A3461"
_SLATE  = "#5E7BA4"
_BG     = "#f8f9ff"
_BORDER = "#dce3ed"

_TILE_COLORS = {
    "critical": "#ba1a1a",
    "watch":    "#b45309",
    "resolved": "#15803d",
    "latency":  _NAVY,
}


# ── Metric tile (HTML, no st.metric) ─────────────────────────────────────────

def _metric_tile(label: str, value: str, color: str) -> str:
    """Return a bordered metric tile as an HTML string."""
    return (
        f'<div style="'
        f'border:1px solid {_BORDER};border-radius:8px;background:#ffffff;'
        f'padding:16px 20px;min-width:0;">'
        f'<div style="font-size:10px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.08em;color:{_SLATE};margin-bottom:6px;">'
        f'{html.escape(label)}</div>'
        f'<div style="font-size:28px;font-weight:700;color:{color};line-height:1;">'
        f'{html.escape(str(value))}</div>'
        f'</div>'
    )


# ── Tiny section-label helper ─────────────────────────────────────────────────

def _section_label(text: str) -> str:
    return (
        f'<div style="font-size:10px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.08em;color:{_SLATE};margin-bottom:4px;">'
        f'{html.escape(text)}</div>'
    )


# ── Drilldown (unchanged logic) ───────────────────────────────────────────────

def render_drilldown(item: dict) -> None:
    rationale = item.get("rationale", "")
    if rationale:
        st.markdown("**Rationale**")
        st.write(rationale)

    alts = item.get("alternatives", []) or []
    if alts:
        st.markdown("**Therapeutic alternatives**")
        rows = []
        for i, alt in enumerate(alts):
            rows.append({
                "Rank":       "Preferred" if i == 0 else "Alternative",
                "Drug":       alt.get("name", ""),
                "Confidence": (alt.get("confidence", "") or "").upper(),
                "RxCUI":      alt.get("rxcui", ""),
                "Rationale":  alt.get("rationale", ""),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    cites = item.get("citations", []) or []
    if cites:
        st.markdown("**All citations**")
        for c in cites:
            url = c.get("url") or c.get("source_url", "")
            claim = c.get("claim", "")
            if url:
                st.markdown(f"- {html.escape(claim)} — [source]({url})")
            else:
                st.markdown(f"- {html.escape(claim)}")

    tool_calls = item.get("tool_call_log", []) or []
    if tool_calls:
        item_id = item.get("item_id", "")
        toggle_key = f"trace-{item_id}"
        if st.toggle(f"Show audit trail ({len(tool_calls)} API calls)", key=toggle_key):
            for tc in tool_calls:
                args_str = json.dumps(tc.get("args", {}))[:300]
                preview = str(tc.get("result_preview", ""))[:300]
                st.code(f"{tc.get('tool', '')}({args_str})\n→ {preview}", language="text")


# ── Override form (rendered inside col3) ─────────────────────────────────────

def _render_override_form(item_id: str, briefing_path) -> None:
    """Render the override reason form inline; returns True when form is open."""
    override_key = f"override-open-{item_id}"
    with st.container(border=True):
        reason = st.text_area(
            "Override reason (required)",
            key=f"override-reason-{item_id}",
            placeholder="Document the clinical rationale for overriding…",
            height=80,
        )
        c1, c2 = st.columns([1, 1])
        if c1.button(
            "Confirm override",
            key=f"override-confirm-{item_id}",
            type="primary",
            use_container_width=True,
        ):
            if reason and reason.strip():
                log_action(briefing_path, item_id, "override", reason.strip())
                st.session_state[override_key] = False
                st.rerun()
            else:
                st.warning("Reason required to log override.")
        if c2.button(
            "Cancel",
            key=f"override-cancel-{item_id}",
            use_container_width=True,
        ):
            st.session_state[override_key] = False
            st.rerun()


# ── Single alert card ─────────────────────────────────────────────────────────

def render_collapsed_card(item: dict, briefing_path) -> None:
    severity   = item.get("severity", "Watch")
    drug       = item.get("drug_name", "Unknown")
    summary    = item.get("summary", "")
    action     = item.get("recommended_action", "")
    confidence = item.get("confidence", "low")
    cite_url   = primary_citation_url(item)
    user_action = item.get("user_action")
    item_id    = item.get("item_id", "")
    override_key = f"override-open-{item_id}"

    with st.container(border=True):
        # ── Row 1: drug name left | badges right ─────────────────────────────
        r1_left, r1_right = st.columns([5, 3])
        with r1_left:
            st.markdown(
                f'<div style="font-size:16px;font-weight:700;color:{_NAVY};'
                f'padding-top:2px;">{html.escape(drug)}</div>',
                unsafe_allow_html=True,
            )
        with r1_right:
            badge_html = (
                f'<div style="display:flex;justify-content:flex-end;'
                f'align-items:center;gap:8px;flex-wrap:wrap;">'
                f'{severity_badge(severity)}'
                f'{confidence_pill(confidence)}'
            )
            if user_action:
                label = ACTION_LABELS.get(user_action, user_action.title())
                badge_html += (
                    f'<span style="font-size:12px;font-weight:600;color:var(--resolved);'
                    f'background:var(--resolved-bg);padding:2px 8px;border-radius:3px;'
                    f'border:1px solid #BBF7D0;">{html.escape(label)}</span>'
                )
            badge_html += '</div>'
            st.markdown(badge_html, unsafe_allow_html=True)

        # ── Row 2: body (description | action required | buttons) ────────────
        col_desc, col_action, col_btns = st.columns([4, 4, 2])

        with col_desc:
            st.markdown(_section_label("Description"), unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:14px;color:#374151;line-height:1.5;">'
                f'{html.escape(summary)}</div>',
                unsafe_allow_html=True,
            )
            if cite_url:
                st.markdown(
                    f'<div style="margin-top:6px;font-size:12px;">'
                    f'Source: {citation_link(cite_url)}</div>',
                    unsafe_allow_html=True,
                )

        with col_action:
            st.markdown(_section_label("Action Required"), unsafe_allow_html=True)
            if action:
                st.markdown(
                    f'<div style="font-size:14px;color:#374151;line-height:1.5;">'
                    f'{html.escape(action)}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="font-size:13px;color:{_SLATE};">—</div>',
                    unsafe_allow_html=True,
                )

        with col_btns:
            if user_action:
                # Already actioned — show badge only (badges already shown in row 1;
                # keep col_btns visually quiet so layout stays balanced)
                label = ACTION_LABELS.get(user_action, user_action.title())
                st.markdown(
                    f'<div style="font-size:12px;font-weight:600;color:var(--resolved);'
                    f'background:var(--resolved-bg);padding:4px 8px;border-radius:3px;'
                    f'border:1px solid #BBF7D0;text-align:center;">'
                    f'{html.escape(label)}</div>',
                    unsafe_allow_html=True,
                )
            elif st.session_state.get(override_key):
                _render_override_form(item_id, briefing_path)
            else:
                if st.button(
                    "Accept",
                    key=f"accept-{item_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    log_action(briefing_path, item_id, "accept")
                    st.rerun()

                if st.button(
                    "Override",
                    key=f"override-{item_id}",
                    use_container_width=True,
                ):
                    st.session_state[override_key] = True
                    st.rerun()

                # Escalate as a red text link styled via markdown
                escalate_key = f"escalate-{item_id}"
                if st.button(
                    "Escalate",
                    key=escalate_key,
                    use_container_width=True,
                ):
                    log_action(briefing_path, item_id, "escalate")
                    st.toast("Escalation flagged in audit log.")
                    st.rerun()

        # ── Drilldown expander ────────────────────────────────────────────────
        with st.expander("Details + citations"):
            render_drilldown(item)


# ── Main tab renderer ─────────────────────────────────────────────────────────

def render_briefing_tab() -> None:
    running = st.session_state.get("briefing_running", False)

    # ── Page header ──────────────────────────────────────────────────────────
    hcol1, hcol2 = st.columns([4, 1])
    with hcol1:
        st.markdown(
            f'<h1 style="font-size:26px;font-weight:700;color:{_NAVY};'
            f'margin-bottom:0;padding-bottom:0;">Rx Shortage Intelligence</h1>',
            unsafe_allow_html=True,
        )
    with hcol2:
        rerun_clicked = st.button(
            "Running…" if running else "Re-run briefing",
            use_container_width=True,
            disabled=running,
        )

    # ── Demo banner ──────────────────────────────────────────────────────────
    st.markdown(demo_banner(), unsafe_allow_html=True)

    # ── Re-run logic ─────────────────────────────────────────────────────────
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
        st.info(
            "No briefing for today yet. Click **Re-run briefing** to fetch the latest "
            "FDA shortage data — takes 2-3 minutes."
        )
        return

    run = load_briefing(path)
    items = run.get("items", []) or []

    # Surface FDA fetch errors honestly — fake-clean briefings break trust.
    if run.get("fetch_error"):
        st.error(
            f"FDA shortage feed returned error: {run['fetch_error']}. "
            "Briefing items below may be incomplete or stale."
        )

    counts = {s: 0 for s in Severity}
    for it in items:
        sev = it.get("severity", Severity.WATCH)
        if sev in counts:
            counts[sev] += 1

    run_ts = format_timestamp(run.get("run_timestamp", ""))

    # ── Sub-header row: title left | date-time right ─────────────────────────
    sh_left, sh_right = st.columns([3, 2])
    with sh_left:
        st.markdown(
            f'<div style="font-size:18px;font-weight:700;color:{_NAVY};'
            f'padding-top:8px;">Shortage Briefing</div>',
            unsafe_allow_html=True,
        )
    with sh_right:
        st.markdown(
            f'<div style="text-align:right;font-size:13px;color:{_SLATE};'
            f'padding-top:12px;">{html.escape(run_ts)}</div>',
            unsafe_allow_html=True,
        )

    # ── 4 metric tiles ───────────────────────────────────────────────────────
    t1, t2, t3, t4 = st.columns(4)
    t1.markdown(
        _metric_tile("Critical", str(counts[Severity.CRITICAL]), _TILE_COLORS["critical"]),
        unsafe_allow_html=True,
    )
    t2.markdown(
        _metric_tile("Watch", str(counts[Severity.WATCH]), _TILE_COLORS["watch"]),
        unsafe_allow_html=True,
    )
    t3.markdown(
        _metric_tile("Resolved", str(counts[Severity.RESOLVED]), _TILE_COLORS["resolved"]),
        unsafe_allow_html=True,
    )
    t4.markdown(
        _metric_tile("Latency", format_latency_or_dash(run.get("latency_ms", 0)), _TILE_COLORS["latency"]),
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="font-size:12px;color:{_SLATE};margin-top:6px;">'
        f'{run.get("items_reviewed", 0)} drugs reviewed · '
        f'{run.get("items_surfaced", 0)} items surfaced</div>',
        unsafe_allow_html=True,
    )

    if not items:
        st.info(
            f"No formulary drugs affected by current FDA shortages as of {run_ts}."
        )
        return

    # ── Active Alerts heading ────────────────────────────────────────────────
    st.markdown(
        f'<div style="font-size:16px;font-weight:700;color:{_NAVY};'
        f'margin-top:20px;margin-bottom:8px;">Active Alerts</div>',
        unsafe_allow_html=True,
    )

    sorted_items = sorted(items, key=lambda x: SEVERITY_RANK.get(x.get("severity", "Watch"), 1))
    for item in sorted_items:
        render_collapsed_card(item, path)
