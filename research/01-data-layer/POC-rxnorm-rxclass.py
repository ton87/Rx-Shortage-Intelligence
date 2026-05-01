"""
POC: RxNorm name normalization + RxClass therapeutic class members as alternatives proxy.

Run: python research/01-data-layer/POC-rxnorm-rxclass.py

Demonstrates:
- RxNorm /rxcui.json?name=...
- RxClass /class/byRxcui to find ATC class
- RxClass /classMembers to enumerate drugs in same class
- Why this is a proxy, not true equivalence
"""

import httpx

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
RXCLASS_BASE = "https://rxnav.nlm.nih.gov/REST/rxclass"


def normalize_name_to_rxcui(name: str) -> str | None:
    """Drug name → RxCUI."""
    resp = httpx.get(f"{RXNORM_BASE}/rxcui.json", params={"name": name}, timeout=10)
    resp.raise_for_status()
    ids = (resp.json().get("idGroup") or {}).get("rxnormId") or []
    return ids[0] if ids else None


def get_atc_class(rxcui: str) -> dict | None:
    """RxCUI → ATC therapeutic class."""
    params = {"rxcui": rxcui, "relaSource": "ATC"}
    resp = httpx.get(f"{RXCLASS_BASE}/class/byRxcui.json", params=params, timeout=10)
    resp.raise_for_status()
    items = (resp.json().get("rxclassDrugInfoList") or {}).get("rxclassDrugInfo") or []
    if not items:
        return None
    # First-level ATC class
    return items[0].get("rxclassMinConceptItem")


def get_class_members(class_id: str) -> list[dict]:
    """ATC class → list of member drugs."""
    params = {"classId": class_id, "relaSource": "ATC"}
    resp = httpx.get(f"{RXCLASS_BASE}/classMembers.json", params=params, timeout=15)
    resp.raise_for_status()
    items = (resp.json().get("drugMemberGroup") or {}).get("drugMember") or []
    return [item.get("minConcept") for item in items if item.get("minConcept")]


def get_alternatives(drug_name: str, exclude_rxcuis: set[str] = None) -> list[dict]:
    """Top-level: drug name → list of class-member alternatives."""
    exclude = exclude_rxcuis or set()
    rxcui = normalize_name_to_rxcui(drug_name)
    if not rxcui:
        return []

    cls = get_atc_class(rxcui)
    if not cls:
        return []

    members = get_class_members(cls["classId"])
    # Filter out the original drug + caller-excluded
    return [
        m for m in members
        if m.get("rxcui") and m["rxcui"] != rxcui and m["rxcui"] not in exclude
    ]


if __name__ == "__main__":
    name = "cisplatin"
    print(f"=== Normalize: {name} ===")
    rxcui = normalize_name_to_rxcui(name)
    print(f"RxCUI: {rxcui}\n")

    print(f"=== ATC class for RxCUI {rxcui} ===")
    cls = get_atc_class(rxcui)
    print(f"Class: {cls}\n")

    if cls:
        print(f"=== Class members (alternatives proxy) ===")
        members = get_class_members(cls["classId"])
        for m in members[:15]:
            print(f"  {m.get('name')} (RxCUI {m.get('rxcui')})")

    print("\n=== Caveat ===")
    print("RxClass class membership ≠ true therapeutic equivalence.")
    print("Filter by route_of_administration + formulary_status before surfacing.")
