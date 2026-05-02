"""
Rx Shortage Intelligence — Streamlit dashboard.

Pattern B: 100% sync. Reads data/briefings/YYYY-MM-DD.json.
Re-run button spawns CLI subprocess, then reloads.

Run: streamlit run src/main.py
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from src.domain.constants import BRIEFING_SUBPROCESS_TIMEOUT_S
from src.io_.briefing_store import load_briefing
from src.ui.theme import render_theme
from src.ui.briefing_view import render_briefing_tab
from src.ui.formulary_view import render_formulary_tab

# ── Config ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

DATA_DIR = Path(__file__).parent.parent / "data"

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
