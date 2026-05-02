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
from pathlib import Path

import pandas as pd
import streamlit as st

from src.domain.severity import SEVERITY_RANK
from src.domain.constants import BRIEFING_SUBPROCESS_TIMEOUT_S
from src.domain.matching import (
    build_shortage_index,
    find_shortage_match,
)
from src.io_.briefing_store import (
    find_latest_briefing,
    load_briefing,
)
from src.ui.theme import render_theme
from src.ui.components import severity_badge
from src.ui.briefing_view import render_briefing_tab

# ── Config ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

DATA_DIR = Path(__file__).parent.parent / "data"

# ── Data loading (formulary + orders) ───────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_formulary() -> list[dict]:
    from src.io_.data_loader import load_formulary as _load
    return _load()

@st.cache_data(show_spinner=False)
def load_orders_index() -> dict:
    from src.io_.data_loader import load_orders_index as _load
    return _load()

# ── Formulary tab ───────────────────────────────────────────────────────────

STATUS_COLORS = {
    "preferred":     ("#15803D", "#F0FDF4"),
    "restricted":    ("#B45309", "#FFFBEB"),
    "non-preferred": ("#6B7280", "#F3F4F6"),
    "non-formulary": ("#374151", "#E5E7EB"),
}

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
    path = find_latest_briefing()
    items = load_briefing(path).get("items", []) if path else []
    rxcui_idx, name_idx = build_shortage_index(items)

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

    severity_order = {**SEVERITY_RANK, "—": 3}
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
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "src.eval.runner"],
                        capture_output=True, text=True, timeout=BRIEFING_SUBPROCESS_TIMEOUT_S,
                    )
                except subprocess.TimeoutExpired:
                    status.update(label="Eval timed out (>10 min).", state="error")
                    return
            if result.returncode == 0:
                status.update(label="Eval complete.", state="complete")
                if result.stdout.strip():
                    status.code(result.stdout, language="text")
                st.rerun()
            else:
                status.update(label="Eval failed.", state="error")
                err = (result.stderr or result.stdout or "(no output)").strip()
                status.code(err, language="text")
        return

    eval_data = load_briefing(eval_path)
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
