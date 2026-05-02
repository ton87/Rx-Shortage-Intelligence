"""Formulary tab renderer.

Owns render_formulary_tab, render_drug_drilldown, and the
@st.cache_data wrappers for formulary + orders data loading.
"""

import html

import pandas as pd
import streamlit as st

from src.domain.severity import SEVERITY_RANK
from src.domain.matching import build_shortage_index, find_shortage_match
from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.ui.components import formulary_status_badge, severity_badge


@st.cache_data(show_spinner=False)
def load_formulary() -> list[dict]:
    from src.io_.data_loader import load_formulary as _load
    return _load()


@st.cache_data(show_spinner=False)
def load_orders_index() -> dict:
    from src.io_.data_loader import load_orders_index as _load
    return _load()


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
        status_html = formulary_status_badge(drug.get("formulary_status"))
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
