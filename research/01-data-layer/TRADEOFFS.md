# Data Layer — Tradeoffs

## Live API vs cached snapshot for FDA shortages
https://faqs-comparing-resulting-oral.trycloudflare.com
| Approach | Pro | Con |
|----------|-----|-----|
| **Live fetch every briefing** (chosen) | Real, current, defensible | Rate limit risk; demo-day API outage = dead |
| Cached snapshot at H1, reused all day | Fast, no API risk on demo | Stale; weakens "real public APIs" claim |

**Mitigation**: live fetch wrapped by diskcache 1-hr TTL — best of both. Demo runs hit cache; cache invalidates between demos.

## Synthetic formulary: hand-curated vs sampled-from-feed

| Approach | Pro | Con |
|----------|-----|-----|
| **Sampled from live shortage feed** (chosen) | Guaranteed overlap, real RxCUIs, demos shortage-affected items | Drugs are arbitrary; may not match a "realistic" hospital |
| Hand-curated 30 representative hospital drugs | Looks like a real formulary | Coin-flip on overlap with today's shortage list — empty demo possible |
| Curated + sampled hybrid | Best of both | More effort; +20 min |

Sampled-from-feed accepted because demo continuity > formulary realism. Anton can swap in a real curated list at v0.2.

## Therapeutic alternatives source

Decided in clarifying questions. RxClass class members chosen over hand-curated table or DrugBank.

**Drawback**: ATC class includes drugs with very different clinical profiles. Filter is critical:
1. Same `route_of_administration`
2. Not also in current shortage
3. On formulary (preferred > restricted > non-formulary)
4. Confidence tag = "class-member" never "equivalent"

Without filters, the agent will suggest oral atorvastatin as an "alternative" to IV methotrexate. Disaster.

## Yesterday snapshot: real persistence vs fabricated

Real persistence requires running the system >1 day. Hackathon = 6 hr. So fabrication is forced choice.

**Drawback**: yesterday data is fictional, must be labeled. Add disclaimer in UI: "Yesterday baseline is synthetic for v0.1 demo."

## Storage: JSON files vs SQLite

| Approach | Pro | Con |
|----------|-----|-----|
| **Local JSON** (chosen) | Demoable, diffable, zero infra | Unsafe under concurrent writes |
| SQLite | Atomic writes, query flexibility | Schema migration overhead; less demoable |
| DuckDB | Analytics-friendly | Overkill for v0.1 |

JSON wins on hackathon simplicity. v0.2 can introduce SQLite when multi-user appears.

## Field-level decisions

- **Strip openFDA `openfda` nested object** at ingest time: too much metadata, blow up token count. Keep only `rxcui`, `generic_name`, `brand_name`, `route`.
- **Don't store full label JSON in formulary**. Fetch on demand, cache disk-side.
- **Yesterday snapshot regenerated only if file missing**. Otherwise diff drifts every run.

## What we explicitly punt

- Real ASHP cross-reference (PRD §15 risk: FDA shortage data quality varies). v0.2.
- Drug pricing data. PRD §9.4 out of scope.
- Brand-vs-generic NDC reconciliation. RxNorm gives us RxCUI; that's enough for v0.1.
- Compounded drug handling. Out of scope.
