"""
Rx Shortage Intelligence — Streamlit dashboard.

Pattern B: 100% sync. Reads data/briefings/YYYY-MM-DD.json.
Re-run button spawns CLI subprocess, then reloads.

Run: streamlit run src/main.py
"""

import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Config ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

DATA_DIR = Path(__file__).parent.parent / "data"
BRIEFINGS_DIR = DATA_DIR / "briefings"
FORMULARY_PATH = DATA_DIR / "synthetic_formulary.json"
ORDERS_PATH = DATA_DIR / "active_orders.json"

SEVERITY_RANK = {"Critical": 0, "Watch": 1, "Resolved": 2}
ACTION_LABELS = {"accept": "Accepted", "override": "Overridden", "escalate": "Escalated to P&T"}

# ── Theme tokens (injected once) ────────────────────────────────────────────

THEME_CSS = """
<style>
:root {
  --neutral-50:  #F9FAFB;
  --neutral-100: #F3F4F6;
  --neutral-200: #E5E7EB;
  --neutral-300: #D1D5DB;
  --neutral-500: #6B7280;
  --neutral-600: #4B5563;
  --neutral-700: #374151;
  --neutral-800: #1F2937;
  --neutral-900: #111827;

  --critical:    #B91C1C;
  --critical-bg: #FEF2F2;
  --watch:       #B45309;
  --watch-bg:    #FFFBEB;
  --resolved:    #15803D;
  --resolved-bg: #F0FDF4;

  --action-primary:   #1D4ED8;
  --action-secondary: #374151;
  --action-danger:    #B91C1C;

  --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono-stack: ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace;
}

html, body, [class*="css"] {
  font-family: var(--font-stack);
  color: var(--neutral-800);
}

h1 { font-size: 26px !important; font-weight: 700 !important; color: var(--neutral-900) !important; letter-spacing: -0.01em; }
h2 { font-size: 19px !important; font-weight: 600 !important; color: var(--neutral-900) !important; }
h3 { font-size: 16px !important; font-weight: 600 !important; color: var(--neutral-900) !important; }

.stApp { background: var(--neutral-50); }

code, kbd { font-family: var(--mono-stack) !important; font-size: 12.5px; background: var(--neutral-100); padding: 1px 5px; border-radius: 3px; color: var(--neutral-700); }

.rx-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-family: var(--font-stack);
  vertical-align: middle;
}
.rx-badge-critical { background: var(--critical); color: #fff; }
.rx-badge-watch    { background: var(--watch);    color: #fff; }
.rx-badge-resolved { background: var(--resolved); color: #fff; }

.rx-pill {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: var(--font-stack);
  vertical-align: middle;
}
.rx-pill-high   { background: #DCFCE7; color: #15803D; border: 1px solid #BBF7D0; }
.rx-pill-medium { background: #FEF9C3; color: #A16207; border: 1px solid #FDE047; }
.rx-pill-low    { background: #FEE2E2; color: #B91C1C; border: 1px solid #FECACA; }

.rx-card {
  background: #FFFFFF;
  border: 1px solid var(--neutral-200);
  border-left-width: 4px;
  border-radius: 6px;
  padding: 14px 18px;
  margin-bottom: 14px;
}
.rx-card-critical { border-left-color: var(--critical); }
.rx-card-watch    { border-left-color: var(--watch); }
.rx-card-resolved { border-left-color: var(--resolved); }

.rx-card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-900);
  margin: 4px 0 6px 0;
}
.rx-card-summary {
  font-size: 14px;
  color: var(--neutral-800);
  line-height: 1.5;
  margin: 0 0 6px 0;
}
.rx-card-action {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--neutral-700);
  margin: 4px 0 8px 0;
}
.rx-card-action-label { color: var(--neutral-500); font-weight: 500; margin-right: 4px; }
.rx-card-citation {
  font-size: 12.5px;
  color: var(--neutral-600);
  margin: 6px 0 0 0;
}
.rx-card-citation a { color: var(--action-primary); text-decoration: none; border-bottom: 1px solid var(--neutral-300); }
.rx-card-citation a:hover { border-bottom-color: var(--action-primary); }

.rx-demo-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #FFFFFF;
  border: 1px solid var(--neutral-200);
  border-left: 3px solid var(--watch);
  border-radius: 4px;
  padding: 10px 14px;
  margin: 6px 0 18px 0;
  font-size: 13px;
  color: var(--neutral-700);
}
.rx-demo-chip {
  display: inline-block;
  background: var(--watch-bg);
  color: var(--watch);
  font-weight: 700;
  font-size: 11px;
  letter-spacing: 0.08em;
  padding: 2px 7px;
  border-radius: 3px;
  border: 1px solid #FDE047;
  flex-shrink: 0;
}

.rx-stat-target {
  font-size: 11.5px;
  color: var(--neutral-500);
  margin-top: -10px;
  margin-bottom: 8px;
}

.rx-meta-row {
  font-size: 12.5px;
  color: var(--neutral-600);
  margin: 4px 0 16px 0;
}

button:focus-visible {
  outline: 2px solid var(--action-primary) !important;
  outline-offset: 2px !important;
}

[data-testid="stMetricDelta"] { display: none !important; }
</style>
"""

# ── Helpers ─────────────────────────────────────────────────────────────────

def render_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)

def severity_badge(severity: str) -> str:
    s = (severity or "").strip()
    cls = s.lower() if s.lower() in ("critical", "watch", "resolved") else "watch"
    return f'<span class="rx-badge rx-badge-{cls}">{html.escape(s.upper())}</span>'

def confidence_pill(conf: str) -> str:
    c = (conf or "").strip().lower()
    if c not in ("high", "medium", "low"):
        c = "low"
    label = {"high": "HIGH", "medium": "MED", "low": "LOW"}[c]
    return f'<span class="rx-pill rx-pill-{c}">{label}</span>'

def format_timestamp(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y · %H:%M UTC")
    except (ValueError, TypeError):
        return iso

def format_int_or_dash(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "—"
    return "—" if n == 0 else f"{n:,}"

def format_latency_or_dash(latency_ms) -> str:
    try:
        ms = int(latency_ms)
    except (TypeError, ValueError):
        return "—"
    if ms == 0:
        return "—"
    return f"{ms // 1000}s" if ms >= 1000 else f"{ms} ms"

def primary_citation_url(item: dict) -> str | None:
    for c in item.get("citations", []) or []:
        url = c.get("url") or c.get("source_url")
        if url:
            return url
    return None

# ── Data loading ────────────────────────────────────────────────────────────

def find_latest_briefing() -> Path | None:
    if not BRIEFINGS_DIR.exists():
        return None
    files = sorted(BRIEFINGS_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None

def load_json(path: Path) -> dict:
    return json.loads(path.read_text())

@st.cache_data(show_spinner=False)
def load_formulary() -> list[dict]:
    if not FORMULARY_PATH.exists():
        return []
    return load_json(FORMULARY_PATH).get("drugs", [])

@st.cache_data(show_spinner=False)
def load_orders_index() -> dict:
    if not ORDERS_PATH.exists():
        return {}
    data = load_json(ORDERS_PATH)
    return {str(o["rxcui"]): o for o in data.get("orders", [])}

# ── HITL action logging ─────────────────────────────────────────────────────

def log_action(briefing_path: Path, item_id: str, action: str, reason: str | None = None) -> None:
    run = load_json(briefing_path)
    for item in run["items"]:
        if item["item_id"] == item_id:
            item["user_action"] = action
            item["user_action_timestamp"] = datetime.now(timezone.utc).isoformat()
            if reason:
                item["user_action_reason"] = reason
            break
    briefing_path.write_text(json.dumps(run, indent=2))

# ── Re-run pipeline ─────────────────────────────────────────────────────────

def run_briefing_cli() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "src.briefing"],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "Briefing exceeded 10-minute timeout."
    if result.returncode == 0:
        return True, result.stdout.strip() or "Briefing complete."
    err = (result.stderr or result.stdout or "").strip()
    return False, err or "Briefing failed (no stderr)."

def run_briefing_with_status() -> bool:
    with st.status("Running briefing…", expanded=True) as status:
        status.write("Fetching FDA shortage data…")
        ok, msg = run_briefing_cli()
        if ok:
            status.update(label="Briefing complete.", state="complete")
            status.write(msg)
            return True
        status.update(label="Briefing failed.", state="error")
        status.code(msg, language="text")
        return False

# ── Briefing item rendering ─────────────────────────────────────────────────

def render_collapsed_card(item: dict, briefing_path: Path) -> None:
    severity = item.get("severity", "Watch")
    sev_cls = severity.lower() if severity.lower() in ("critical", "watch", "resolved") else "watch"
    drug = item.get("drug_name", "Unknown")
    summary = item.get("summary", "")
    action = item.get("recommended_action", "")
    confidence = item.get("confidence", "low")
    cite_url = primary_citation_url(item)
    user_action = item.get("user_action")

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
            f'Source: <a href="{html.escape(cite_url)}" target="_blank" rel="noopener">FDA shortage record</a>'
            f'</div>'
        )
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)

    if not user_action:
        render_action_row(item, briefing_path)

    with st.expander("Details + citations"):
        render_drilldown(item)

def render_action_row(item: dict, briefing_path: Path) -> None:
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

# ── Briefing tab ────────────────────────────────────────────────────────────

def render_briefing_tab() -> None:
    hcol1, hcol2 = st.columns([4, 1])
    hcol1.title("Rx Shortage Intelligence")
    rerun_clicked = hcol2.button("Re-run briefing", use_container_width=True)

    st.markdown(
        '<div class="rx-demo-banner">'
        '<span class="rx-demo-chip">DEMO</span>'
        '<span>Formulary and active orders are synthetic. '
        'FDA shortage feed and RxNorm are live public data.</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    if rerun_clicked:
        if run_briefing_with_status():
            st.rerun()
        return

    path = find_latest_briefing()
    if path is None:
        st.info(
            "No briefing for today yet. Click **Re-run briefing** to fetch the latest "
            "FDA shortage data — takes about 45 seconds."
        )
        return

    run = load_json(path)
    items = run.get("items", []) or []

    counts = {"Critical": 0, "Watch": 0, "Resolved": 0}
    for it in items:
        sev = it.get("severity", "Watch")
        if sev in counts:
            counts[sev] += 1

    sub = st.empty()
    run_ts = format_timestamp(run.get("run_timestamp", ""))
    sub.subheader(f"Morning Briefing — {run_ts}")

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

# ── Formulary tab ───────────────────────────────────────────────────────────

STATUS_COLORS = {
    "preferred":     ("#15803D", "#F0FDF4"),
    "restricted":    ("#B45309", "#FFFBEB"),
    "non-preferred": ("#6B7280", "#F3F4F6"),
    "non-formulary": ("#374151", "#E5E7EB"),
}

def get_briefing_shortage_index() -> tuple[dict, dict]:
    """Return (rxcui_idx, name_idx) from latest briefing items.

    rxcui_idx: rxcui -> match dict
    name_idx:  lowercase-name-token -> match dict (fallback when RxCUI concept levels differ)
    """
    path = find_latest_briefing()
    if not path:
        return {}, {}
    run = load_json(path)
    rxcui_idx: dict = {}
    name_idx: dict = {}
    for item in run.get("items", []) or []:
        match = {
            "severity":   item.get("severity", "Watch"),
            "summary":    item.get("summary", ""),
            "citation":   primary_citation_url(item),
            "item_id":    item.get("item_id", ""),
        }
        rxcui = str(item.get("rxcui", ""))
        if rxcui:
            rxcui_idx[rxcui] = match
        name = (item.get("drug_name") or "").lower().strip()
        if name:
            name_idx[name.split()[0]] = match
    return rxcui_idx, name_idx

def find_shortage_match(drug: dict, rxcui_idx: dict, name_idx: dict):
    rxcui_list = drug.get("rxcui_list") or [drug.get("rxcui")]
    for r in rxcui_list:
        if str(r) in rxcui_idx:
            return rxcui_idx[str(r)]
    drug_name = (drug.get("name") or "").lower()
    for token, match in name_idx.items():
        if token and token in drug_name:
            return match
    return None

def render_formulary_tab() -> None:
    st.title("Formulary")
    st.markdown(
        '<div class="rx-meta-row">Memorial Health System · 30 drugs · '
        'Cross-referenced against today\'s FDA shortage feed</div>',
        unsafe_allow_html=True,
    )

    drugs = load_formulary()
    if not drugs:
        st.info("No formulary loaded. Run `python -m src.data_loader` to bootstrap.")
        return

    orders_idx = load_orders_index()
    rxcui_idx, name_idx = get_briefing_shortage_index()

    rows = []
    for d in drugs:
        match = find_shortage_match(d, rxcui_idx, name_idx)
        primary_rxcui = str(d.get("rxcui", ""))
        order_rec = orders_idx.get(primary_rxcui, {})
        rows.append({
            "Drug":           d.get("name", ""),
            "Route":          (d.get("route_of_administration") or "").title(),
            "Status":         d.get("formulary_status", ""),
            "Restriction":    d.get("restriction_criteria") or "—",
            "Orders (30d)":   order_rec.get("count_last_30_days", 0),
            "Shortage today": match["severity"] if match else "—",
            "RxCUI":          primary_rxcui,
        })
    df = pd.DataFrame(rows)

    affected_count = sum(1 for r in rows if r["Shortage today"] != "—")
    critical_count = sum(1 for r in rows if r["Shortage today"] == "Critical")

    m1, m2, m3 = st.columns(3)
    m1.metric("Total formulary", len(rows))
    m2.metric("Affected today", affected_count)
    m3.metric("Critical", critical_count)
    st.divider()

    f1, f2, f3 = st.columns(3)
    routes = sorted({r["Route"] for r in rows if r["Route"]})
    statuses = sorted({r["Status"] for r in rows if r["Status"]})
    shortage_filter = ["Critical", "Watch", "Resolved", "—"]
    sel_route = f1.multiselect("Route", routes, default=[])
    sel_status = f2.multiselect("Formulary status", statuses, default=[])
    sel_shortage = f3.multiselect("Shortage status", shortage_filter, default=[])

    filtered = df.copy()
    if sel_route:
        filtered = filtered[filtered["Route"].isin(sel_route)]
    if sel_status:
        filtered = filtered[filtered["Status"].isin(sel_status)]
    if sel_shortage:
        filtered = filtered[filtered["Shortage today"].isin(sel_shortage)]

    severity_order = {"Critical": 0, "Watch": 1, "Resolved": 2, "—": 3}
    filtered = filtered.assign(
        _sev_rank=filtered["Shortage today"].map(severity_order).fillna(3)
    ).sort_values(by=["_sev_rank", "Drug"]).drop(columns=["_sev_rank"])

    st.markdown(f"**{len(filtered)} drugs**")
    selection = st.dataframe(
        filtered,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Drug":           st.column_config.TextColumn("Drug", width="medium"),
            "Route":          st.column_config.TextColumn("Route", width="small"),
            "Status":         st.column_config.TextColumn("Status", width="small"),
            "Restriction":    st.column_config.TextColumn("Restriction", width="medium"),
            "Orders (30d)":   st.column_config.NumberColumn("Orders (30d)", width="small"),
            "Shortage today": st.column_config.TextColumn("Shortage today", width="small"),
            "RxCUI":          st.column_config.TextColumn("RxCUI", width="small"),
        },
        key="formulary-table",
    )

    selected_rows = selection.selection.rows if selection and selection.selection else []
    if selected_rows and selected_rows[0] < len(filtered):
        idx = selected_rows[0]
        selected_rxcui = filtered.iloc[idx]["RxCUI"]
        st.divider()
        render_drug_drilldown(selected_rxcui, drugs, orders_idx, rxcui_idx, name_idx)

def render_drug_drilldown(rxcui: str, drugs: list[dict], orders_idx: dict, rxcui_idx: dict, name_idx: dict) -> None:
    drug = next((d for d in drugs if str(d.get("rxcui")) == str(rxcui)), None)
    if not drug:
        st.warning("Drug not found in formulary.")
        return

    st.subheader(drug.get("name", "Unknown"))
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("**Formulary record**")
        status_color, status_bg = STATUS_COLORS.get(drug.get("formulary_status", ""), ("#6B7280", "#F3F4F6"))
        status_html = (
            f'<span style="background:{status_bg};color:{status_color};'
            f'padding:2px 8px;border-radius:3px;font-size:12px;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.04em;">'
            f'{html.escape(drug.get("formulary_status", "—"))}</span>'
        )
        st.markdown(
            f"- **Status:** {status_html}\n"
            f"- **Route:** {(drug.get('route_of_administration') or '—').title()}\n"
            f"- **Class:** {drug.get('therapeutic_class') or '—'}\n"
            f"- **Restriction:** {drug.get('restriction_criteria') or 'None'}\n"
            f"- **Last P&T review:** {drug.get('last_pt_review_date') or '—'}\n"
            f"- **RxCUI:** `{drug.get('rxcui')}`",
            unsafe_allow_html=True,
        )
        prefs = drug.get("preferred_alternatives") or []
        if prefs:
            st.markdown("**Preferred alternatives**")
            for p in prefs:
                st.markdown(f"- {html.escape(str(p))}")

    with col_r:
        st.markdown("**Operational context**")
        order_rec = orders_idx.get(str(rxcui), {})
        order_count = order_rec.get("count_last_30_days", 0)
        depts = ", ".join(order_rec.get("departments", []) or []) or "—"
        st.markdown(
            f"- **Active orders (30d):** {order_count}\n"
            f"- **Departments:** {depts}"
        )

        match = find_shortage_match(drug, rxcui_idx, name_idx)

        if match:
            sev_html = severity_badge(match["severity"])
            cite = match.get("citation")
            cite_link = f' · [FDA source]({cite})' if cite else ""
            st.markdown(
                f"**Shortage today:** {sev_html}{cite_link}",
                unsafe_allow_html=True,
            )
            st.markdown(f"_{html.escape(match['summary'])}_")
        else:
            st.markdown("**Shortage today:** Clear")

# ── Eval tab ────────────────────────────────────────────────────────────────

def render_eval_tab() -> None:
    st.title("Eval — 15-case scoring")
    st.caption("Internal quality scoring · pharmacy operations review · not for clinical use.")

    eval_path = DATA_DIR / "eval_results.json"
    if not eval_path.exists():
        st.info("No eval results found. Run: `python -m src.eval.runner`")
        if st.button("Run eval now"):
            with st.status("Running eval…", expanded=True) as status:
                result = subprocess.run(
                    [sys.executable, "-m", "src.eval.runner"],
                    capture_output=True, text=True, timeout=60,
                )
            if result.returncode == 0:
                status.update(label="Eval complete.", state="complete")
                st.rerun()
            else:
                st.error(result.stderr[:500])
        return

    eval_data = load_json(eval_path)
    v1 = eval_data.get("v1", {})
    agg = v1.get("aggregate", {})

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Severity acc",  f"{agg.get('severity_accuracy', 0):.0%}")
    m2.metric("Citation acc",  f"{agg.get('citation_accuracy', 0):.0%}")
    m3.metric("Hallucination", f"{agg.get('hallucination_rate', 0):.0%}")
    m4.metric("Recall",        f"{agg.get('recall', 0):.0%}")
    m5.metric("Clinical appr.", f"{agg.get('clinical_appropriateness', 0):.1f}/5")

    st.markdown(
        '<div class="rx-stat-target">'
        'Targets: Severity ≥90% · Citation 100% · Hallucination &lt;2% · Recall 100% · Clinical ≥4'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption("Clinical appropriateness is stubbed at 4.0 for v0.1. Wire Claude-as-judge in v0.2.")

    results = v1.get("results", []) or []
    st.subheader("Case results")
    st.caption("✓ = matched expected · ✗ = mismatch or not found")

    if not results:
        st.info("No case results in eval_results.json.")
        return

    rows = []
    for r in results:
        s = r.get("scores", {})
        rows.append({
            "Case":          r.get("case_id", ""),
            "Drug":          r.get("drug_name", ""),
            "Expected":      r.get("expected_severity", ""),
            "Actual":        r.get("actual_severity", ""),
            "Severity":      "✓" if s.get("severity_accuracy", 0) == 1.0 else "✗",
            "Citations":     "✓" if s.get("citation_accuracy", 0) == 1.0 else "✗",
            "Hallucination": "clean" if s.get("hallucination_rate", 0) == 0.0 else "detected",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    render_theme()
    tab_briefing, tab_formulary, tab_eval = st.tabs(["Briefing", "Formulary", "Eval"])
    with tab_briefing:
        render_briefing_tab()
    with tab_formulary:
        render_formulary_tab()
    with tab_eval:
        render_eval_tab()


if __name__ == "__main__":
    main()
