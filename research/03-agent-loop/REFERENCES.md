# Agent Loop — References

## Anthropic SDK + tool use

- Tool use guide: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- Messages API reference: https://docs.anthropic.com/en/api/messages
- Streaming (not used in v0.1): https://docs.anthropic.com/en/docs/build-with-claude/streaming

## Prompt caching

- Prompt caching guide: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Pricing for cache writes/reads: https://docs.anthropic.com/en/docs/about-claude/pricing
- Cache TTL options (5-min ephemeral, 1-hr): https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching#caching-control

## Model

- claude-sonnet-4-6 announcement: https://www.anthropic.com/news/claude-sonnet-4-6
- Model overview + IDs: https://docs.anthropic.com/en/docs/about-claude/models

## RAG

- BM25 reference: https://en.wikipedia.org/wiki/Okapi_BM25
- openFDA label fields used as RAG corpus: https://open.fda.gov/apis/drug/label/searchable-fields/

## PRD anchors

- §12.1 LLM choice rationale
- §12.4 native loop over abstraction libraries
- §13.1 confidence-based routing
- FR-4 citation requirements
- FR-5 drill-down agent traces

## Internal POCs

- `POC-tool-use-loop.py` — minimal mock-tool loop
- `POC-prompt-caching.py` — cache_control + cost math
- `POC-rag-label-chunks.py` — chunk + BM25 retrieve
