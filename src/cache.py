"""
Disk-backed API cache using diskcache.

Usage:
    from src.cache import cached_get, TTL_FDA_SHORTAGES

    data = cached_get(
        key="fda_shortages:current:100",
        fetch_fn=lambda: httpx.get(...).json(),
        ttl=TTL_FDA_SHORTAGES,
    )

TTLs:
    FDA shortage feed   : 3_600 s  (1 hr)   — changes daily at most
    openFDA label       : 86_400 s (24 hr)  — very stable
    RxNorm / RxClass    : 86_400 s (24 hr)  — very stable
"""

from pathlib import Path

from diskcache import Cache

# ── TTL constants (seconds) — importable by other modules ─────────────────
TTL_FDA_SHORTAGES = 3_600
TTL_OPENFDA_LABEL = 86_400
TTL_RXNORM        = 86_400

# ── Sentinel: distinguishes cache miss from a legitimately cached None ─────
_MISS = object()

# ── Module-level Cache singleton ───────────────────────────────────────────
_CACHE_DIR = Path(__file__).parent.parent / "cache" / "api"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_cache: Cache = Cache(str(_CACHE_DIR), size_limit=int(500e6))  # 500 MB cap


def cached_get(key: str, fetch_fn, ttl: int):
    """
    Return cached value for `key`, or call `fetch_fn()`, store result, return it.

    Caches None results (sentinel pattern) so failed lookups aren't re-fetched
    on every call — avoids hammering APIs for drugs with no label / no RxCUI.

    Args:
        key:      Cache key string, e.g. "label:rxcui:2555"
        fetch_fn: Zero-arg callable returning the value to cache.
        ttl:      Seconds until expiry.

    Returns:
        Cached or freshly-fetched value (may be None for legitimate not-found).
    """
    value = _cache.get(key, default=_MISS)
    if value is not _MISS:
        return value  # cache hit (including a cached None)

    value = fetch_fn()
    _cache.set(key, value, expire=ttl)
    return value


def clear_key(key: str) -> None:
    """Remove a specific key so it is re-fetched on next call."""
    _cache.delete(key)


def cache_info() -> dict:
    """Basic stats — used in smoke tests and diagnostics."""
    return {
        "directory":  str(_CACHE_DIR),
        "size_bytes": _cache.volume(),
        "item_count": len(_cache),
    }
