"""Rx Shortage Intelligence — Streamlit dashboard entry point.

Pattern B: 100% sync. CLI generates briefing JSON; UI reads it.
See CLAUDE.md "Architecture: briefing CLI + Streamlit reader" for rationale.
"""

import sys
from pathlib import Path

# `streamlit run src/main.py` puts src/ on sys.path, not the project root, so
# the absolute `from src.*` imports below would otherwise fail at startup.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import base64  # noqa: E402

import streamlit as st  # noqa: E402

from src.ui.briefing_view import render_briefing_tab  # noqa: E402
from src.ui.eval_view import render_eval_tab  # noqa: E402
from src.ui.formulary_view import render_formulary_tab  # noqa: E402
from src.ui.orders_view import render_orders_tab  # noqa: E402
from src.ui.theme import render_theme  # noqa: E402

_LOGO_PATH   = Path(__file__).parent / "assets" / "logo.png"
_AVATAR_PATH = Path(__file__).parent / "assets" / "avatar.png"

# ── User profile (static for v0.1 demo) ──────────────────────────────────────
_USER_NAME = "averenitch"
_USER_ROLE = "Pharmacist"


def _render_header() -> None:
    """Full-width header row: logo left, user profile right, same baseline."""
    # Logo
    logo_b64 = ""
    if _LOGO_PATH.exists():
        logo_b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode()

    # Avatar — real photo or initials fallback
    if _AVATAR_PATH.exists():
        av_b64 = base64.b64encode(_AVATAR_PATH.read_bytes()).decode()
        avatar_html = (
            f'<img src="data:image/png;base64,{av_b64}" alt="{_USER_NAME}" '
            f'style="width:48px;height:48px;border-radius:50%;object-fit:cover;'
            f'border:2px solid #dce3ed;flex-shrink:0;"/>'
        )
    else:
        avatar_html = (
            f'<div style="width:48px;height:48px;border-radius:50%;background:#1C3561;'
            f'display:flex;align-items:center;justify-content:center;'
            f'color:white;font-weight:700;font-size:16px;flex-shrink:0;">AV</div>'
        )

    logo_html = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="Anton Hospital" '
        f'height="130" style="display:block; margin-left:-48px;"/>'
        if logo_b64 else ""
    )

    st.markdown(
        f"""
        <div style="
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 0 8px 0;
        ">
            {logo_html}
            <div style="display:flex; align-items:center; gap:12px; padding-right:4px;">
                <div style="text-align:right; line-height:1.3;">
                    <div style="font-size:14px; font-weight:700; color:#1C3561;">{_USER_NAME}</div>
                    <div style="font-size:12px; color:#5E7BA4;">{_USER_ROLE}</div>
                </div>
                {avatar_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    render_theme()
    _render_header()
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
