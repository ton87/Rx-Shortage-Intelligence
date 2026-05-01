"""
RxNorm + RxClass MCP server.

Provides 2 tools:
- normalize_drug_name(name)               -> RxCUI lookup via RxNorm
- get_therapeutic_alternatives(rxcui)     -> ATC class members via RxClass

All HTTP calls go through src.cache.cached_get (disk-backed, TTL=24hr).
"""

import httpx
from mcp.server.fastmcp import FastMCP

from src.cache import cached_get, TTL_RXNORM

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"

mcp = FastMCP("rxnorm")


@mcp.tool()
def normalize_drug_name(name: str) -> dict:
    """Resolve a drug name to its canonical RxNorm RxCUI.

    Args:
        name: Drug name string (e.g. "cisplatin", "Metformin HCl").

    Returns:
        Dict with rxcui, name, source_url on success; {"error": "..."} on miss or failure.
    """
    try:
        key = f"rxnorm:normalize:{name.lower().strip()}"

        def fetch():
            url = f"{RXNORM_BASE}/rxcui.json"
            resp = httpx.get(url, params={"name": name}, timeout=15)
            resp.raise_for_status()
            return resp.json()

        data = cached_get(key, fetch, TTL_RXNORM)
        ids = (data or {}).get("idGroup", {}).get("rxnormId") or []
        if not ids:
            return {"error": f"No RxCUI found for '{name}'"}
        rxcui = ids[0]
        return {
            "rxcui": rxcui,
            "name": name,
            "source_url": f"{RXNORM_BASE}/rxcui.json?name={name}",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_therapeutic_alternatives(rxcui: str) -> list[dict]:
    """Get therapeutic alternatives via RxClass ATC membership.

    Uses two RxClass API calls:
      1. Look up ATC class for the given RxCUI.
      2. Fetch all members of that ATC class.

    Self is excluded. Results are capped at 10.
    Confidence is always 'class-member'.

    Args:
        rxcui: RxNorm Concept Unique Identifier.

    Returns:
        List of dicts with rxcui, name, confidence; empty list if no ATC class found;
        [{"error": "..."}] on failure.
    """
    try:
        # Step 1: look up ATC class for this drug
        class_key = f"rxclass:byRxcui:{rxcui}"

        def fetch_class():
            url = f"{RXNORM_BASE}/rxclass/class/byRxcui.json"
            resp = httpx.get(url, params={"rxcui": rxcui, "relaSource": "ATC"}, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

        class_data = cached_get(class_key, fetch_class, TTL_RXNORM)

        drug_infos = (
            (class_data or {})
            .get("rxclassDrugInfoList", {})
            .get("rxclassDrugInfo") or []
        )
        if not drug_infos:
            return []

        class_id = drug_infos[0]["rxclassMinConceptItem"]["classId"]

        # Step 2: get all members of that ATC class
        members_key = f"rxclass:members:{class_id}"

        def fetch_members():
            url = f"{RXNORM_BASE}/rxclass/classMembers.json"
            resp = httpx.get(url, params={"classId": class_id, "relaSource": "ATC"}, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

        members_data = cached_get(members_key, fetch_members, TTL_RXNORM)

        members = (
            (members_data or {})
            .get("drugMemberGroup", {})
            .get("drugMember") or []
        )

        results = []
        for m in members:
            concept = m.get("minConcept", {})
            alt_rxcui = concept.get("rxcui", "")
            alt_name = concept.get("name", "")
            if alt_rxcui == rxcui:  # exclude self
                continue
            results.append({
                "rxcui": alt_rxcui,
                "name": alt_name,
                "confidence": "class-member",
            })
            if len(results) >= 10:  # cap at 10
                break

        return results

    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    mcp.run()
