"""Briefing tab renderer — Pattern B: 100% sync."""

import html
import json

import pandas as pd
import streamlit as st

from src.domain.severity import Severity, SEVERITY_RANK
from src.domain.matching import primary_citation_url
from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.ui.actions import log_action
from src.ui.components import demo_banner
from src.ui.formatters import format_timestamp
from src.ui.runner import run_briefing_with_status

ACTION_LABELS = {"accept": "Accepted", "override": "Overridden", "escalate": "Escalated to P&T"}

# ── Design tokens ──────────────────────────────────────────────────────────────
_NAVY       = "#002045"
_SLATE      = "#74777f"
_ON_SURFACE = "#0d1c2e"
_ON_VARIANT = "#43474e"
_WHITE      = "#ffffff"
_BORDER     = "#c4c6cf"

_SEV_ACCENT   = {"Critical": "#ba1a1a", "Watch": "#b45309", "Resolved": "#15803d"}
_SEV_BADGE_BG = {"Critical": "#ffdad6", "Watch": "#fffbeb", "Resolved": "#dcfce7"}
_SEV_BADGE_FG = {"Critical": "#93000a", "Watch": "#92400e", "Resolved": "#166534"}
_CONF_BG = {"HIGH": "#dcfce7", "MEDIUM": "#dce9ff", "LOW": "#fee2e2"}
_CONF_FG = {"HIGH": "#166534", "MEDIUM": "#43474e", "LOW": "#991b1b"}


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
    rationale = item.get("rationale", "")
    if rationale:
        st.markdown("**Rationale**")
        st.write(rationale)

    alts = item.get("alternatives", []) or []
    if alts:
        st.markdown("**Therapeutic alternatives**")
        rows = [
            {
                "Rank":       "Preferred" if i == 0 else "Alternative",
                "Drug":       a.get("name", ""),
                "Confidence": (a.get("confidence", "") or "").upper(),
                "RxCUI":      a.get("rxcui", ""),
                "Rationale":  a.get("rationale", ""),
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


# ── Override form ──────────────────────────────────────────────────────────────

def _render_override_form(item_id: str, briefing_path) -> None:
    override_key = f"override-open-{item_id}"
    reason = st.text_area(
        "Override reason (required)",
        key=f"override-reason-{item_id}",
        placeholder="Document the clinical rationale…",
        height=80,
    )
    c1, c2 = st.columns(2)
    if c1.button("Confirm", key=f"override-confirm-{item_id}",
                 type="primary", use_container_width=True):
        if reason and reason.strip():
            log_action(briefing_path, item_id, "override", reason.strip())
            st.session_state[override_key] = False
            st.rerun()
        else:
            st.warning("Reason required.")
    if c2.button("Cancel", key=f"override-cancel-{item_id}", use_container_width=True):
        st.session_state[override_key] = False
        st.rerun()


# ── Alert card ─────────────────────────────────────────────────────────────────

def render_collapsed_card(item: dict, briefing_path, card_idx: int = 0) -> None:
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
    conf_up  = (confidence or "low").upper()
    conf_bg  = _CONF_BG.get(conf_up, "#e5eeff")
    conf_fg  = _CONF_FG.get(conf_up, _NAVY)

    badges_html = (
        f'<span style="background:{badge_bg};color:{badge_fg};font-size:10px;'
        f'font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'
        f'padding:3px 9px;border-radius:2px;">{html.escape(severity.upper())}</span>'
        f'&nbsp;'
        f'<span style="background:{conf_bg};color:{conf_fg};font-size:10px;'
        f'font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'
        f'padding:3px 9px;border-radius:2px;">CONF: {html.escape(conf_up)}</span>'
    )

    source_html = (
        f'<div style="margin-top:14px;">{_lbl("Source")}'
        f'<a href="{html.escape(cite_url)}" target="_blank" '
        f'style="font-size:12px;color:{_NAVY};text-decoration:none;'
        f'border-bottom:1px solid {_BORDER};">∞ FDA Drug Shortage Record</a></div>'
    ) if cite_url else ""

    # Per-card CSS: target this card's bordered wrapper via :has() marker
    marker_cls = f"rxcm-{card_idx}"
    st.markdown(
        f'<style>'
        # Card shell: 4px coloured left border, white bg
        f'[data-testid="element-container"]:has(.{marker_cls})'
        f' + [data-testid="stVerticalBlockBorderWrapper"] {{'
        f'  border-left: 4px solid {accent} !important;'
        f'  background: {_WHITE} !important;'
        f'  margin-bottom: 12px !important;'
        f'}}'
        # Subtle vertical separator (only the line, NO background change)
        f'[data-testid="element-container"]:has(.{marker_cls})'
        f' + [data-testid="stVerticalBlockBorderWrapper"]'
        f' [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2)'
        f' > div:first-child {{'
        f'  border-left: 1px solid {_BORDER};'
        f'  padding-left: 18px;'
        f'}}'
        # Escalate (3rd button in right col): red text, no border, no bg
        f'[data-testid="element-container"]:has(.{marker_cls})'
        f' + [data-testid="stVerticalBlockBorderWrapper"]'
        f' [data-testid="column"]:nth-child(2) .stButton:nth-of-type(3) > button {{'
        f'  color: #ba1a1a !important;'
        f'  background: transparent !important;'
        f'  border: none !important;'
        f'  box-shadow: none !important;'
        f'  font-weight: 600 !important;'
        f'  padding: 4px 8px !important;'
        f'}}'
        f'[data-testid="element-container"]:has(.{marker_cls})'
        f' + [data-testid="stVerticalBlockBorderWrapper"]'
        f' [data-testid="column"]:nth-child(2) .stButton:nth-of-type(3) > button:hover {{'
        f'  background: #ffdad6 !important;'
        f'}}'
        # Constrain button width (narrower than column) + tighter spacing
        f'[data-testid="element-container"]:has(.{marker_cls})'
        f' + [data-testid="stVerticalBlockBorderWrapper"]'
        f' [data-testid="column"]:nth-child(2) .stButton > button {{'
        f'  max-width: 130px;'
        f'  margin: 0 auto;'
        f'  padding: 6px 12px;'
        f'  font-size: 13px;'
        f'  min-height: 32px;'
        f'}}'
        # Stack spacing between buttons in right column
        f'[data-testid="element-container"]:has(.{marker_cls})'
        f' + [data-testid="stVerticalBlockBorderWrapper"]'
        f' [data-testid="column"]:nth-child(2) .stButton {{'
        f'  margin-bottom: 6px;'
        f'}}'
        f'</style>'
        f'<span class="{marker_cls}" style="display:none;"></span>',
        unsafe_allow_html=True,
    )

    # ── Bordered card container ──────────────────────────────────────────────
    with st.container(border=True):
        col_content, col_btns = st.columns([6, 1.6])

        # LEFT — text content
        with col_content:
            st.markdown(
                f'<div style="padding:4px 4px 4px 8px;">'
                # Header row: drug name + badges
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:flex-start;margin-bottom:14px;gap:12px;">'
                f'<div style="font-size:17px;font-weight:600;color:{_ON_SURFACE};'
                f'letter-spacing:-0.01em;line-height:1.3;">{html.escape(drug)}</div>'
                f'<div style="display:flex;gap:6px;padding-top:2px;flex-shrink:0;">'
                f'{badges_html}</div>'
                f'</div>'
                # 2-col grid: description | action required
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">'
                f'<div>{_lbl("Description")}'
                f'<div style="font-size:13px;color:{_ON_VARIANT};line-height:1.6;">'
                f'{html.escape(summary)}</div></div>'
                f'<div>{_lbl("Action Required")}'
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
                    ("#92400e", "#fffbeb") if user_action == "override" else
                    ("#93000a", "#ffdad6")
                )
                label = ACTION_LABELS.get(user_action, user_action.title())
                st.markdown(
                    f'<div style="margin-top:12px;font-size:12px;font-weight:600;'
                    f'color:{fg2};background:{bg2};padding:8px 12px;border-radius:2px;'
                    f'text-align:center;">{html.escape(label)}</div>',
                    unsafe_allow_html=True,
                )
            elif st.session_state.get(override_key):
                _render_override_form(item_id, briefing_path)
            else:
                if st.button("Accept", key=f"accept-{item_id}",
                             type="primary", use_container_width=True):
                    log_action(briefing_path, item_id, "accept")
                    st.rerun()
                if st.button("Override", key=f"override-{item_id}",
                             use_container_width=True):
                    st.session_state[override_key] = True
                    st.rerun()
                if st.button("Escalate", key=f"escalate-{item_id}",
                             use_container_width=True):
                    log_action(briefing_path, item_id, "escalate")
                    st.toast("Escalation flagged in audit log.")
                    st.rerun()

        # Drilldown expander INSIDE the card
        with st.expander("Details + citations"):
            render_drilldown(item)


# ── Briefing tab ───────────────────────────────────────────────────────────────

def render_briefing_tab() -> None:
    # Global style overrides for this tab
    st.markdown(
        f"""<style>
        /* All bordered card containers: white */
        [data-testid="stVerticalBlockBorderWrapper"] {{
          background: {_WHITE} !important;
        }}
        /* Primary button (Accept) = navy */
        .stButton button[kind="primaryButton"],
        button[data-testid="baseButton-primary"] {{
          background-color: {_NAVY} !important;
          border-color: {_NAVY} !important;
          color: #fff !important;
        }}
        .stButton button[kind="primaryButton"]:hover {{
          background-color: #1a365d !important;
          border-color: #1a365d !important;
        }}
        </style>""",
        unsafe_allow_html=True,
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
    t1.markdown(_metric_tile("Critical", str(counts[Severity.CRITICAL]), _SEV_ACCENT["Critical"]), unsafe_allow_html=True)
    t2.markdown(_metric_tile("Watch",    str(counts[Severity.WATCH]),    _SEV_ACCENT["Watch"]),    unsafe_allow_html=True)
    t3.markdown(_metric_tile("Resolved", str(counts[Severity.RESOLVED]), _SEV_ACCENT["Resolved"]), unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-size:12px;color:{_SLATE};margin-top:6px;margin-bottom:4px;">'
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
