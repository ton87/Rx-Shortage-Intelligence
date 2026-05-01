"""
POC: eval tab — 15-case grid with 5-dim scoring.

Run: streamlit run research/05-streamlit-ui/POC-eval-tab.py

Demonstrates:
- Pandas dataframe with conditional formatting
- Aggregate metrics
- v1 vs v2 placeholder
"""

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Eval — POC", layout="wide")

MOCK_CASES = [
    {"id": "C-01", "drug": "cisplatin",       "expected_sev": "Critical", "actual_sev": "Critical", "clin_appropriate": 5, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-02", "drug": "methotrexate",    "expected_sev": "Critical", "actual_sev": "Watch",    "clin_appropriate": 3, "citation_acc": 1.0, "hallucinated": False, "sev_match": False, "recall_hit": True},
    {"id": "C-03", "drug": "vincristine",     "expected_sev": "Resolved", "actual_sev": "Resolved", "clin_appropriate": 5, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-04", "drug": "carboplatin",     "expected_sev": "Watch",    "actual_sev": "Watch",    "clin_appropriate": 4, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-05", "drug": "morphine_inj",    "expected_sev": "Critical", "actual_sev": "Critical", "clin_appropriate": 5, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-06", "drug": "amoxicillin_iv",  "expected_sev": "Watch",    "actual_sev": "Watch",    "clin_appropriate": 4, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-07", "drug": "fentanyl_patch",  "expected_sev": "Resolved", "actual_sev": "Resolved", "clin_appropriate": 5, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-08", "drug": "albuterol_neb",   "expected_sev": "Watch",    "actual_sev": "Watch",    "clin_appropriate": 4, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-09", "drug": "lidocaine_iv",    "expected_sev": "Critical", "actual_sev": "Critical", "clin_appropriate": 5, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-10", "drug": "heparin_unfx",    "expected_sev": "Critical", "actual_sev": "Critical", "clin_appropriate": 4, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-11", "drug": "epinephrine",     "expected_sev": "Critical", "actual_sev": "Critical", "clin_appropriate": 5, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-12", "drug": "ibuprofen_oral",  "expected_sev": "Watch",    "actual_sev": "Watch",    "clin_appropriate": 4, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-13", "drug": "ondansetron",     "expected_sev": "Watch",    "actual_sev": "Watch",    "clin_appropriate": 5, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
    {"id": "C-14", "drug": "diphenhydramine", "expected_sev": "Resolved", "actual_sev": "Watch",    "clin_appropriate": 3, "citation_acc": 1.0, "hallucinated": False, "sev_match": False, "recall_hit": True},
    {"id": "C-15", "drug": "acetaminophen",   "expected_sev": "Watch",    "actual_sev": "Watch",    "clin_appropriate": 4, "citation_acc": 1.0, "hallucinated": False, "sev_match": True, "recall_hit": True},
]

st.title("Eval Harness — 15 cases × 5 dimensions")

df = pd.DataFrame(MOCK_CASES)

# Aggregate
clin = df["clin_appropriate"].mean() * 20  # 1-5 scale → 0-100%
cite = df["citation_acc"].mean() * 100
hall = df["hallucinated"].mean() * 100
sev = df["sev_match"].mean() * 100
rec = df["recall_hit"].mean() * 100

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Clinical appropriateness", f"{clin:.0f}%", delta="≥90% target")
m2.metric("Citation accuracy", f"{cite:.0f}%", delta="100% target")
m3.metric("Hallucination rate", f"{hall:.1f}%", delta="<2% target", delta_color="inverse")
m4.metric("Severity accuracy", f"{sev:.0f}%")
m5.metric("Recall (formulary-affecting)", f"{rec:.0f}%", delta="100% target")

st.divider()

st.subheader("Case-by-case results")

# Color function for sev_match
def style_sev(row):
    return ["background-color: #ffeeee" if not row["sev_match"] else "" for _ in row]

st.dataframe(
    df.style.apply(style_sev, axis=1),
    use_container_width=True,
    hide_index=True,
)

st.divider()

st.subheader("v1 vs v2 prompt comparison")
st.info("v1 prompt scores shown above. v2 prompt hook scaffolded but not yet exercised in v0.1.")

vc1, vc2 = st.columns(2)
vc1.markdown("**v1 (current)**")
vc1.write(f"- Clinical: {clin:.0f}%")
vc1.write(f"- Severity: {sev:.0f}%")
vc1.write(f"- Hallucination: {hall:.1f}%")

vc2.markdown("**v2 (placeholder)**")
vc2.write("_Run `python -m src.eval.runner --prompt-version=v2` to populate_")
