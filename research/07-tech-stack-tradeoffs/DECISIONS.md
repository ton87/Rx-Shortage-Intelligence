# Tech Stack Decisions

Full decision log for v0.1. Each row: chosen tool, alternatives, why this, what we lose.

## Layer-by-layer

### LLM
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Anthropic Claude (claude-sonnet-4-6)** | GPT-4o, Llama 3 70B, Gemini Flash | Native MCP, strong tool use, citations, JSON output reliability | Cost; vendor lock-in; cost target hard to hit |

### Agent framework
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Anthropic SDK native loop** | LangChain, LangGraph, Haystack, smolagents | Code IS the trace (FR-5); no abstraction tax; ~50 LOC | Reinvent retry, state, async patterns |

### Tool transport
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **FastMCP stdio + bridge** | Plain function tools, FastMCP HTTP+ngrok, Anthropic mcp_servers beta | PRD §12.3-faithful; future MCP distribution surface; local-only | +30-45 min build; bridge code novel; async/stdio gotchas |

### Therapeutic alternatives source
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **RxClass class members** (ATC) | DrugBank, Orange Book, hand-curated table | Free, real public API, defensible cite | Class membership ≠ true equivalence; needs filters |

### RAG
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **BM25-lite over JSON section chunks** | Sentence-transformers + FAISS, LlamaIndex, Cohere rerank | Zero infra; deterministic; 30 LOC | Misses synonyms; lower recall than embeddings |

### UI
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Streamlit** | Gradio, FastAPI+React, Next.js, Reflex | Single-file Python, hours-to-ship | Threading edges; "looks streamlit"; limited custom layout |

### Persistence
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Local JSON files** | SQLite, DuckDB, Postgres, Parquet | Demoable, diffable, zero infra, single-user fine | Concurrent-write unsafe; no query power |

### API response cache (Tier 2)
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **diskcache** | Redis, sqlite-cache, lru_cache, requests-cache | Pure-Python, persists across runs, 1-line wrap | Single-machine; no multi-process coordination |

### Prompt cache (Tier 1)
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Anthropic ephemeral 5-min** | 1-hr ephemeral, no caching | Fits single-briefing run; 0.1× read cost | Cold first call pays 1.25× write |

### UI cache (Tier 3)
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **st.cache_data + JSON file fallback** | st.session_state, custom file cache | Streamlit-native + cold-start works | Two layers to reason about |

### Eval harness
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Custom Python + Claude-as-judge** | Promptfoo, Inspect AI, OpenAI evals | PRD-aligned 5 dims; minimal deps | Reinvents wheel; single-judge bias |

### Severity classifier
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Rule-based pre-filter + LLM rationale** | Pure rules, pure LLM | Deterministic where possible + semantic where needed | LLM override path adds complexity |

### Diff logic
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **Set ops on (rxcui, status) tuples** | Per-record full diff, hash-based | O(n+m), simple, deterministic | Drops ~10% RxCUI-less FDA records |

### Confidence scoring
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **LLM-reported with rule-based ceiling** | Pure rules, pure LLM | Captures nuance; prevents overconfidence | Requires both layers correct |

### Code repo
| Choice | Alternatives | Why | Drawback |
|--------|--------------|-----|----------|
| **GitHub** | GitLab, local-only, Bitbucket | Customer-demoable artifact; well-known | Public repo would leak strategy — keep private |

## Cross-cutting decisions

### Real public APIs vs synthetic-only
**Chosen**: Real APIs (FDA + openFDA + RxNorm) for live data, synthetic for formulary/orders.
**Why**: PRD principle 5 demands citations. Citing fake URLs is dishonest. v0.2 swaps synthetic for real customer formulary.

### v1 vs v2 prompt scaffolding
**Chosen**: v1 only with v2 hook.
**Why**: Customer chose this in clarifying questions. Saves ~30 min. v2 prompt is "TBD" — inventing one would be guess work.

### Demo target: local-only
**Chosen**: `streamlit run` on developer laptop.
**Why**: Customer chose this. Zero deploy time. Screen-share for demo.
**Backup**: Loom recording during buffer block.

### Synthetic data labeled as synthetic
**Chosen**: UI banner, file labels, demo script all say "synthetic for v0.1."
**Why**: PRD Principle 7 is non-negotiable. Honest scoping = trust.

## Decisions deferred to production

- Real customer formulary integration (v0.2)
- EHR/CDS Hooks (v0.4)
- Background scheduler + push notifications (v0.3)
- Multi-tenancy + auth (v0.2)
- Pharmacy inventory partnership (v1.x)
- MCP server distribution (v1.0)
- Mixture-of-models cost optimization (v0.2)

## Decisions we'd revisit at v0.2

| Decision | Why revisit |
|----------|-------------|
| BM25 keyword RAG | Embeddings give better recall when corpus grows |
| Local JSON persistence | Multi-user + concurrent writes need real DB |
| diskcache | Multi-process production needs Redis |
| Claude-as-judge sole evaluator | Add second judge for inter-rater reliability |
| RxClass alternatives proxy | Add curated equivalence table for high-stakes drugs |
| 5-min prompt cache TTL | 1-hr if briefings run more than once/hour |
