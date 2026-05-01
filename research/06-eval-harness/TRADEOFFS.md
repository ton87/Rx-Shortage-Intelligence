# Eval Harness — Tradeoffs

## Custom harness vs framework

| Approach | Pro | Con |
|----------|-----|-----|
| **Custom Python module** (chosen) | Tailored to 5 PRD-aligned dims; no learning curve | Reinvents some wheels |
| Promptfoo | YAML-config harness, popular | Adds dep; output format different from PRD |
| Inspect AI (UK AISI) | Strong reproducibility | Heavy install; multi-process orchestration |
| OpenAI evals | Battle-tested patterns | OpenAI-flavored, not Anthropic-native |

Custom wins for v0.1. Each dim aligns with a PRD §9.2 KR — easier to write 50 LOC than to map onto a generic framework.

## Scoring: deterministic vs LLM-judge

| Dim | Method | Why |
|-----|--------|-----|
| Citation accuracy | Deterministic (URL HTTPable check) | Binary, no judgment |
| Severity accuracy | Deterministic (string match) | Bucket-level, no judgment |
| Recall | Deterministic (set membership) | No judgment |
| Hallucination | Hybrid | Check RxCUI/NDC against known set + LLM for narrative claims |
| Clinical appropriateness | LLM judge | Semantic, requires clinical judgment |

LLM judge only where deterministic fails. Avoids judge-model bias on objective dims.

## Judge model: Claude vs Haiku vs human

| Approach | Pro | Con |
|----------|-----|-----|
| **Claude Sonnet 4.6 as judge** (chosen v0.1) | Same model = self-consistent; available | Self-judging risk |
| Haiku 4.5 as judge | Cheaper | Less nuanced clinical judgment |
| Human spot-check | Gold standard | Not feasible in 6-hr build |
| Different vendor (GPT-4) | Decoupled | API key + dep |

v0.2: add Haiku as cheap pre-screen + Sonnet for borderline cases. v0.3: human in the loop on a sample.

## 15 cases — why this number

PRD §9.2 says 15. Big enough for stratified coverage (5 Critical / 7 Watch / 3 Resolved), small enough to run in <2 min and hand-curate well.

If we cut: ≥5 cases minimum for any signal. Stratification breaks below 6.

## v1 vs v2 scaffolding (not exercised)

PRD wants side-by-side. v0.1 ships v1 only with hook for v2:

```python
def run_suite(prompt_version: str):  # 'v1' or 'v2'
    ...

# v0.1 deliverable
v1 = run_suite("v1")
v2 = None  # placeholder

save({"v1": v1, "v2": v2})
```

If H6 has time, write v2 prompt = v1 with severity rubric tweaked for "consider order velocity trend." Re-run.

## Cases stable vs generated

| Approach | Pro | Con |
|----------|-----|-----|
| **Hand-curated 15 cases** (chosen) | Stable test surface; results comparable across runs | Manual to extend |
| LLM-generated cases | Can scale to 1000s | Not reproducible; quality unverified |
| Real-world traces | Most realistic | Requires deployment first |

Hand-curated for v0.1. v1.0 can mine real briefings for new cases.

## Recall denominator

What's "all formulary-affecting shortages"? Defined as:
- RxCUI is in synthetic_formulary AND
- Today's status is "Current" AND
- Active orders > 0 (low-volume = informational)

Computed from input data, not hand-labeled. Recall = (surfaced ∩ ground_truth) / |ground_truth|.

For 15-case run: each case is a single drug, so recall is whether the briefing item exists at all. Real recall meaningful only on full-formulary runs.

## Cost of running the suite

15 LLM calls (briefing) + 15 judge calls = ~$0.15-$0.20 per full run. Run once at H6, persist.

Cache the actual outputs in `data/eval_results.json`. UI eval tab is read-only.

## What we accept

- Single-judge bias (Sonnet judging Sonnet output)
- 15-case ceiling for v0.1
- v2 not actually run, only scaffolded
- No time-series tracking (regression detection across runs is v0.2)
- No false-positive cases (currently no "should NOT be surfaced" cases — could add 3-5 in v0.2)
