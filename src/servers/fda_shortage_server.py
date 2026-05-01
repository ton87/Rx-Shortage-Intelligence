"""
FDA Shortage MCP server.

Provides 2 tools:
- get_current_shortages(limit) -> list of current FDA shortage records
- get_shortage_detail(rxcui)   -> single shortage record by RxCUI

All HTTP calls go through src.cache.cached_get (disk-backed, TTL=1hr).
"""

import httpx
from mcp.server.fastmcp import FastMCP

from src.cache import cached_get, TTL_FDA_SHORTAGES

BASE = "https://api.fda.gov/drug/shortages.json"

mcp = FastMCP("fda-shortage")


@mcp.tool()
def get_current_shortages(limit: int = 20) -> list[dict]:
    """
    Fetch current FDA drug shortages.

    Args:
        limit: Max number of records to return (default 20, max 100).

    Returns:
        List of shortage records. Each has generic_name, status, rxcui (list),
        shortage_reason, and source_url for citation.
    """
    try:
        safe_limit = min(limit, 100)
        key = f"fda_shortages:status:Current:limit:{safe_limit}"

        def fetch():
            params = {
                "search": "status:Current",
                "limit": safe_limit,
            }
            resp = httpx.get(BASE, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()

        data = cached_get(key=key, fetch_fn=fetch, ttl=TTL_FDA_SHORTAGES)
        results = (data or {}).get("results", [])
        source_url = f"{BASE}?search=status%3ACurrent&limit={safe_limit}"
        return [_trim(r, source_url=source_url) for r in results]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_shortage_detail(rxcui: str) -> dict:
    """
    Fetch the most recent shortage record for a specific RxCUI.

    Args:
        rxcui: RxNorm Concept Unique Identifier.

    Returns:
        Shortage record dict, or {"error": "..."} if not found.
    """
    try:
        key = f"fda_shortage:rxcui:{rxcui}"

        def fetch():
            params = {"search": f"openfda.rxcui:{rxcui}", "limit": 1}
            resp = httpx.get(BASE, params=params, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

        data = cached_get(key=key, fetch_fn=fetch, ttl=TTL_FDA_SHORTAGES)
        if data is None:
            return {"error": f"No shortage record for RxCUI {rxcui}"}
        results = data.get("results", [])
        if not results:
            return {"error": f"No shortage record for RxCUI {rxcui}"}
        source_url = f"{BASE}?search=openfda.rxcui%3A{rxcui}"
        return _trim(results[0], source_url=source_url)
    except Exception as e:
        return {"error": str(e)}


def _trim(rec: dict, source_url: str = BASE) -> dict:
    """
    Reduce FDA record bloat for token efficiency.

    rxcui MUST stay a list (never coerced to str or None).
    source_url MUST always be present — caller passes a query-specific URL
    so citations link directly to the record that was fetched.
    """
    openfda = rec.get("openfda") or {}
    rxcui = openfda.get("rxcui", [])
    # Guarantee list shape — never None, never str
    if not isinstance(rxcui, list):
        rxcui = [rxcui] if rxcui else []

    return {
        "generic_name": rec.get("generic_name"),
        "proprietary_name": rec.get("proprietary_name"),
        "status": rec.get("status"),
        "shortage_reason": rec.get("shortage_reason"),
        "availability": rec.get("availability"),
        "estimated_resolution": rec.get("estimated_resolution"),
        "rxcui": rxcui,
        "ndc": openfda.get("product_ndc", []),
        "source_url": source_url,
        "update_date": rec.get("update_date"),
    }


if __name__ == "__main__":
    mcp.run()
