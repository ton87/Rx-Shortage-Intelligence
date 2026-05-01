"""
POC: rule-based severity classifier with LLM-rationale stub.

Run: python research/04-briefing-diff/POC-severity-classifier.py

Demonstrates:
- Pure-rule pre-filter (deterministic, fast)
- Pluggable LLM rationale (stubbed here as fixed text)
- Confidence ceiling for class-member alternatives
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
FORMULARY_PATH = ROOT / "data" / "synthetic_formulary.json"
ORDERS_PATH = ROOT / "data" / "active_orders.json"


def classify_severity(diff_bucket: str, item: dict, formulary_entry: dict, orders_entry: dict) -> dict:
    """Return {severity, rationale, confidence_ceiling}."""
    if diff_bucket == "resolved":
        return {
            "severity": "Resolved",
            "rationale": "No longer appears in FDA shortage feed.",
            "confidence_ceiling": "high",
        }

    order_count = (orders_entry or {}).get("count_last_30_days", 0)
    alts = (formulary_entry or {}).get("preferred_alternatives", []) or []
    has_alt = len(alts) > 0
    route = (formulary_entry or {}).get("route_of_administration", "")
    is_iv = route == "IV"
    is_restricted = (formulary_entry or {}).get("restriction_criteria") is not None

    if order_count > 10 and not has_alt and (is_iv or is_restricted):
        return {
            "severity": "Critical",
            "rationale": (
                f"{order_count} active orders in last 30 days, "
                f"{'IV-only ' if is_iv else ''}"
                f"{'restricted ' if is_restricted else ''}"
                "with no formulary alternative."
            ),
            "confidence_ceiling": "high",
        }

    if diff_bucket == "escalated" and order_count > 0:
        return {
            "severity": "Critical",
            "rationale": f"Status worsened since yesterday and {order_count} active orders.",
            "confidence_ceiling": "high",
        }

    if order_count > 0:
        return {
            "severity": "Watch",
            "rationale": (
                f"{order_count} active orders. "
                f"{'Alternative available on formulary.' if has_alt else 'No formulary alternative — monitor.'}"
            ),
            "confidence_ceiling": "medium" if not has_alt else "high",
        }

    return {
        "severity": "Watch",
        "rationale": "No active orders in last 30 days; informational only.",
        "confidence_ceiling": "low",
    }


def apply_confidence_ceiling(reported: str, ceiling: str) -> str:
    """Cap LLM-reported confidence at the rule-based ceiling."""
    rank = {"low": 0, "medium": 1, "high": 2}
    return reported if rank.get(reported, 0) <= rank.get(ceiling, 0) else ceiling


if __name__ == "__main__":
    if not FORMULARY_PATH.exists():
        print("Run POC-synthetic-formulary.py first.")
        exit(1)

    formulary = json.loads(FORMULARY_PATH.read_text())
    orders = json.loads(ORDERS_PATH.read_text())
    formulary_idx = {d["rxcui"]: d for d in formulary["drugs"]}
    orders_idx = {o["rxcui"]: o for o in orders["orders"]}

    print("=== Sample classifications ===\n")
    test_cases = [
        ("escalated", {"rxcui": "2555", "generic_name": "cisplatin"}),
        ("new", {"rxcui": "6851", "generic_name": "methotrexate"}),
        ("resolved", {"rxcui": "11202", "generic_name": "vincristine"}),
        ("unchanged", {"rxcui": "9999", "generic_name": "imaginarydrug"}),
    ]

    for bucket, item in test_cases:
        rxcui = item["rxcui"]
        f_entry = formulary_idx.get(rxcui, {})
        o_entry = orders_idx.get(rxcui, {})
        result = classify_severity(bucket, item, f_entry, o_entry)
        print(f"{item['generic_name']} ({bucket}): {result['severity']}")
        print(f"  Rationale: {result['rationale']}")
        print(f"  Confidence ceiling: {result['confidence_ceiling']}\n")

    print("=== Ceiling test ===")
    print(f"LLM says 'high', ceiling 'medium' → {apply_confidence_ceiling('high', 'medium')}")
    print(f"LLM says 'low', ceiling 'high' → {apply_confidence_ceiling('low', 'high')}")
