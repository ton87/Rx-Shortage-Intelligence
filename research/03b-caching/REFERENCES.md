# Caching — References

## Anthropic prompt caching

- Docs: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Pricing: https://docs.anthropic.com/en/docs/about-claude/pricing
- Cache TTL options: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching#caching-control
- Sonnet 4.6 minimum cacheable token threshold: 2048

## diskcache

- Docs: https://grantjenks.com/docs/diskcache/
- API: `Cache(directory)`, `.set(key, value, expire=ttl)`, `.get(key)`, `key in cache`
- PyPI: https://pypi.org/project/diskcache/

## Streamlit caching

- `st.cache_data`: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data
- `st.cache_resource`: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource
- Difference: https://docs.streamlit.io/develop/concepts/architecture/caching
- `st.session_state` (alternative): https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state

## openFDA rate limits

- Without API key: 240 requests/min, 1000/day
- With key: 240/min, 120000/day
- https://open.fda.gov/apis/authentication/

## PRD anchors

- §9.3 NFR-2: cost <$0.05/briefing
- §9.3 NFR-1: latency <60 sec
- FR-9: dashboard <2 sec, drill-down <1 sec, rerun <30 sec
- §13.5 failure modes: stale data → live API + last-known cache fallback

## Internal POCs

- `POC-prompt-cache-tiers.py` — 3 cacheable system blocks, cost trace
- `POC-diskcache-api-wrapper.py` — wrapped httpx with per-source TTL
- `POC-streamlit-cache.py` — `st.cache_data` vs `st.cache_resource` demo
- `COST-MATH.md` — full cost scenarios A-E
