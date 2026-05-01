"""
POC: layered prompt cache_control on system blocks.

Run: ANTHROPIC_API_KEY=... python research/03b-caching/POC-prompt-cache-tiers.py

Demonstrates:
- 3 cacheable system blocks (role, rubric, formulary)
- Per-drug user message stays dynamic
- Cache write on call 1, cache reads on calls 2-3
- usage breakdown per call
"""

import os
import json
import anthropic

MODEL = "claude-sonnet-4-6"

ROLE_PROMPT = (
    "You are a clinical pharmacist briefing assistant. "
    "You surface drug shortages affecting a specific hospital's formulary. "
    "Every claim must cite a source. Never invent drugs or NDC codes. "
    "Output strict JSON matching the BriefingItem schema. "
    + ("Detailed role rules continue. " * 150)
)

SEVERITY_RUBRIC = (
    "SEVERITY CLASSIFICATION RUBRIC v1: "
    "Critical = active orders >0 AND no formulary alternative AND IV/restricted route. "
    "Watch = active orders >0 AND alternative exists. "
    "Resolved = no longer in shortage feed but recently was. "
    + ("Detailed severity examples follow. " * 150)
)

FORMULARY = json.dumps({
    "drugs": [
        {"rxcui": str(2000 + i), "name": f"drug-{i}", "formulary_status": "preferred", "route": "IV"}
        for i in range(40)
    ]
}, sort_keys=True)


def call(drug_name: str, client: anthropic.Anthropic) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=[
            {"type": "text", "text": ROLE_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": SEVERITY_RUBRIC, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"FORMULARY:\n{FORMULARY}", "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": f"Briefly classify severity for: {drug_name}. One sentence."}],
    )
    return dict(resp.usage)


def fmt(u: dict) -> str:
    return (
        f"input={u.get('input_tokens', 0):>5} | "
        f"cache_write={u.get('cache_creation_input_tokens', 0):>5} | "
        f"cache_read={u.get('cache_read_input_tokens', 0):>5} | "
        f"output={u.get('output_tokens', 0):>4}"
    )


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first.")
        exit(1)

    client = anthropic.Anthropic()
    drugs = ["cisplatin", "methotrexate", "vincristine"]

    cumulative_cost = 0.0
    for i, d in enumerate(drugs, 1):
        u = call(d, client)
        write = u.get("cache_creation_input_tokens", 0) * 1.25 * 3 / 1_000_000
        read = u.get("cache_read_input_tokens", 0) * 0.1 * 3 / 1_000_000
        dyn_in = u.get("input_tokens", 0) * 3 / 1_000_000
        out = u.get("output_tokens", 0) * 15 / 1_000_000
        cost = write + read + dyn_in + out
        cumulative_cost += cost
        print(f"Call {i} ({d}):  {fmt(u)}  $={cost:.5f}")

    print(f"\nCumulative cost (3 drugs): ${cumulative_cost:.5f}")
    print(f"Projected 30-drug cost:    ${cumulative_cost * 10:.5f}")
