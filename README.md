# Rx Shortage Intelligence — v0.1

AI morning briefing for hospital pharmacy directors. Cross-references live FDA drug shortages against a hospital formulary, classifies hospital impact (High / Monitor / Resolved), and recommends therapeutic alternatives with citations.

> ⚠️ Formulary and active orders are **synthetic** for demo. FDA shortage feed and RxNorm are **live public data**.

> 🎯 Prototype built by **Anton Verenitch**. Not a production product.

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

1. Opens to today's briefing — three metric tiles (**High Impact / Monitor / Resolved**) with one card per surfaced drug
2. Click **Re-run briefing** to fetch fresh FDA data — hits real FDA/RxNorm APIs, takes ~30–60s
3. Each card answers the pharmacist's questions in scannable order:
   - What drug is this? → drug name in the card header
   - What does FDA say? → `FDA: Current shortage` pill
   - How much does it matter here? → `Impact: High / Monitor / Resolved` pill
   - Why is FDA reporting it? → `Reason: …` row (or "Not provided by FDA")
   - Is supply constrained? → `Availability: …` row
   - Why does it matter locally? → **Why it matters** body section (plain-language hospital impact)
   - What should I do? → **Recommended next step** body section
4. Each card has two HITL actions:
   - **Mark reviewed** — log that the alert was seen; the app takes no clinical action
   - **Dismiss** — record a required reason explaining why the alert is not actionable for this briefing
5. Expand **Details + citations** on any card for the **FDA details** panel (FDA status, FDA reason, FDA availability, manufacturer, presentation, dosage form, RxCUI, posting dates, estimated resolution), the agent rationale, the **Potential therapeutic alternatives** table (RxNorm/RxClass suggestions — clinical review required), and the full citation list
6. Top tabs: **Briefing** · **Formulary** (synthetic drugs being checked) · **Active Orders** (synthetic 30-day order volume) · **Eval** (15-case scoring results)

### UX terminology — internal vs. user-facing

The internal severity/confidence values stay in the JSON for backward compatibility, but the UI translates them into pharmacist-facing language so internal rule IDs and rubric jargon never appear in the alert text.

| Internal value (JSON) | User-facing label |
|----------------------|-------------------|
| `severity: Critical` | `Impact: High` |
| `severity: Watch`    | `Impact: Monitor` |
| `severity: Resolved` | `Impact: Resolved` |
| `status: Current`    | `FDA: Current shortage` |
| `status: To Be Discontinued` | `FDA: To be discontinued` |
| `status: Resolved`   | `FDA: Resolved by FDA` |
| `user_action: accept` | "Reviewed" pill |
| `user_action: dismiss` (legacy `override` also accepted) | "Dismissed" pill |

The agent prompt is hardened to never emit internal rule IDs (`C1`, `C2`, `W1`, `R1`, etc.) in user-facing text; a defensive sanitizer in `parse_briefing_item()` strips any leakage as a safety net.

---

## All commands

```bash
make run        # launch Streamlit dashboard  → http://localhost:8501
make briefing   # generate a live briefing    (hits real APIs, ~$0.10–0.20)
make test       # run 340 unit tests          (~1 second)
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
  main.py                  # Streamlit tab dispatcher (streamlit run src/main.py)
  briefing.py              # CLI orchestrator (python -m src.briefing)
  mcp_bridge.py            # spawns 3 servers, exposes 6 tools
  cache.py                 # diskcache wrapper
  domain/                  # pure logic: severity, confidence, fda, diff,
                           # indexing, matching, constants
  agent/                   # LLM: loop.py, prompts.py, prefetch.py, prompts/*.md
  io_/                     # filesystem: briefing_store.py, data_loader.py
  ui/                      # streamlit: theme, components, formatters,
                           # actions, runner, *_view.py per tab
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

tests/                     # 340 tests
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
