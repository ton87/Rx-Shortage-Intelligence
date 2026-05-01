"""
POC: agent reasoning + tool-call trace panel.

Run: streamlit run research/05-streamlit-ui/POC-drilldown-trace.py

Demonstrates:
- st.status streaming for live agent runs
- Tool-call log rendered like a developer console
- Citation chips clickable
"""

import time
import streamlit as st

st.set_page_config(page_title="Drill-down trace POC", layout="wide")

MOCK_TOOL_CALLS = [
    {"server": "fda_shortage", "tool": "get_shortage_detail", "args": {"rxcui": "2555"}, "duration_ms": 245, "result": "status=Current; 1 record returned"},
    {"server": "drug_label", "tool": "get_drug_label_sections", "args": {"rxcui": "2555", "sections": ["indications_and_usage", "warnings"]}, "duration_ms": 412, "result": "2 sections, 1843 tokens"},
    {"server": "rxnorm", "tool": "get_therapeutic_alternatives", "args": {"rxcui": "2555"}, "duration_ms": 298, "result": "ATC class L01XA, 4 members"},
    {"server": "drug_label", "tool": "get_drug_label_sections", "args": {"rxcui": "40048", "sections": ["contraindications"]}, "duration_ms": 189, "result": "1 section, 521 tokens"},
]

st.title("Drill-down: Cisplatin (RxCUI 2555)")

# Live re-run simulation
if st.button("▶ Simulate live agent run"):
    with st.status("Running agent for cisplatin...", expanded=True) as status:
        for tc in MOCK_TOOL_CALLS:
            time.sleep(0.4)
            st.write(f"→ `{tc['server']}.{tc['tool']}({tc['args']})`")
            time.sleep(0.1)
            st.caption(f"  ← {tc['result']} ({tc['duration_ms']}ms)")
        status.update(label="✓ Agent run complete (1144ms total)", state="complete")

st.divider()

# Static trace panel
st.subheader("Tool calls (audit log)")

for i, tc in enumerate(MOCK_TOOL_CALLS, 1):
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        c1.code(f"{tc['server']}.{tc['tool']}({tc['args']})", language="python")
        c2.caption(f"{tc['duration_ms']}ms")
        c1.caption(f"Result: {tc['result']}")

st.divider()

st.subheader("Reasoning chain")
st.markdown("""
1. **Identified shortage**: cisplatin (RxCUI 2555) is currently in shortage per FDA.
2. **Checked formulary**: cisplatin is preferred-status, IV-only, restricted to oncology.
3. **Looked up alternatives**: queried ATC class L01XA → 4 members (carboplatin, oxaliplatin, satraplatin, picoplatin).
4. **Filtered alternatives**: carboplatin matches IV route + on formulary. Oxaliplatin different indication. Others not on formulary.
5. **Severity verdict**: Critical (high active orders + restrictive route + no in-stock alternative would be Critical, but carboplatin available → could be Watch). Rule classifier says Critical because pre-classification doesn't account for the alternative match.
6. **Confidence**: high. Tool calls returned exact RxCUI matches.
""")

st.subheader("Citations")
st.markdown("""
- **Currently in shortage** — [api.fda.gov/drug/shortages.json?search=openfda.rxcui:2555](#)
- **IV-only formulary status** — `data/synthetic_formulary.json` entry for RxCUI 2555
- **Carboplatin in same ATC class** — [rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json?rxcui=2555](#)
- **Carboplatin contraindications** — [api.fda.gov/drug/label.json?search=openfda.rxcui:40048](#)
""")
