"""Rx Shortage Intelligence — Streamlit dashboard entry point.

Pattern B: 100% sync. CLI generates briefing JSON; UI reads it.
See CLAUDE.md "Architecture: briefing CLI + Streamlit reader" for rationale.
"""

import streamlit as st

from src.ui.briefing_view import render_briefing_tab
from src.ui.eval_view import render_eval_tab
from src.ui.formulary_view import render_formulary_tab
from src.ui.theme import render_theme

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
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
