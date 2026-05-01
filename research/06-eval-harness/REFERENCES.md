# Eval Harness — References

## PRD anchors

- §9.2 Objective 2: clinical safety / quality KRs
- FR-7: eval harness 15 cases × 5 dims, v1 vs v2 side-by-side
- §9.3 NFR-2: cost <$0.05 (eval is one-time, not per-briefing)
- §13.5 failure modes: hallucination → eval is the verification

## Methodology background

- LLM-as-judge: https://arxiv.org/abs/2306.05685 (Zheng et al)
- Inter-rater reliability for clinical scoring: Cohen's kappa, weighted kappa
- BLEU/ROUGE NOT used — citation accuracy is HTTP-resolvable, not text-similar

## Related frameworks (for v0.2 evaluation)

- Promptfoo: https://promptfoo.dev/
- Inspect AI: https://inspect.ai-safety-institute.org.uk/
- OpenAI Evals: https://github.com/openai/evals

## Internal POCs

- `POC-eval-runner.py` — load + score + persist
- `POC-eval-cases.json` — 15 hand-curated cases
- `COST-MATH.md` (in 03b-caching) — eval run cost estimate

## Related research

- Confidence ceiling rules: `research/04-briefing-diff/POC-severity-classifier.py`
- Citation enforcement: `research/03-agent-loop/LESSON.md` §Citations
