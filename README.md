# Rx Shortage Intelligence — v0.1

AI morning briefing for hospital pharmacy directors. Cross-references live FDA drug shortages against a hospital formulary, classifies severity (Critical / Watch / Resolved), and recommends therapeutic alternatives with citations.

> ⚠️ Formulary and active orders are **synthetic** for demo. FDA, openFDA, and RxNorm data are **live**.

---

## Run it — copy-paste these commands

### First time only

```bash
# 1. Go to the project
cd /Users/anton/Downloads/Rx-Shortage-Intelligence

# 2. Activate the Python 3.12 environment
source venv/bin/activate

# 3. Confirm you're on the right Python (should say 3.12.x)
python3 --version

# 4. Install dependencies
make install

# 5. Add your Anthropic API key
#    Open .env in any editor and paste your key
open .env
#    It should contain exactly: ANTHROPIC_API_KEY=sk-ant-...

# 6. Bootstrap synthetic data (one-time)
make data
```

### Every time you want to use it

```bash
cd /Users/anton/Downloads/Rx-Shortage-Intelligence
source venv/bin/activate
make run
```

That opens the dashboard at **http://localhost:8501**

---

## What the dashboard does

1. Opens showing a sample briefing (Cisplatin Critical, Methotrexate Watch)
2. Click **Re-run briefing** to generate a live one — hits real FDA/RxNorm APIs, takes ~30–60s
3. Click any item to expand agent reasoning + citations
4. Click **✓ Accept**, **✎ Override**, or **⚠ Escalate** to log your decision
5. Sidebar → **Eval** tab to see 15-case scoring results

---

## All commands

```bash
make run        # launch Streamlit dashboard  → http://localhost:8501
make briefing   # generate a live briefing    (hits real APIs, ~$0.10–0.20)
make test       # run 283 unit tests          (~1 second)
make eval       # run eval harness            (no API cost, deterministic)
make smoke      # confirm 6 MCP tools found   (quick sanity check)
make install    # install/verify dependencies
```

---

## If pip gives a Python version error

Your system `pip` points to macOS Python 3.9. Always use:
```bash
# Option A — activate venv first (then pip works normally)
source venv/bin/activate
pip install -r requirements.txt

# Option B — bypass activation entirely
make install
```

---

## Stack

| Layer | Choice |
|-------|--------|
| LLM | `claude-sonnet-4-6` |
| Agent | Anthropic SDK native tool-use loop |
| Tools | 3 FastMCP stdio servers (FDA, openFDA, RxNorm) |
| UI | Streamlit — sync only, Pattern B |
| API cache | diskcache (1h FDA shortages, 24h labels/RxNorm) |
| Prompt cache | Anthropic ephemeral 5-min TTL |

---

## Project layout

```
src/
  main.py                  # Streamlit dashboard (streamlit run src/main.py)
  agent.py                 # Anthropic tool-use loop
  briefing.py              # generate_briefing(), compute_diff()
  mcp_bridge.py            # spawns 3 servers, exposes 6 tools
  cache.py                 # diskcache wrapper
  servers/
    fda_shortage_server.py
    drug_label_server.py
    rxnorm_server.py
  eval/
    runner.py              # 15-case eval harness
    cases.json

data/
  synthetic_formulary.json
  active_orders.json
  yesterday_snapshot.json
  briefings/               # YYYY-MM-DD.json written on each run
  eval_results.json

tests/                     # 283 tests
```

---

## Eval results

| Dimension | Score | Target |
|-----------|-------|--------|
| Severity accuracy | 100% | ≥ 90% |
| Citation accuracy | 100% | 100% |
| Hallucination rate | 0% | < 2% |
| Recall | 100% | 100% |
| Clinical appropriateness | 4.0 / 5 | ≥ 4 (stubbed — Claude-as-judge in v0.2) |

Cost: ~$0.10–0.20 per briefing (PRD target $0.05 — documented honestly).
