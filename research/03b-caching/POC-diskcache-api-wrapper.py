"""
POC: diskcache wrapper around httpx for FDA/openFDA/RxNorm.

Run: python research/03b-caching/POC-diskcache-api-wrapper.py

Demonstrates:
- Single cached_get() function with per-source TTL
- Cache hit/miss instrumentation
- Persistence across runs
- Key uniqueness via full URL
"""

import time
import httpx
from pathlib import Path
from diskcache import Cache

CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "api"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE = Cache(str(CACHE_DIR))

TTL_BY_HOST = {
    "api.fda.gov/drug/shortages": 3600,        # 1 hr
    "api.fda.gov/drug/label": 7 * 24 * 3600,    # 7 days
    "rxnav.nlm.nih.gov/REST/rxcui": 30 * 24 * 3600,  # 30 days
    "rxnav.nlm.nih.gov/REST/rxclass": 7 * 24 * 3600,  # 7 days
}


def _ttl_for(url: str) -> int:
    for prefix, ttl in TTL_BY_HOST.items():
        if prefix in url:
            return ttl
    return 3600  # default 1 hr


def _make_key(url: str, params: dict | None) -> str:
    if not params:
        return url
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return f"{url}?{qs}"


def cached_get(url: str, params: dict | None = None) -> dict:
    """GET with disk cache. Returns parsed JSON. Records hit/miss in stats."""
    key = _make_key(url, params)
    hit = key in CACHE
    if hit:
        return CACHE[key]

    resp = httpx.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    CACHE.set(key, data, expire=_ttl_for(url))
    return data


if __name__ == "__main__":
    print(f"Cache dir: {CACHE_DIR}")
    print(f"Existing cache size: {len(CACHE)} entries\n")

    # First call — likely miss (cold)
    t0 = time.perf_counter()
    data = cached_get("https://api.fda.gov/drug/shortages.json", {"limit": 5})
    t1 = time.perf_counter()
    print(f"Call 1: {(t1 - t0) * 1000:.0f}ms  (records returned: {len(data['results'])})")

    # Second call — hit
    t0 = time.perf_counter()
    data = cached_get("https://api.fda.gov/drug/shortages.json", {"limit": 5})
    t1 = time.perf_counter()
    print(f"Call 2: {(t1 - t0) * 1000:.0f}ms  (cache hit)")

    # Different params — miss
    t0 = time.perf_counter()
    data = cached_get("https://api.fda.gov/drug/shortages.json", {"limit": 10})
    t1 = time.perf_counter()
    print(f"Call 3 (different params): {(t1 - t0) * 1000:.0f}ms")

    print(f"\nCache size after run: {len(CACHE)} entries")
    print(f"Cache disk usage: {sum(f.stat().st_size for f in CACHE_DIR.rglob('*') if f.is_file()) / 1024:.1f} KB")
