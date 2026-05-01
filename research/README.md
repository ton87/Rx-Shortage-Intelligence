# Rx Shortage Intelligence — Research Folder

Lecture-style scaffold. Read before you build. Each numbered subfolder is a self-contained 10-minute "go learn this" unit.

## Folder convention

Each section follows the same shape:

| File | Purpose |
|------|---------|
| `LESSON.md` | Concept, the why, what to internalize |
| `POC-*.py` | Runnable proof-of-concept code (or `.md` if config) |
| `TRADEOFFS.md` | Why this approach over alternatives |
| `REFERENCES.md` | URLs, docs, source materials |

POCs are **drop-in-ready** for the real `src/` build during the hackathon. Copy, don't rewrite.

## Folder map

| # | Folder | What it teaches | Use during |
|---|--------|----------------|------------|
| 00 | `00-prd-summary` | PRD distilled to 1 page + non-negotiables | Pre-H0 |
| 01 | `01-data-layer` | FDA / openFDA / RxNorm + synthetic data + yesterday snapshot | H1 |
| 02 | `02-mcp-servers` | MCP protocol, FastMCP, Anthropic-stdio bridge | H2 |
| 03 | `03-agent-loop` | Tool-use loop, RAG over labels, citations | H3 |
| 03b | `03b-caching` | 3-tier cache: prompt + API + UI | H3 (parallel) |
| 04 | `04-briefing-diff` | Snapshot diff, severity classifier rules | H4 |
| 05 | `05-streamlit-ui` | FR-mapping, scan order, anti-patterns | H5 |
| 06 | `06-eval-harness` | 5 scoring dims, 15-case design, judge | H6 |
| 07 | `07-tech-stack-tradeoffs` | Why claude / FastMCP / Streamlit / diskcache | All |
| 08 | `08-concerns-risks` | Time bombs + mitigations | All |

## Reading order

**Hackathon morning**: skim 00 → 07 → 08, then dive into 01 as you start H1.

**Pre-block**: read that block's LESSON before starting (~10 min). Reference POC code while building.

**Stuck mid-build**: TRADEOFFS.md tells you why we made the choice and what to swap if blocked.

## How to run a POC

```bash
cd /Users/ragglesoft/Desktop/anton-ai-project
python -m venv .venv && source .venv/bin/activate
pip install anthropic mcp httpx diskcache streamlit python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...     # only needed for 03 + 06 POCs

python research/01-data-layer/POC-fda-shortages.py
```

POCs in 03/03b/06 require API key; rest run on public APIs only.

## What this scaffold is NOT

- Not the actual `src/`. Real build happens during hackathon hours per `ROADMAP.md`.
- Not exhaustive. Lessons are tight. Where deeper context helps, `REFERENCES.md` points out.
- Not commitment to every line of POC code. POCs are seeds, not specs.

## What it IS

- Pre-loaded answers to "how do I X" so hackathon hours go to building, not researching.
- Defensible record of tradeoffs for customer review.
- Risk register so surprises happen on paper, not at H4.
