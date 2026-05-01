# Cost Math — $0.05/briefing target

## Sonnet 4.6 pricing

| Type | Cost per 1M tokens |
|------|-------------------|
| Input (uncached) | $3.00 |
| Cache write (5-min ephemeral) | $3.00 × 1.25 = $3.75 |
| Cache write (1-hr ephemeral) | $3.00 × 2.00 = $6.00 |
| Cache read | $3.00 × 0.10 = $0.30 |
| Output | $15.00 |

## Briefing workload

- 30-drug formulary
- ~10 drugs hit the diff (rest unchanged)
- Per-drug input context: ~6K tokens (system + rubric + formulary + label chunks + drug-specific)
- Per-drug output: ~400 tokens (one BriefingItem JSON)

## Scenario A: no caching, 1 call per drug

| Item | Tokens | Cost |
|------|--------|------|
| Input × 10 drugs | 60K | $0.18 |
| Output × 10 | 4K | $0.06 |
| **Total** | | **$0.24** |

5× over budget.

## Scenario B: prompt caching, 1 call per drug

System blocks (5K tokens) cached. Per-drug dynamic input ~1K.

| Item | Tokens | Cost |
|------|--------|------|
| Cache write (call 1) | 5K | $0.0188 |
| Cache reads (calls 2-10) | 45K | $0.0135 |
| Dynamic input × 10 | 10K | $0.0300 |
| Output × 10 | 4K | $0.0600 |
| **Total** | | **$0.122** |

2.5× over budget. Better but still over.

## Scenario C: prompt caching + batching (5 drugs/call)

2 calls. Cache writes once, reads once.

| Item | Tokens | Cost |
|------|--------|------|
| Cache write (call 1) | 5K | $0.0188 |
| Cache read (call 2) | 5K | $0.0015 |
| Dynamic input × 2 | 5K (2.5K each) | $0.0150 |
| Output × 2 | 4K (2K each, 5 items × 400 tok) | $0.0600 |
| **Total** | | **$0.095** |

~2× over budget.

## Scenario D: caching + batching + max_tokens cap

Force `max_tokens=1500` per call. Tighter JSON output.

| Item | Tokens | Cost |
|------|--------|------|
| Cache write | 5K | $0.0188 |
| Cache read | 5K | $0.0015 |
| Dynamic input × 2 | 5K | $0.0150 |
| Output × 2 | 3K | $0.0450 |
| **Total** | | **$0.080** |

~1.6× over budget. Honest target for v0.1.

## Scenario E (v0.2 path): mixture of models

- Haiku 4.5 ($1/$5 per M) for first-pass screening: which drugs need full briefing?
- Sonnet 4.6 only for the 3-5 high-stakes items.

| Item | Tokens | Cost |
|------|--------|------|
| Haiku screen all 30 (cached) | 8K input + 2K output | $0.018 |
| Sonnet detail × 5 items | similar to D | $0.040 |
| **Total** | | **$0.058** |

Hits target. Reserved for v0.2.

## Honest disclosure for v0.1

PRD §9.3 says <$0.05/briefing. v0.1 ships at ~$0.08-$0.10. Document in demo:

> "v0.1 cost is ~$0.09/briefing on Sonnet 4.6 with full caching + batching. v0.2 will route screening through Haiku 4.5 to hit the <$0.05 target. The cost gap is intentional — Sonnet quality is non-negotiable for a clinical safety product, and we'd rather ship the right model and document the cost path than under-deliver on accuracy."

## Verification

After H6, run one full briefing and check `response.usage`:

```python
total_write = sum(r.usage.cache_creation_input_tokens for r in responses)
total_read = sum(r.usage.cache_read_input_tokens for r in responses)
total_dyn = sum(r.usage.input_tokens for r in responses)
total_out = sum(r.usage.output_tokens for r in responses)

cost = (
    total_write * 1.25 * 3 / 1_000_000 +
    total_read * 0.1 * 3 / 1_000_000 +
    total_dyn * 3 / 1_000_000 +
    total_out * 15 / 1_000_000
)
print(f"Briefing cost: ${cost:.4f}")
```

Surface this in the eval tab.
