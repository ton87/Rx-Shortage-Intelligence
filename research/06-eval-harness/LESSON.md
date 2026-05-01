# Eval Harness — Lesson

## What this layer owns

The 15-case scoring framework that proves the briefing is correct, cited, and clinically appropriate. Maps directly to PRD §9.2 KRs and FR-7.

## 5 scoring dimensions (PRD §9.2 + FR-7)

| Dimension | Range | Target | What it measures |
|-----------|-------|--------|------------------|
| **Clinical appropriateness** | 1-5 | ≥4 (≥80%) | Is the recommendation clinically sensible? Human-rated semantics |
| **Citation accuracy** | 0-1 | 1.0 (100%) | Every claim links to a verifiable source |
| **Hallucination rate** | 0-1 | <0.02 (<2%) | No invented drugs, NDCs, or facts |
| **Severity accuracy** | 0-1 | ≥0.9 (≥90%) | Critical/Watch/Resolved matches expected |
| **Recall on formulary-affecting** | 0-1 | 1.0 (100%) | No missed shortages affecting the formulary |

## 15 cases by bucket

| Bucket | Count | Examples |
|--------|-------|----------|
| Critical | 5 | cisplatin (no alt + IV + high orders), methotrexate IV, lidocaine IV, heparin, epinephrine |
| Watch | 7 | methotrexate PO, carboplatin, amoxicillin IV, albuterol neb, ibuprofen, ondansetron, acetaminophen |
| Resolved | 3 | vincristine, fentanyl patch, diphenhydramine |

Total = 15. Cases span:
- Routes: IV, IM, PO, Inhalation, Topical
- Specialties: Oncology, ICU, ER, Pediatrics, Ambulatory
- Order volume: 0 to 80+
- Alternative availability: yes / no / partial

## Case shape

Each case is a JSON object. Input = drug context + diff bucket. Expected = bucket assignment + key facts the briefing must capture.

```json
{
  "case_id": "C-01",
  "input": {
    "rxcui": "2555",
    "drug_name": "cisplatin",
    "diff_bucket": "escalated",
    "today_status": "Current",
    "yesterday_status": "Available with limitations",
    "active_orders_30d": 23,
    "departments": ["Oncology", "Surgery"],
    "formulary_status": "preferred",
    "route": "IV",
    "preferred_alternatives": []
  },
  "expected": {
    "severity": "Critical",
    "must_mention_facts": [
      "no formulary alternative",
      "IV-only or restricted",
      "active oncology orders"
    ],
    "must_not_hallucinate": [
      "any RxCUI not in {2555, 40048, ...}",
      "any NDC not retrievable from openFDA"
    ],
    "expected_alternatives_class": "L01XA platinum compounds",
    "min_confidence": "high"
  }
}
```

## Scoring approach

Hybrid: deterministic checks + Claude-as-judge for semantic dims.

| Dimension | Method |
|-----------|--------|
| Citation accuracy | Deterministic: every claim has source_url; URL is HTTPable |
| Severity accuracy | Deterministic: actual_sev == expected_sev |
| Recall | Deterministic: every formulary-affecting shortage in input set was surfaced |
| Hallucination rate | Deterministic + LLM: invented drug names / NDCs detected by check against retrieved data |
| Clinical appropriateness | Claude-as-judge: rate 1-5 against rubric |

### Claude-as-judge rubric

```
You are evaluating a drug shortage briefing item for clinical appropriateness.

Score 1-5:
5 — Recommendation is clinically sound, includes relevant safety considerations,
    alternatives are appropriate for the indication and route.
4 — Sound recommendation but minor omission (e.g., didn't mention dose adjustment).
3 — Defensible but incomplete (e.g., suggests alternative without route match check).
2 — Marginal — would prompt clarifying questions from a pharmacist.
1 — Clinically inappropriate (wrong route, wrong indication, missing safety flag).

Provide score + 1-sentence rationale. Be strict.
```

## v1 vs v2 prompt comparison

PRD §9.2 + FR-7: side-by-side scoring. v0.1 ships v1 only with hook for v2.

```python
def run_suite(prompt_version: str = "v1") -> dict:
    cases = json.load(open("cases.json"))
    results = []
    for case in cases:
        actual = generate_briefing_item(case["input"], prompt_version=prompt_version)
        scores = score_case(case, actual)
        results.append({"case_id": case["case_id"], "scores": scores, "actual": actual})
    return {
        "prompt_version": prompt_version,
        "results": results,
        "aggregate": aggregate_scores(results),
    }


# v0.1: only v1 runs
v1_results = run_suite("v1")
save("data/eval_results.json", {"v1": v1_results, "v2": None})
```

For v2: change a single thing (e.g., severity rubric wording). Re-run. Compare aggregate. Hackathon-time = scaffolded but not exercised.

## Where the harness runs

`src/eval/runner.py` — CLI: `python -m src.eval.runner --prompt-version=v1`. Writes `data/eval_results.json`. UI eval tab reads this file.

## Cost considerations

15 cases × 1 briefing item each = 15 LLM calls + 15 judge calls = 30 calls. Even without batching, ~$0.15 to run full suite. Run once at H6, persist, re-render.

## What can go wrong

- **Judge bias**: Claude-as-judge tends to be lenient. Calibrate: include 2 deliberately wrong actual-outputs in pre-flight to verify judge catches them.
- **Cases drift from data**: if synthetic formulary changes, expected values may need update. Mitigation: cases reference live FDA RxCUIs; expected values are about *behavior* not *content*.
- **Recall calculation requires ground truth**: which shortages are "formulary-affecting"? Defined as: in today's FDA feed AND RxCUI is in formulary. Compute from input data, not by hand.
- **Citation URL HTTPability**: 100% target requires all citations resolve to HTTP 200. Validation step in scorer.
- **Time budget**: 15 cases × ~3 sec each + 15 judge calls × ~2 sec = ~75 sec. Under 5 min budget, fine.

## What we accept for v0.1

- Cases hand-curated, not generated (deliberately — eval set should be stable test surface)
- Judge is single-model (Claude). v0.2: add second judge (Haiku?) for inter-rater reliability
- v2 scaffolded only — actual v2 prompt is "TBD" in PRD, not our job to invent
