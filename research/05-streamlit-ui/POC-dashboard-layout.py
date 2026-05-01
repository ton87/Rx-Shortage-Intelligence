"""
POC: Streamlit dashboard layout — severity-ordered briefing, mocked data.

Run: streamlit run research/05-streamlit-ui/POC-dashboard-layout.py

Renders FR-11 visual scan order:
  Top stats → severity-ordered items → expandable detail
"""

import streamlit as st

st.set_page_config(page_title="Rx Shortage Intelligence — POC", layout="wide")

MOCK_BRIEFING = {
    "run_timestamp": "2026-04-30T08:00:00Z",
    "items": [
        {
            "item_id": "1",
            "drug_name": "Cisplatin",
            "rxcui": "2555",
            "severity": "Critical",
            "summary": "23 active oncology orders, IV-only, no formulary alternative.",
            "rationale": "Cisplatin shortage continues per FDA. Active orders concentrated in Oncology dept (23 in last 30 days). Formulary lists no preferred alternative for this RxCUI in IV form.",
            "alternatives": [
                {"name": "Carboplatin", "rxcui": "40048", "rationale": "Same ATC class L01XA, IV route match, on formulary as preferred", "source_url": "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json?rxcui=2555"},
            ],
            "citations": [
                {"claim": "Currently in shortage", "source_url": "https://api.fda.gov/drug/shortages.json?search=openfda.rxcui:2555"},
                {"claim": "Carboplatin in same class", "source_url": "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json?rxcui=2555"},
            ],
            "confidence": "high",
            "recommended_action": "Switch new orders to carboplatin pending P&T review",
        },
        {
            "item_id": "2",
            "drug_name": "Methotrexate",
            "rxcui": "6851",
            "severity": "Watch",
            "summary": "8 active orders, alternative on formulary.",
            "rationale": "New shortage today. Active orders moderate. Methotrexate PO available as substitute for IV in non-oncology indications.",
            "alternatives": [
                {"name": "Methotrexate PO", "rxcui": "6852", "rationale": "Oral form not in shortage; restricted to non-oncology", "source_url": "..."},
            ],
            "citations": [{"claim": "FDA shortage record", "source_url": "..."}],
            "confidence": "medium",
            "recommended_action": "Continue current orders; flag for prescriber review",
        },
        {
            "item_id": "3",
            "drug_name": "Vincristine",
            "rxcui": "11202",
            "severity": "Resolved",
            "summary": "No longer in FDA shortage feed.",
            "rationale": "Was in yesterday's snapshot, not in today's feed.",
            "alternatives": [],
            "citations": [{"claim": "Resolved status", "source_url": "..."}],
            "confidence": "high",
            "recommended_action": "Acknowledge resolution; no action needed",
        },
    ],
    "total_tokens_used": 18432,
    "total_cost_usd": 0.087,
    "latency_ms": 47200,
}


def severity_emoji(s: str) -> str:
    return {"Critical": "🔴", "Watch": "🟡", "Resolved": "🟢"}.get(s, "⚪")


def severity_rank(s: str) -> int:
    return {"Critical": 0, "Watch": 1, "Resolved": 2}.get(s, 99)


# === Header ===
col1, col2, col3 = st.columns([3, 2, 1])
col1.title("Rx Shortage Intelligence")
col2.markdown(f"**Run**: {MOCK_BRIEFING['run_timestamp']}")
if col3.button("Re-run", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# === Stats ===
counts = {"Critical": 0, "Watch": 0, "Resolved": 0}
for it in MOCK_BRIEFING["items"]:
    counts[it["severity"]] += 1

s1, s2, s3, s4 = st.columns(4)
s1.metric("🔴 Critical", counts["Critical"])
s2.metric("🟡 Watch", counts["Watch"])
s3.metric("🟢 Resolved", counts["Resolved"])
s4.metric("Latency", f"{MOCK_BRIEFING['latency_ms'] / 1000:.1f}s")

st.divider()

# === Severity-ordered items ===
items = sorted(MOCK_BRIEFING["items"], key=lambda x: severity_rank(x["severity"]))

for item in items:
    with st.container(border=True):
        a, b = st.columns([4, 1])
        a.markdown(f"{severity_emoji(item['severity'])} **{item['severity'].upper()}** — **{item['drug_name']}** (RxCUI {item['rxcui']})")
        a.write(item["summary"])
        a.caption(f"→ {item['recommended_action']}")
        b.write(f"Confidence: **{item['confidence']}**")

        with st.expander("Show reasoning + citations"):
            st.markdown("**Rationale**")
            st.write(item["rationale"])

            if item["alternatives"]:
                st.markdown("**Alternatives**")
                for alt in item["alternatives"]:
                    st.write(f"- **{alt['name']}** (RxCUI {alt['rxcui']}) — {alt['rationale']}")
                    st.caption(f"[Source]({alt['source_url']})")

            st.markdown("**Citations**")
            for c in item["citations"]:
                st.markdown(f"- {c['claim']} — [source]({c['source_url']})")

            ac1, ac2, ac3 = st.columns(3)
            ac1.button("✓ Accept", key=f"a-{item['item_id']}", use_container_width=True)
            ac2.button("✎ Override", key=f"o-{item['item_id']}", use_container_width=True)
            ac3.button("⚠ Escalate", key=f"e-{item['item_id']}", use_container_width=True)

# === Disclaimer ===
st.caption("⚠ Synthetic formulary and active orders for v0.1 demo only. FDA + RxNorm data is live.")
