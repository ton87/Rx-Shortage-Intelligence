# Rx Shortage Intelligence — v0.1

AI-assisted morning briefing for hospital pharmacy directors. Cross-references live FDA drug shortages against a hospital's formulary and active orders, classifies severity (Critical / Watch / Resolved), and recommends therapeutic alternatives with citations.

> **Synthetic data** — formulary and active orders are synthetic for demo purposes. FDA shortage feed, openFDA labels, and RxNorm data are live public APIs.

---

## Quick start

```bash
# 1. Clone and set up
git clone git@github.com:ton87/Rx-Shortage-Intelligence.git
cd Rx-Shortage-Intelligence

# 2. Create venv with Python 3.12+
/path/to/python3.12 -m venv venv
source venv/bin/activate           # or: use venv/bin/pip and venv/bin/python3 explicitly

# 3. Install dependencies
venv/bin/pip install -r requirements.txt

# 4. Add your Anthropic API key
cp .env.template .env
# Edit .env and set: ANTHROPIC_API_KEY=sk-ant-...

# 5. Bootstrap synthetic data (one-time)
venv/bin/python3 -m src.data_loader

# 6. Launch dashboard
streamlit run src/main.py
```

The dashboard loads a sample briefing immediately. Hit **Re-run briefing** to generate a live one (~30–60s).

---

## Architecture

```
CLI:  python -m src.briefing
        ↓ async — MCP servers, Anthropic SDK, tool-use loop
        writes data/briefings/YYYY-MM-DD.json

UI:   streamlit run src/main.py
        ↓ pure sync — reads JSON, renders, no async
        Re-run button → subprocess.run(["python", "-m", "src.briefing"])
```

**Three MCP servers** (FastMCP stdio):

| Server | Tools |
|--------|-------|
| `fda_shortage_server` | `get_current_shortages`, `get_shortage_detail` |
| `drug_label_server` | `get_drug_label_sections`, `search_labels_by_indication` |
| `rxnorm_server` | `normalize_drug_name`, `get_therapeutic_alternatives` |

**Agent loop** — native Anthropic SDK tool-use (`while stop_reason == "tool_use"`). No LangChain. Code is the trace.

---

## Commands

```bash
# Smoke test — confirm 6 tools discovered across 3 servers
venv/bin/python3 -m src.mcp_bridge

# Generate a live briefing (hits real APIs, costs ~$0.10–$0.20)
venv/bin/python3 -m src.briefing

# Run eval harness (deterministic, no API cost)
venv/bin/python3 -m src.eval.runner

# Run full test suite (283 tests, ~1s)
venv/bin/python3 -m pytest tests/ -q
```

---

## Stack

| Layer | Choice |
|-------|--------|
| LLM | `claude-sonnet-4-6` |
| Agent | Anthropic SDK native tool-use loop |
| Tools | 3 FastMCP stdio servers |
| UI | Streamlit (sync only — Pattern B) |
| API cache | `diskcache` (1h FDA, 24h labels/RxNorm) |
| Prompt cache | Anthropic ephemeral (5-min TTL) |
| Data | Synthetic formulary + orders; live FDA + openFDA + RxNorm |

---

## Eval results (v0.1 deterministic)

| Dimension | Score | Target |
|-----------|-------|--------|
| Severity accuracy | 100% | ≥90% |
| Citation accuracy | 100% | 100% |
| Hallucination rate | 0% | <2% |
| Recall | 100% | 100% |
| Clinical appropriateness | 4.0/5 | ≥4 (stubbed — wire Claude-as-judge in v0.2) |

---

## Cost

Modeled at **~$0.10–$0.20/briefing** (30 drugs, with Anthropic ephemeral prompt cache).  
PRD target was $0.05 — documented honestly per Principle 7. Production v0.2 can reduce with Haiku screening pass.

---

## Known gaps (v0.2+)

- Real customer formulary (EHR integration)
- Background scheduler + push notifications
- Multi-tenancy + auth
- Claude-as-judge for clinical appropriateness scoring
- RAG over label chunks (currently full-label text passed)
- `@st.cache_resource` for warm MCP client (faster Re-run)
