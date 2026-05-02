"""openFDA label MCP server — implemented in H2."""

import httpx
from mcp.server.fastmcp import FastMCP

from src.cache import cached_get, TTL_OPENFDA_LABEL

BASE = "https://api.fda.gov/drug/label.json"

KEEP_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings",
    "boxed_warning",
    "drug_interactions",
    "clinical_pharmacology",
]

mcp = FastMCP("drug-label")


@mcp.tool()
def get_drug_label_sections(
    rxcui: str,
    sections: list[str] | None = None,
    drug_name: str | None = None,
) -> dict:
    """Fetch a drug label from openFDA by RxCUI and return filtered sections."""
    try:
        # Primary lookup by RxCUI
        primary_url = f"{BASE}?search=openfda.rxcui%3A{rxcui}&limit=1"
        key = f"label:rxcui:{rxcui}"

        def _fetch_by_rxcui():
            params = {"search": f"openfda.rxcui:{rxcui}", "limit": 1}
            resp = httpx.get(BASE, params=params, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

        data = cached_get(key, _fetch_by_rxcui, TTL_OPENFDA_LABEL)

        label = None
        source_url = primary_url

        # Extract label from primary response
        if data and data.get("results"):
            label = data["results"][0]

        # Fallback: try exact RxCUI search or name-based search
        if label is None:
            if drug_name:
                # Use provided drug_name for fallback
                fallback_name = drug_name
                fallback_url = f"{BASE}?search=openfda.generic_name%3A{fallback_name}*&limit=1"
                fallback_key = f"label:name:{fallback_name}"

                def _fetch_by_name():
                    params = {
                        "search": f"openfda.generic_name:{fallback_name}*",
                        "limit": 1,
                    }
                    resp = httpx.get(BASE, params=params, timeout=15)
                    if resp.status_code == 404:
                        return None
                    resp.raise_for_status()
                    return resp.json()

                fallback_data = cached_get(fallback_key, _fetch_by_name, TTL_OPENFDA_LABEL)
                if fallback_data and fallback_data.get("results"):
                    label = fallback_data["results"][0]
                    source_url = fallback_url
            else:
                # Fallback: try to extract generic_name from a broader search
                # and use it to look up the label
                fallback_key = f"label:rxcui:exact:{rxcui}"

                def _fetch_by_exact_rxcui():
                    # Try to find any label with this rxcui to get the generic_name
                    params = {
                        "search": f"openfda.rxcui.exact:{rxcui}",
                        "limit": 1,
                    }
                    resp = httpx.get(BASE, params=params, timeout=15)
                    if resp.status_code == 404:
                        return None
                    resp.raise_for_status()
                    return resp.json()

                fallback_data = cached_get(fallback_key, _fetch_by_exact_rxcui, TTL_OPENFDA_LABEL)

                if fallback_data and fallback_data.get("results"):
                    label = fallback_data["results"][0]
                    # Use the generic name from the result for source_url
                    generic_names = label.get("openfda", {}).get("generic_name", [])
                    if generic_names:
                        gname = generic_names[0]
                        source_url = f"{BASE}?search=openfda.generic_name%3A%22{gname}%22&limit=1"
                    else:
                        source_url = f"{BASE}?search=openfda.rxcui.exact%3A{rxcui}&limit=1"

        if label is None:
            return {"error": f"No label found for RxCUI {rxcui}"}

        # Determine which sections to return
        if sections is not None:
            # Return only the intersection of requested sections and KEEP_SECTIONS
            active_sections = [s for s in sections if s in KEEP_SECTIONS]
        else:
            active_sections = KEEP_SECTIONS

        # Build result with filtered sections
        result = {}
        for section in active_sections:
            val = label.get(section)
            if val is not None:
                if isinstance(val, list):
                    result[section] = "\n".join(val)
                else:
                    result[section] = str(val)

        result["source_url"] = source_url
        return result

    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def search_labels_by_indication(query: str) -> list[dict]:
    """Search openFDA drug labels by indication and return matching entries."""
    try:
        source_url = f"{BASE}?search=indications_and_usage%3A{query}"
        key = f"label:indication:{query}"

        def _fetch():
            params = {"search": f"indications_and_usage:{query}", "limit": 5}
            resp = httpx.get(BASE, params=params, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

        data = cached_get(key, _fetch, TTL_OPENFDA_LABEL)

        if not data or not data.get("results"):
            return []

        results = []
        for record in data["results"]:
            openfda = record.get("openfda", {})
            generic_name = openfda.get("generic_name", [None])[0] if openfda.get("generic_name") else None
            rxcui = openfda.get("rxcui", [])
            indications_raw = record.get("indications_and_usage", [])
            if isinstance(indications_raw, list):
                indications_text = "\n".join(indications_raw)
            else:
                indications_text = str(indications_raw)
            results.append({
                "generic_name": generic_name,
                "rxcui": rxcui,
                "indications_and_usage": indications_text[:300],
                "source_url": source_url,
            })

        return results

    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    mcp.run()
