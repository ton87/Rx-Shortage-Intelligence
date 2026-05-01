# Caching — Lesson

## Three tiers, three problems

| Tier | What it caches | Why | Library |
|------|---------------|-----|---------|
| **1. Anthropic prompt cache** | System + rubric + formulary blocks sent to Claude | Hit cost target <$0.05/briefing | Built-in `cache_control` |
| **2. API response cache** | httpx responses from FDA/openFDA/RxNorm | Avoid rate limits, speed up rerun | `diskcache` |
| **3. Briefing artifact cache** | Final BriefingRun JSON | Dashboard <2 sec render (FR-9) | `st.cache_data` + disk persist |

Each tier has a different invalidation horizon. Don't conflate.

## Tier 1 — Prompt cache

`cache_control: {"type": "ephemeral"}` marks a system block as cacheable. 5-min TTL by default. ≥2048 tokens minimum on Sonnet 4.6. Each block must be byte-identical between calls to hit.

**Layering** for Rx Shortage briefing:

```python
system = [
    {"type": "text", "text": ROLE_PROMPT, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": SEVERITY_RUBRIC, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": json.dumps(formulary), "cache_control": {"type": "ephemeral"}},
]
```

Static-to-dynamic order. ROLE_PROMPT changes once per release. SEVERITY_RUBRIC is the v1/v2 axis (eval harness varies this). Formulary changes per customer.

**1-hr TTL option**: `{"type": "ephemeral", "ttl": "1h"}`. Costs 2× write but reads forever. Use for production once stable.

**Verification**: response.usage has `cache_creation_input_tokens` (write) and `cache_read_input_tokens` (hit). Log both per call.

## Tier 2 — API cache

`diskcache.Cache` is a Python on-disk key-value store. Wrap every httpx call:

```python
from diskcache import Cache
import httpx

CACHE = Cache("./cache/api")

def cached_get(url: str, params: dict = None, ttl: int = 3600) -> dict:
    key = f"{url}?{sorted((params or {}).items())}"
    if key in CACHE:
        return CACHE[key]
    resp = httpx.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    CACHE.set(key, data, expire=ttl)
    return data
```

**TTL by source**:
- FDA shortages list: 1 hr (changes daily, but tolerate 1-hr lag for demo)
- openFDA labels: 7 days (basically immutable per drug)
- RxNorm normalize: 30 days (drug ↔ RxCUI mapping ~immutable)
- RxClass class members: 7 days

**Persistence across runs**: `diskcache` writes to `./cache/api/`. Survives Streamlit reruns and `kill -9`. Keep `cache/` in `.gitignore`.

**Why not `lru_cache`**: in-memory only. Streamlit reloads = cache loss. `lru_cache` good for inner loops, bad for HTTP.

## Tier 3 — Briefing artifact cache

Two layers:

**Memory**: `@st.cache_data(ttl=3600)` on `get_today_briefing(customer_id, date)`. Returns same Python object on cache hit. Dashboard renders <2 sec (FR-9).

**Disk**: persist final BriefingRun JSON to `data/briefings/YYYY-MM-DD.json`. On cold start, load from disk if exists. On re-run, regenerate + overwrite.

```python
@st.cache_data(ttl=3600, show_spinner=False)
def get_today_briefing(customer_id: str, date_iso: str) -> dict:
    path = Path(f"data/briefings/{date_iso}.json")
    if path.exists():
        return json.loads(path.read_text())
    briefing = generate_briefing(customer_id, date_iso)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(briefing, indent=2))
    return briefing
```

**Re-run** button:
```python
if st.button("Re-run briefing"):
    st.cache_data.clear()
    Path(f"data/briefings/{today}.json").unlink(missing_ok=True)
    st.rerun()
```

## `st.cache_data` vs `st.cache_resource`

- `cache_data`: caches return value (must be serializable). Use for dataframes, dicts, lists, JSON.
- `cache_resource`: caches the object itself, not value. Use for clients (Anthropic, MCP, DB connections).

```python
@st.cache_resource
def get_anthropic_client():
    return anthropic.Anthropic()

@st.cache_resource
def get_mcp_clients():
    return asyncio.run(setup_mcp_tools())
```

Mix-up = error: `cache_data` will try to serialize a client and fail.

## Cost math

See `COST-MATH.md` for the per-call breakdown. Summary:

- 6 batch calls of 5 drugs each
- 1 prompt cache write + 5 reads
- ~2K output tokens per call
- **~$0.21/briefing**
- Above $0.05 PRD target. Document the gap. v0.2 mitigation = mixture-of-models.

## Cache hazards

1. **Prompt cache miss surprise**: any whitespace difference between calls = miss. Always use `json.dumps(formulary, sort_keys=True)` for deterministic serialization.

2. **TTL drift**: Tier 2 cache says "1 hr" for FDA shortages; Tier 1 prompt cache says "5 min". If a single briefing run takes 8 min, prompt cache invalidates mid-run. Mitigation: complete briefing within 5 min OR upgrade to 1-hr ephemeral on Tier 1.

3. **Stale briefing**: Tier 3 caches for 1 hr. New FDA shortage published → user sees stale. Mitigation: render `last_updated` timestamp prominently; "Re-run" button always available.

4. **Disk cache collision**: same drug, different presentation (oral vs IV) = same RxCUI but different label record. Solution: key on full URL including query params, not RxCUI alone.

5. **Cold-start cost**: first briefing of the day pays full price (no cache hits). Demo: pre-warm by running once before customer call.

## What can go wrong with caching

- **Forget `cache_control`**: cost goes 10× without caching. Verify on first call via `response.usage.cache_creation_input_tokens > 0`.
- **diskcache locked**: another process holds lock. Single-user demo = fine.
- **`st.cache_data` returns old value forever**: TTL wasn't set. Use `ttl=3600` not just `@st.cache_data`.
- **Streamlit rerun resets memory cache but not disk cache**: that's a feature. Disk wins on cold start.
