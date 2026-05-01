# Caching — Tradeoffs

## Tier 1 — Anthropic prompt cache TTL

| Option | Cost | Use case |
|--------|------|----------|
| **5-min ephemeral** (chosen) | 1.25× write, free reads | Single briefing run completes <5 min |
| 1-hr ephemeral | 2× write, free reads for 1 hr | Production with multiple briefings/hr |
| No cache | 1× write, every call | Debugging |

5-min chosen because briefing target latency is <60 sec. Plenty of margin.

## Tier 2 — diskcache vs alternatives

| Tool | Pro | Con |
|------|-----|-----|
| **diskcache** (chosen) | Pure-Python, zero infra, persists | No multi-process write coordination beyond fcntl |
| Redis | Battle-tested, multi-process safe | Need server running |
| sqlite-cache | Standard lib `sqlite3` | DIY TTL eviction |
| `requests-cache` | httpx-style integration with TTL | Adds extra dep, less control |
| `lru_cache` | Built-in | In-memory only, lost on rerun |

diskcache wins on hackathon simplicity. Production v0.2 → Redis.

## Tier 2 — TTL by source

| Source | TTL | Why |
|--------|-----|-----|
| FDA shortages list | 1 hr | Updates daily, 1-hr lag acceptable for demo |
| openFDA labels | 7 days | Labels rarely change |
| RxNorm normalize | 30 days | Drug ↔ RxCUI mapping is essentially permanent |
| RxClass class | 7 days | Class mappings stable |

Aggressive TTLs save API quota. Conservative TTLs (5 min) would defeat the cache. Balance picks a side.

## Tier 3 — st.cache_data vs custom file cache

| Approach | Pro | Con |
|----------|-----|-----|
| **st.cache_data + JSON file fallback** (chosen) | Streamlit-native; cold-start works | Two layers to reason about |
| Pure st.cache_data | Single layer | Loses on Streamlit process restart |
| Pure file cache | Persists forever | Manual TTL handling, no UI integration |

Two layers is OK because they have distinct invalidation: st.cache_data on rerun, file on manual delete.

## Cache key design

URL + sorted query params. Why sorted: `?a=1&b=2` and `?b=2&a=1` should hit same cache. dict iteration order is insertion-ordered in Python 3.7+ but explicit sort is safer.

Don't include user-specific data (customer_id) in cache key for public APIs — same FDA response is valid for every customer.

## Cache invalidation strategy

| Event | What to clear |
|-------|---------------|
| User clicks "Re-run briefing" | Tier 3 only |
| FDA publishes new shortage | (we don't know — accept 1-hr staleness) |
| Customer adds drug to formulary | Tier 1 (formulary block changed) — Tier 2 unaffected |
| Severity rubric changes (v1→v2) | Tier 1 (rubric block changed) |
| Prompt template change | Tier 1 (role block changed) |

Cache invalidation is surgical, not nuclear.

## What we accept

- Cold-start cost: first briefing of the day pays full price. Mitigation: pre-warm at H6.
- 5-min TTL drift: if user takes >5 min to drill down + re-run, cache misses. Acceptable.
- diskcache write contention: single-user demo = no contention.
- No cross-customer cache sharing on Tier 1: each customer's formulary is unique. v1.x can introduce shared system block + per-customer formulary block to share infra.
