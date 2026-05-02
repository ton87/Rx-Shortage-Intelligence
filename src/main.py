"""Rx Shortage Intelligence — Streamlit dashboard entry point.

Pattern B: 100% sync. CLI generates briefing JSON; UI reads it.
See CLAUDE.md "Architecture: briefing CLI + Streamlit reader" for rationale.
"""

import sys
from pathlib import Path

# `streamlit run src/main.py` puts src/ on sys.path, not the project root, so
# the absolute `from src.*` imports below would otherwise fail at startup.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from src.ui.briefing_view import render_briefing_tab  # noqa: E402
from src.ui.eval_view import render_eval_tab  # noqa: E402
from src.ui.formulary_view import render_formulary_tab  # noqa: E402
from src.ui.orders_view import render_orders_tab  # noqa: E402
from src.ui.theme import render_theme  # noqa: E402

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    render_theme()
    tab_briefing, tab_formulary, tab_orders, tab_eval = st.tabs(
        ["Briefing", "Formulary", "Active Orders", "Eval"]
    )
    with tab_briefing:
        render_briefing_tab()
    with tab_formulary:
        render_formulary_tab()
    with tab_orders:
        render_orders_tab()
    with tab_eval:
        render_eval_tab()


if __name__ == "__main__":
    main()
