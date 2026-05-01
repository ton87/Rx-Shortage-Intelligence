"""
POC: eval runner — load cases, run mock briefing function, score, persist.

Run: python research/06-eval-harness/POC-eval-runner.py

In real H6, replace `mock_generate_briefing_item()` with the actual generator
imported from src.briefing.

Demonstrates:
- Case loading
- Per-case scoring across 5 dimensions
- Deterministic checks (citation, severity, recall, naive hallucination)
- Claude-as-judge stub for clinical appropriateness
- Aggregate metrics
- v1 vs v2 hook
"""

import json
from pathlib import Path

CASES_PATH = Path(__file__).parent / "POC-eval-cases.json"
OUT_PATH = Path(__file__).parent.parent.parent / "data" / "eval_results.json"


def mock_generate_briefing_item(case_input: dict, prompt_version: str = "v1") -> dict:
    """Stand-in for the real generator. Returns a plausible briefing item."""
    bucket_to_severity = {
        "new": "Watch",
        "escalated": "Critical",
        "improved": "Watch",
        "resolved": "Resolved",
    }
    return {
        "rxcui": case_input["rxcui"],
        "drug_name": case_input["drug_name"],
        "severity": bucket_to_severity.get(case_input["diff_bucket"], "Watch"),
        "summary": f"{case_input['drug_name']} status from FDA feed.",
        "rationale": f"Active orders: {case_input['active_orders_30d']}.",
        "alternatives": [],
        "citations": [{"claim": "FDA shortage record", "source_url": "https://api.fda.gov/drug/shortages.json"}],
        "confidence": "medium",
        "recommended_action": "Review with prescriber.",
    }


def score_citation_accuracy(actual: dict) -> float:
    citations = actual.get("citations", [])
    if not citations:
        return 0.0
    has_url = sum(1 for c in citations if c.get("source_url", "").startswith("http"))
    return has_url / len(citations)


def score_severity_match(expected: dict, actual: dict) -> bool:
    return expected.get("severity") == actual.get("severity")


def score_hallucination(case_input: dict, actual: dict) -> float:
    """Simple check: any drug name in alternatives that lacks an RxCUI."""
    invented_count = 0
    for alt in actual.get("alternatives", []):
        if not alt.get("rxcui"):
            invented_count += 1
    return invented_count / max(len(actual.get("alternatives", [])), 1)


def score_clinical_appropriateness_mock(actual: dict) -> int:
    """Stub for Claude-as-judge. Returns 1-5."""
    if actual.get("severity") and actual.get("rationale"):
        return 4
    return 2


def score_recall(case: dict, actual: dict) -> bool:
    """For a single case, recall = was the item surfaced at all (severity != null)."""
    return actual.get("severity") is not None


def score_case(case: dict, actual: dict) -> dict:
    return {
        "citation_accuracy": score_citation_accuracy(actual),
        "severity_match": score_severity_match(case["expected"], actual),
        "hallucination_rate": score_hallucination(case["input"], actual),
        "clinical_appropriateness": score_clinical_appropriateness_mock(actual),
        "recall": score_recall(case, actual),
    }


def aggregate(per_case: list[dict]) -> dict:
    n = len(per_case)
    if n == 0:
        return {}
    return {
        "n_cases": n,
        "citation_accuracy": sum(c["scores"]["citation_accuracy"] for c in per_case) / n,
        "severity_accuracy": sum(1 for c in per_case if c["scores"]["severity_match"]) / n,
        "hallucination_rate": sum(c["scores"]["hallucination_rate"] for c in per_case) / n,
        "clinical_appropriateness_avg": sum(c["scores"]["clinical_appropriateness"] for c in per_case) / n,
        "recall": sum(1 for c in per_case if c["scores"]["recall"]) / n,
    }


def run_suite(prompt_version: str = "v1") -> dict:
    cases = json.loads(CASES_PATH.read_text())
    per_case = []
    for case in cases:
        actual = mock_generate_briefing_item(case["input"], prompt_version)
        scores = score_case(case, actual)
        per_case.append({"case_id": case["case_id"], "scores": scores, "actual": actual})
    return {
        "prompt_version": prompt_version,
        "results": per_case,
        "aggregate": aggregate(per_case),
    }


if __name__ == "__main__":
    print(f"Loading cases from {CASES_PATH}")
    if not CASES_PATH.exists():
        print("Cases file not found. Aborting.")
        exit(1)

    print("\n=== Running v1 suite ===")
    v1 = run_suite("v1")
    print(f"Cases: {v1['aggregate']['n_cases']}")
    print(f"Severity accuracy: {v1['aggregate']['severity_accuracy']:.0%}")
    print(f"Citation accuracy: {v1['aggregate']['citation_accuracy']:.0%}")
    print(f"Hallucination rate: {v1['aggregate']['hallucination_rate']:.1%}")
    print(f"Clinical (avg 1-5): {v1['aggregate']['clinical_appropriateness_avg']:.1f}")
    print(f"Recall: {v1['aggregate']['recall']:.0%}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"v1": v1, "v2": None}, indent=2))
    print(f"\nWrote {OUT_PATH}")
