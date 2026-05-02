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


def render_collapsed_card(item: dict, briefing_path) -> None:
    severity = item.get("severity", "Watch")
    drug = item.get("drug_name", "Unknown")
    summary = item.get("summary", "")
    action = item.get("recommended_action", "")
    confidence = item.get("confidence", "low")
    cite_url = primary_citation_url(item)
    user_action = item.get("user_action")

    sev_cls = severity.lower() if severity.lower() in ("critical", "watch", "resolved") else "watch"
    parts = [f'<div class="rx-card rx-card-{sev_cls}">']
    parts.append(
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">'
        f'<div>{severity_badge(severity)}'
        f'<span style="margin-left:10px;font-size:11.5px;color:var(--neutral-500);'
        f'text-transform:uppercase;letter-spacing:0.06em;">Confidence:</span> '
        f'{confidence_pill(confidence)}</div>'
    )
    if user_action:
        label = ACTION_LABELS.get(user_action, user_action.title())
        parts.append(
            f'<span style="font-size:12px;font-weight:600;color:var(--resolved);'
            f'background:var(--resolved-bg);padding:2px 8px;border-radius:3px;'
            f'border:1px solid #BBF7D0;">{html.escape(label)}</span>'
        )
    parts.append('</div>')
    parts.append(f'<div class="rx-card-title">{html.escape(drug)}</div>')
    parts.append(f'<div class="rx-card-summary">{html.escape(summary)}</div>')
    if action:
        parts.append(
            f'<div class="rx-card-action">'
            f'<span class="rx-card-action-label">Action:</span>{html.escape(action)}'
            f'</div>'
        )
    if cite_url:
        parts.append(
            f'<div class="rx-card-citation">'
            f'Source: {citation_link(cite_url)}'
            f'</div>'
        )
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)

    if not user_action:
        render_action_row(item, briefing_path)

    with st.expander("Details + citations"):
        render_drilldown(item)


def render_action_row(item: dict, briefing_path) -> None:
    item_id = item.get("item_id", "")
    override_key = f"override-open-{item_id}"
    if st.session_state.get(override_key):
        with st.container(border=True):
            reason = st.text_area(
                "Override reason (required)",
                key=f"override-reason-{item_id}",
                placeholder="Document the clinical rationale for overriding this recommendation…",
                height=80,
            )
            c1, c2 = st.columns([1, 1])
            if c1.button("Confirm override", key=f"override-confirm-{item_id}", type="primary", use_container_width=True):
                if reason and reason.strip():
                    log_action(briefing_path, item_id, "override", reason.strip())
                    st.session_state[override_key] = False
                    st.rerun()
                else:
                    st.warning("Reason required to log override.")
            if c2.button("Cancel", key=f"override-cancel-{item_id}", use_container_width=True):
                st.session_state[override_key] = False
                st.rerun()
        return

    b1, b2, b3 = st.columns([1, 1, 1])
    if b1.button("Accept", key=f"accept-{item_id}", type="primary", use_container_width=True):
        log_action(briefing_path, item_id, "accept")
        st.rerun()
    if b2.button("Override", key=f"override-{item_id}", use_container_width=True):
        st.session_state[override_key] = True
        st.rerun()
    if b3.button("Escalate", key=f"escalate-{item_id}", use_container_width=True):
        log_action(briefing_path, item_id, "escalate")
        st.toast("Escalation flagged in audit log.")
        st.rerun()


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


def render_briefing_tab() -> None:
    running = st.session_state.get("briefing_running", False)
    hcol1, hcol2 = st.columns([4, 1])
    hcol1.title("Rx Shortage Intelligence")
    rerun_clicked = hcol2.button(
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
        sev = it.get("severity", "Watch")
        if sev in counts:
            counts[sev] += 1

    run_ts = format_timestamp(run.get("run_timestamp", ""))
    st.subheader(f"Morning Briefing — {run_ts}")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Critical", counts["Critical"])
    s2.metric("Watch", counts["Watch"])
    s3.metric("Resolved", counts["Resolved"])
    s4.metric("Latency", format_latency_or_dash(run.get("latency_ms", 0)))
    st.markdown(
        f'<div class="rx-meta-row">{run.get("items_reviewed", 0)} drugs reviewed · '
        f'{run.get("items_surfaced", 0)} items surfaced</div>',
        unsafe_allow_html=True,
    )

    if not items:
        st.info(
            f"No formulary drugs affected by current FDA shortages as of {run_ts}."
        )
        return

    st.divider()
    sorted_items = sorted(items, key=lambda x: SEVERITY_RANK.get(x.get("severity", "Watch"), 1))
    for item in sorted_items:
        render_collapsed_card(item, path)
