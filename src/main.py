"""
Rx Shortage Intelligence — Streamlit dashboard.

Pattern B: 100% sync. Reads data/briefings/YYYY-MM-DD.json.
Re-run button spawns CLI subprocess, then reloads.

Run: streamlit run src/main.py
"""

import streamlit as st

from src.ui.theme import render_theme
from src.ui.briefing_view import render_briefing_tab
from src.ui.formulary_view import render_formulary_tab
from src.ui.eval_view import render_eval_tab

# ── Config ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

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
