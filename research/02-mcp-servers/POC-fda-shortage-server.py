"""
POC: real FDA Shortage MCP server stub.

Run as MCP server (stdio): python research/02-mcp-servers/POC-fda-shortage-server.py

Tools:
- get_current_shortages(limit) → list of shortage records
- get_shortage_detail(rxcui) → single record by RxCUI

This is the shape that ships to src/servers/fda_shortage_server.py at H2.
"""

import httpx
from mcp.server.fastmcp import FastMCP

BASE = "https://api.fda.gov/drug/shortages.json"

mcp = FastMCP("fda-shortage")


@mcp.tool()
def get_current_shortages(limit: int = 20) -> list[dict]:
    """
    Fetch current FDA drug shortages.

    Args:
        limit: Max number of records to return (default 20, max 100).

    Returns:
        List of shortage records. Each has generic_name, status, shortage_reason,
        openfda.rxcui (when available), and source_url for citation.
    """
    # FDA status field actual values: 'Current' (1140), 'To Be Discontinued' (498), 'Resolved' (29)
    # v0.1 filters to Current only. TBD handling = open question (see QUESTIONS-FOR-ANTON.md Q1).
    params = {
        "search": "status:Current",
        "limit": min(limit, 100),
    }
    resp = httpx.get(BASE, params=params, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [_trim(r) for r in results]


@mcp.tool()
def get_shortage_detail(rxcui: str) -> dict:
    """
    Fetch the most recent shortage record for a specific RxCUI.

    Args:
        rxcui: RxNorm Concept Unique Identifier.

    Returns:
        Shortage record dict, or {"error": "..."} if not found.
    """
    params = {"search": f"openfda.rxcui:{rxcui}", "limit": 1}
    resp = httpx.get(BASE, params=params, timeout=15)
    if resp.status_code == 404:
        return {"error": f"No shortage record for RxCUI {rxcui}"}
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return {"error": f"No shortage record for RxCUI {rxcui}"}
    return _trim(results[0])


def _trim(rec: dict) -> dict:
    """Reduce label-record bloat for token efficiency."""
    return {
        "generic_name": rec.get("generic_name"),
        "proprietary_name": rec.get("proprietary_name"),
        "status": rec.get("status"),
        "shortage_reason": rec.get("shortage_reason"),
        "availability": rec.get("availability"),
        "estimated_resolution": rec.get("estimated_resolution"),
        "rxcui": (rec.get("openfda") or {}).get("rxcui", []),
        "ndc": (rec.get("openfda") or {}).get("product_ndc", []),
        "source_url": "https://api.fda.gov/drug/shortages.json",
        "update_date": rec.get("update_date"),
    }


if __name__ == "__main__":
    mcp.run()
