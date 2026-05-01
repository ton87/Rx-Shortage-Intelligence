# Briefing Diff — Tradeoffs

## Diff approach: set-based vs incremental

| Approach | Pro | Con |
|----------|-----|-----|
| **Set ops on (rxcui, status) tuples** (chosen) | O(n+m), simple, deterministic | Misses non-RxCUI records (~10% of FDA data) |
| Per-record full comparison | Captures all fields | Slow, complex semantics |
| Hash-based diff | Fast | Doesn't tell you *what* changed |

Set-based wins on simplicity. Drop ~10% RxCUI-less records (will be picked up at v0.2 with name-fallback matching).

## Severity: pure rules vs LLM-only vs hybrid

| Approach | Pro | Con |
|----------|-----|-----|
| Pure rules | Deterministic, fast, explainable | Misses clinical nuance |
| LLM-only | Captures nuance | Slow, expensive, can hallucinate severity |
| **Hybrid: rules pre-classify, LLM rationalizes + can override** (chosen) | Best of both | LLM override coordination |

Rules do the heavy lift. LLM owns *rationale text*, may override only with explicit reason.

## Confidence: rule ceiling vs LLM-reported

| Approach | Pro | Con |
|----------|-----|-----|
| **Rule ceiling, LLM ≤ ceiling** (chosen) | Prevents overconfidence on weak signals | LLM may be too cautious |
| LLM-reported only | Captures context | Hallucinated certainty |
| Rule-only | Defensible | Misses semantic uncertainty |

Ceiling: class-member alts max at "medium". Name-fallback used → max "medium". Tool error → max "low".

## Diff bucket semantics

| Bucket | Definition | UI placement |
|--------|------------|--------------|
| **new** | In today, not in yesterday | Top — first attention |
| **escalated** | Status got worse | Mixed in with new |
| **improved** | Status got better | Below escalated |
| **resolved** | In yesterday, not in today | Bottom — good news |
| **unchanged** | Same status both days | NOT surfaced |

PRD §10.3: green/amber/red severity. Bucket → severity is an indirect mapping done by classifier.

## Why no "all 30 drugs every day"

PRD principle 4: customer-relevance > universal content. If a drug's status is unchanged, surfacing it is noise. Skip `unchanged` bucket entirely.

## What we accept

- ~10% RxCUI-less FDA records dropped silently. Logged as `dropped_no_rxcui` count.
- Severity rules are coarse — eval harness measures whether they hit ≥90% appropriateness.
- Override path (LLM disagrees with rule) is rare; v0.2 audits override frequency.
- Resolved items don't get full agent run — just diff detection + simple summary.
