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
from src.ui.components import demo_banner
from src.ui.formatters import format_timestamp, format_latency_or_dash
from src.ui.runner import run_briefing_with_status

ACTION_LABELS = {"accept": "Accepted", "override": "Overridden", "escalate": "Escalated to P&T"}

# ── Design tokens (matching Stitch mockup "Clinical Precision") ────────────────
_NAVY        = "#002045"
_NAVY_HOVER  = "#1a365d"
_SLATE       = "#74777f"
_ON_SURFACE  = "#0d1c2e"
_ON_VARIANT  = "#43474e"
_SURFACE     = "#f8f9ff"
_WHITE       = "#ffffff"
_BORDER      = "#c4c6cf"

# Severity accent colours (left-bar + badge)
_SEV_ACCENT = {
    "Critical": "#ba1a1a",
    "Watch":    "#b45309",
    "Resolved": "#15803d",
}
_SEV_BADGE_BG = {
    "Critical": "#ffdad6",
    "Watch":    "#fffbeb",
    "Resolved": "#dcfce7",
}
_SEV_BADGE_FG = {
    "Critical": "#93000a",
    "Watch":    "#92400e",
    "Resolved": "#166534",
}

# Confidence pill
_CONF_BG = {"HIGH": "#dcfce7", "MEDIUM": "#fef9c3", "LOW": "#fee2e2"}
_CONF_FG = {"HIGH": "#166534", "MEDIUM": "#92400e", "LOW": "#991b1b"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _label(text: str) -> str:
    """Uppercase section micro-label."""
    return (
        f'<div style="font-size:11px;font-weight:600;letter-spacing:0.05em;'
        f'text-transform:uppercase;color:{_SLATE};margin-bottom:4px;">'
        f'{html.escape(text)}</div>'
    )


def _metric_tile(label: str, value: str, accent: str) -> str:
    """White tile with left 4-px accent bar — matching mockup metric cards."""
    return (
        f'<div style="background:{_WHITE};border:1px solid {_BORDER};border-radius:2px;'
        f'padding:16px 20px;position:relative;overflow:hidden;'
        f'box-shadow:0 1px 3px rgba(13,28,46,0.06);">'
        f'<div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:{accent};"></div>'
        f'<div style="font-size:11px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.05em;color:{_SLATE};margin-bottom:8px;">'
        f'{html.escape(label)}</div>'
        f'<div style="font-size:24px;font-weight:500;color:{accent};'
        f'line-height:1.33;letter-spacing:-0.01em;">'
        f'{html.escape(str(value))}</div>'
        f'</div>'
    )


# ── Drilldown ──────────────────────────────────────────────────────────────────

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


# ── Override form ──────────────────────────────────────────────────────────────

def _render_override_form(item_id: str, briefing_path) -> None:
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


# ── Alert card ─────────────────────────────────────────────────────────────────

def render_collapsed_card(item: dict, briefing_path) -> None:
    severity    = item.get("severity", "Watch")
    drug        = item.get("drug_name", "Unknown")
    summary     = item.get("summary", "")
    action      = item.get("recommended_action", "")
    confidence  = item.get("confidence", "low")
    cite_url    = primary_citation_url(item)
    user_action = item.get("user_action")
    item_id     = item.get("item_id", "")
    override_key = f"override-open-{item_id}"

    accent   = _SEV_ACCENT.get(severity, "#5E7BA4")
    badge_bg = _SEV_BADGE_BG.get(severity, "#e5eeff")
    badge_fg = _SEV_BADGE_FG.get(severity, _NAVY)

    conf_upper = (confidence or "low").upper()
    conf_bg = _CONF_BG.get(conf_upper, "#e5eeff")
    conf_fg = _CONF_FG.get(conf_upper, _NAVY)

    # Severity + confidence badges HTML
    badges_html = (
        f'<span style="background:{badge_bg};color:{badge_fg};font-size:10px;font-weight:600;'
        f'letter-spacing:0.05em;text-transform:uppercase;padding:3px 8px;border-radius:2px;">'
        f'{html.escape(severity.upper())}</span>'
        f'&nbsp;<span style="background:{conf_bg};color:{conf_fg};font-size:10px;font-weight:600;'
        f'letter-spacing:0.05em;text-transform:uppercase;padding:3px 8px;border-radius:2px;">'
        f'CONF: {html.escape(conf_upper)}</span>'
    )

    # Source row HTML
    source_html = ""
    if cite_url:
        source_html = (
            f'<div style="margin-top:10px;">'
            f'{_label("Source")}'
            f'<a href="{html.escape(cite_url)}" target="_blank" style="font-size:12px;color:{_NAVY};'
            f'text-decoration:none;border-bottom:1px solid {_BORDER};">'
            f'FDA Drug Shortage Record</a></div>'
        )

    # ── Card container ──────────────────────────────────────────────────────
    with st.container(border=False):
        # Accent stripe + white card wrapping — CSS class rx-alert-card handles background
        st.markdown(
            f'<div style="background:{_WHITE};border:1px solid {_BORDER};'
            f'border-left:4px solid {accent};border-radius:2px;'
            f'box-shadow:0 1px 3px rgba(13,28,46,0.06);margin-bottom:2px;">',
            unsafe_allow_html=True,
        )

        # Main row: content + button panel
        col_content, col_btns = st.columns([7, 2], gap="small")

        with col_content:
            st.markdown(
                f'<div style="padding:16px 20px 12px 16px;">'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:flex-start;margin-bottom:12px;">'
                f'<div style="font-size:18px;font-weight:600;color:{_ON_SURFACE};'
                f'letter-spacing:-0.01em;line-height:1.3;">{html.escape(drug)}</div>'
                f'<div style="display:flex;gap:6px;flex-wrap:wrap;'
                f'justify-content:flex-end;padding-top:2px;">{badges_html}</div>'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">'
                f'<div>{_label("Description")}'
                f'<div style="font-size:13px;color:{_ON_VARIANT};line-height:1.55;">'
                f'{html.escape(summary)}</div></div>'
                f'<div>{_label("Action Required")}'
                f'<div style="font-size:13px;color:{_ON_VARIANT};line-height:1.55;">'
                f'{html.escape(action) if action else "—"}</div></div>'
                f'</div>'
                f'{source_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        with col_btns:
            # Button panel — visually separated
            st.markdown(
                f'<div style="background:{_SURFACE};border-left:1px solid {_BORDER};'
                f'padding:16px 12px;display:flex;flex-direction:column;gap:6px;">',
                unsafe_allow_html=True,
            )

            if user_action:
                label = ACTION_LABELS.get(user_action, user_action.title())
                badge_fg2, badge_bg2 = (
                    ("#166534", "#dcfce7") if user_action == "accept" else
                    ("#92400e", "#fffbeb") if user_action == "override" else
                    ("#93000a", "#ffdad6")
                )
                st.markdown(
                    f'<div style="font-size:12px;font-weight:600;color:{badge_fg2};'
                    f'background:{badge_bg2};padding:6px 10px;border-radius:2px;'
                    f'text-align:center;">{html.escape(label)}</div>',
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

                if st.button(
                    "Escalate",
                    key=f"escalate-{item_id}",
                    use_container_width=True,
                ):
                    log_action(briefing_path, item_id, "escalate")
                    st.toast("Escalation flagged in audit log.")
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # Drilldown expander (sits below the card box)
        with st.expander("Details + citations"):
            render_drilldown(item)


# ── Briefing tab ───────────────────────────────────────────────────────────────

def render_briefing_tab() -> None:
    running = st.session_state.get("briefing_running", False)

    # ── Page header ──────────────────────────────────────────────────────────
    hcol1, hcol2 = st.columns([4, 1])
    with hcol1:
        st.markdown(
            f'<h1 style="font-size:28px;font-weight:700;color:{_ON_SURFACE};'
            f'letter-spacing:-0.02em;margin-bottom:0;padding-bottom:0;">'
            f'Rx Shortage Intelligence</h1>',
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

    # ── Briefing sub-header ───────────────────────────────────────────────────
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

    # Separator
    st.markdown(
        f'<hr style="border:none;border-top:1px solid {_BORDER};margin:6px 0 12px 0;">',
        unsafe_allow_html=True,
    )

    # ── 3 metric tiles (Critical | Watch | Resolved) ──────────────────────────
    t1, t2, t3 = st.columns(3)
    t1.markdown(
        _metric_tile("Critical", str(counts[Severity.CRITICAL]), _SEV_ACCENT["Critical"]),
        unsafe_allow_html=True,
    )
    t2.markdown(
        _metric_tile("Watch", str(counts[Severity.WATCH]), _SEV_ACCENT["Watch"]),
        unsafe_allow_html=True,
    )
    t3.markdown(
        _metric_tile("Resolved", str(counts[Severity.RESOLVED]), _SEV_ACCENT["Resolved"]),
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="font-size:12px;color:{_SLATE};margin-top:6px;margin-bottom:4px;">'
        f'{run.get("items_reviewed", 0)} drugs reviewed · '
        f'{run.get("items_surfaced", 0)} items surfaced</div>',
        unsafe_allow_html=True,
    )

    if not items:
        st.info(f"No formulary drugs affected by current FDA shortages as of {run_ts}.")
        return

    # ── Active Alerts ─────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="font-size:18px;font-weight:600;color:{_ON_SURFACE};'
        f'margin-top:24px;margin-bottom:4px;padding-bottom:8px;'
        f'border-bottom:1px solid {_BORDER};letter-spacing:-0.01em;">Active Alerts</div>',
        unsafe_allow_html=True,
    )

    sorted_items = sorted(items, key=lambda x: SEVERITY_RANK.get(x.get("severity", "Watch"), 1))
    for item in sorted_items:
        render_collapsed_card(item, path)
