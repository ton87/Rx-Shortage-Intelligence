# Agent Loop — Tradeoffs

## Native loop vs LangChain/LangGraph

| Approach | Pro | Con |
|----------|-----|-----|
| **Native Anthropic SDK loop** (chosen) | Code IS the trace; fully transparent; no abstraction tax; ~50 LOC | More boilerplate; reinvent retry/state |
| LangGraph DAG | State machine semantics; checkpointing free; visualization | Hides reasoning; framework lock-in; +30 min setup |
| LangChain AgentExecutor | Many built-in tool integrations | Heavy; opinionated; hides Anthropic-specific features (cache_control) |

PRD §12.4 explicitly chose native. Honor that.

## RAG: keyword vs embeddings

| Approach | Pro | Con |
|----------|-----|-----|
| **BM25-lite keyword over JSON sections** (chosen) | Zero infra; fits in 30 LOC; deterministic | Misses synonyms (e.g., "renal" vs "kidney") |
| Sentence-transformers + FAISS | Better recall on synonyms | +pip install + index build time; per-drug overhead |
| Anthropic Files API + native retrieval | SDK-native | Beta; less control over chunking |

For 7 well-named sections per drug, keyword is enough. v0.2 can swap in embeddings.

## Output format: free text vs JSON-strict

| Approach | Pro | Con |
|----------|-----|-----|
| **JSON output enforced via system prompt + parse** (chosen) | Schema-clean; renders directly to UI | Parse fail = retry needed |
| Tool-call output schema (e.g., `submit_briefing_item` tool) | LLM enforced to call tool with valid args | Adds round trip; tool-use overhead |
| Free text + LLM-extract pass | Cheap to write | Two LLM calls = 2× cost; extraction errors |

JSON enforcement chosen with `try/except` + 1 retry on parse fail. If retry fails, surface as `confidence: low` item.

## Per-drug call vs batch

| Approach | Pro | Con |
|----------|-----|-----|
| One call per drug | Simple loop; isolation | 30× round trips; cache hit only on system block |
| **Batch 5 drugs per call** (chosen) | 6× fewer round trips; shared per-call overhead | Larger output → bigger response; one error fails 5 |
| All 30 in one call | Maximum cache value | Output blows max_tokens; parse complexity |

Batch=5 is sweet spot — cost math in LESSON.md.

## Confidence scoring: rule-based vs LLM-self-reported

| Approach | Pro | Con |
|----------|-----|-----|
| **LLM self-reports confidence** (chosen) | Captures nuance (e.g., partial label match) | Overconfident on hallucinations |
| Rule: tool-call success count + alt-rank → score | Defensible, deterministic | Misses semantic uncertainty |
| Hybrid: rule-based floor + LLM ceiling | Both signals | Complex; v0.2 |

LLM-reported with rule-based **floor** (rules can downgrade, never upgrade). E.g., if name-fallback was used, max confidence is "medium" regardless of LLM claim.

## What we accept as v0.1 limitations

- No streaming output (FR-9 says <30 sec rerun; full response within budget without streaming)
- No retrieval re-ranking
- No multi-turn refinement (single agent run per drug-batch)
- No tool-result caching across drugs (next drug re-fetches even if same RxCUI — handled at API cache layer instead)
