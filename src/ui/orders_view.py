"""Active Orders tab renderer.

Shows synthetic active orders cross-referenced against today's shortage feed.
Row-click drill-down reuses render_drug_drilldown from formulary_view.
"""

import pandas as pd
import streamlit as st

from src.domain.severity import SEVERITY_RANK
from src.domain.matching import build_shortage_index, find_shortage_match
from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.ui.formulary_view import load_formulary, load_orders_index, render_drug_drilldown


def render_orders_tab() -> None:
    st.title("Active Orders")
    st.markdown(
        '<div class="rx-meta-row">Memorial Health System · Last 30 days · '
        'Cross-referenced against today\'s FDA shortage feed</div>',
        unsafe_allow_html=True,
    )

    orders_idx = load_orders_index()
    if not orders_idx:
        st.info("No orders loaded. Run `python -m src.io_.data_loader` to bootstrap.")
        return

    drugs = load_formulary()
    drug_by_rxcui = {str(d.get("rxcui", "")): d for d in drugs}

    path = find_latest_briefing()
    items = load_briefing(path).get("items", []) if path else []
    rxcui_idx, name_idx = build_shortage_index(items)

    rows = []
    for rxcui_str, order_rec in orders_idx.items():
        drug = drug_by_rxcui.get(rxcui_str, {})
        drug_name = drug.get("name") or f"RxCUI {rxcui_str}"
        match = find_shortage_match(drug, rxcui_idx, name_idx) if drug else rxcui_idx.get(rxcui_str)
        departments = order_rec.get("departments", []) or []
        rows.append({
            "Drug":         drug_name,
            "RxCUI":        rxcui_str,
            "Orders (30d)": order_rec.get("count_last_30_days", 0),
            "Departments":  ", ".join(departments) if departments else "—",
            "Shortage":     match["severity"] if match else "—",
        })

    total_vol = sum(r["Orders (30d)"] for r in rows)
    shortage_rows = [r for r in rows if r["Shortage"] != "—"]
    critical_rows = [r for r in rows if r["Shortage"] == "Critical"]
    impacted_vol = sum(r["Orders (30d)"] for r in shortage_rows)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Order volume (30d)", f"{total_vol:,}")
    m2.metric("Drugs ordered", len(rows))
    m3.metric("On shortage", len(shortage_rows))
    m4.metric("Critical-drug orders (30d)", f"{sum(r['Orders (30d)'] for r in critical_rows):,}")

    if total_vol:
        st.markdown(
            f'<div class="rx-stat-target">'
            f'{impacted_vol:,} of {total_vol:,} orders ({impacted_vol / total_vol:.0%}) '
            f'touch a drug in active shortage</div>',
            unsafe_allow_html=True,
        )
    st.divider()

    df = pd.DataFrame(rows)

    all_depts: set[str] = set()
    for r in rows:
        if r["Departments"] != "—":
            for dept in r["Departments"].split(", "):
                all_depts.add(dept.strip())

    f1, f2 = st.columns(2)
    sel_shortage = f1.multiselect(
        "Shortage status", ["Critical", "Watch", "Resolved", "—"],
        default=[], key="orders-shortage-filter",
    )
    sel_dept = f2.multiselect(
        "Department", sorted(all_depts),
        default=[], key="orders-dept-filter",
    )

    filtered = df.copy()
    if sel_shortage:
        filtered = filtered[filtered["Shortage"].isin(sel_shortage)]
    if sel_dept:
        filtered = filtered[filtered["Departments"].apply(
            lambda x: any(d in x for d in sel_dept)
        )]

    severity_order = {**SEVERITY_RANK, "—": 3}
    filtered = (
        filtered
        .assign(_sev_rank=filtered["Shortage"].map(severity_order).fillna(3))
        .sort_values(by=["_sev_rank", "Orders (30d)"], ascending=[True, False])
        .drop(columns=["_sev_rank"])
    )

    st.markdown(f"**{len(filtered)} drugs**")
    selection = st.dataframe(
        filtered,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Drug":         st.column_config.TextColumn("Drug", width="medium"),
            "RxCUI":        st.column_config.TextColumn("RxCUI", width="small"),
            "Orders (30d)": st.column_config.NumberColumn("Orders (30d)", width="small"),
            "Departments":  st.column_config.TextColumn("Departments", width="medium"),
            "Shortage":     st.column_config.TextColumn("Shortage", width="small"),
        },
        key="orders-table",
    )

    selected_rows = selection.selection.rows if selection and selection.selection else []
    if selected_rows and selected_rows[0] < len(filtered):
        idx = selected_rows[0]
        selected_rxcui = filtered.iloc[idx]["RxCUI"]
        st.divider()
        render_drug_drilldown(selected_rxcui, drugs, orders_idx, rxcui_idx, name_idx)
