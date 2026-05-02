"""Streamlit theme injection. CSS lives in theme.css — no Python escaping pain."""

from pathlib import Path

import streamlit as st

CSS_PATH = Path(__file__).parent / "theme.css"


@st.cache_resource
def _css_text() -> str:
    return CSS_PATH.read_text()


def render_theme() -> None:
    """Inject the project CSS once per session. Cached, so reruns don't re-read."""
    st.markdown(f"<style>{_css_text()}</style>", unsafe_allow_html=True)
