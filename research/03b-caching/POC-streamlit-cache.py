"""
POC: st.cache_data vs st.cache_resource demo.

Run: streamlit run research/03b-caching/POC-streamlit-cache.py

Demonstrates:
- @st.cache_data for serializable returns (the briefing JSON)
- @st.cache_resource for client objects (Anthropic, MCP)
- ttl + clear behavior
- Re-run button pattern
"""

import time
import json
import streamlit as st


# Mock "Anthropic client" — would normally be anthropic.Anthropic()
class FakeClient:
    def __init__(self):
        self.created_at = time.time()


# cache_resource: same instance across all reruns
@st.cache_resource
def get_client() -> FakeClient:
    return FakeClient()


# cache_data: serializes return value, ttl-bound
@st.cache_data(ttl=30, show_spinner="Generating briefing...")
def generate_briefing(customer_id: str, date: str) -> dict:
    # Simulate expensive work
    time.sleep(2)
    return {
        "customer_id": customer_id,
        "date": date,
        "items": [
            {"drug": "cisplatin", "severity": "Critical"},
            {"drug": "methotrexate", "severity": "Watch"},
        ],
        "generated_at": time.time(),
    }


st.title("Streamlit cache POC")

client = get_client()
st.write(f"Client created_at: `{client.created_at}` (same across reruns until restart)")

st.divider()

briefing = generate_briefing("memorial-health-450", "2026-04-30")
st.write(f"Briefing generated_at: `{briefing['generated_at']}` (cached for 30 sec)")
st.json(briefing)

if st.button("Re-run briefing"):
    st.cache_data.clear()
    st.rerun()

st.caption("Click 'Re-run' to see generated_at change. Otherwise it stays for 30 sec.")
