# Questions for Anton

Open clarifying questions surfaced during pre-build. Resolve before final demo or note as v0.2 backlog.

---

## Q1 — How to handle FDA `"To Be Discontinued"` status records?

**Date raised**: 2026-05-01 (pre-build smoke test)

**Context**:
- Pre-build smoke test on openFDA Drug Shortage API revealed actual `status` field has 3 values, not 1:
  - `Current` — 1140 records (active shortage)
  - `To Be Discontinued` — 498 records (drug being phased out permanently)
  - `Resolved` — 29 records (no longer in shortage)
- PRD §11.2 + research POCs assumed only `"Currently in Shortage"` (a string that never existed in FDA data).
- ~30% of the FDA feed = `To Be Discontinued`. Non-trivial volume.

**Why it matters**:
- Discontinuation is arguably **more clinically severe** than temporary shortage — drug going away forever, formulary needs permanent alternative, P&T action required.
- Pharmacy directors need to know about TBD drugs in their formulary just as much as Current shortages, possibly more.
- Currently no PRD principle, FR, or severity rule covers TBD.

**v0.1 proposed default**:
- Filter to `status:Current` only.
- Document TBD as v0.2 expansion.
- Rationale: scope discipline, demo focuses on shortage workflow as PRD §2.1 frames.

**Decision needed**:
- (A) v0.1 filters TBD out (proposed default — simplest, on-spec)
- (B) v0.1 includes TBD as Critical severity automatically (broader value, modest H1/H4 cost)
- (C) v0.1 includes TBD as separate severity bucket (e.g., "Discontinuing") — more PRD work, demo surface change
- (D) Other

**Cost of each**: A = 0 min. B = ~10 min H4 (severity classifier branch). C = ~30 min H4 + UI bucket + eval cases.

**Recommendation**: (A) for v0.1, log (B) as v0.2 phase 1 enhancement.

---

## Q2 — How to handle one-shortage-record-to-many-RxCUI relationship?

**Date raised**: 2026-05-01 (pre-build smoke test)

**Context**:
- One generic drug = many products = many RxCUIs. FDA returns `openfda.rxcui` as a list per shortage record.
- Real example from smoke test: "Methylphenidate Hydrochloride Tablet, Extended Release" returned **14 RxCUIs** (different strengths, branded variants, package sizes).
- Other records returned 1, 0, or several. ~80% of records with any RxCUI have >1.
- PRD §11.1 ShortageRecord schema lists `rxcui` as singular field — implies scalar intent. Reality is list.

**Why it matters**:
- **Formulary lookup**: hospital formulary stores one canonical RxCUI per drug. If shortage list is `[A, B, C]` and formulary has `B`, scalar-only lookup misses the match unless we picked `B` first.
- **Severity / orders / route**: all keyed by RxCUI. Need to know which formulation to assess.
- **Therapeutic alternatives**: alts depend on route + strength + dosage form, all RxCUI-specific. Picking the "wrong" RxCUI from the list → wrong alts → patient safety risk per RISKS R3.
- **Citations (PRD Principle 5)**: each citation should round-trip to a specific RxCUI. List shape obscures which.
- **Eval scoring**: hallucination check = "is returned RxCUI in retrieved set?" — set ops differ for scalar vs list.

**v0.1 proposed default**:
- Keep FDA list shape in MCP server output (`rxcui: ["1091155", "1091170", ...]`).
- Index by **every** RxCUI in the list when joining to formulary (1 shortage record → N index entries).
- Agent receives full list, picks the one matching formulary's preferred form for downstream fetches.
- Eval scorer uses set intersection: `agent_rxcui in expected_rxcui_list`.
- Citations name the specific RxCUI the agent reasoned about (not the whole list).

**Decision needed**:
- (A) Keep list, index-by-every (proposed default — honest, catches more matches)
- (B) Take first RxCUI only, lossy but simpler (~80% of records lose data)
- (C) Take first RxCUI matching formulary; fall back to `[0]` (clinical-aware but more code)
- (D) Cross-reference + return canonical via RxNorm normalize call (most accurate, slowest, requires extra API hop)

**Cost**: A = ~10 min (`index_by_rxcui` rewrite). B = 1 min (truncate at trim). C = ~15 min. D = ~30 min + extra API call per record.

**Recommendation**: (A) for v0.1. Closes formulary-lookup miss rate without adding API latency. v0.2 could add (D) as a normalization layer if customers report wrong-formulation alternatives.

**Sub-question**: when the agent surfaces a BriefingItem, which RxCUI from the list should appear in the user-visible `BriefingItem.rxcui`? Options:
- The one matching the formulary entry (recommended — that's the form the hospital actually uses)
- The one the agent fetched a label for
- The full list (UI complexity)

---

## Q3 — Synthetic formulary `preferred_alternatives` population strategy

**Date raised**: 2026-05-01 (pre-build review)

**Context**:
- `POC-synthetic-formulary.py` generates 30 drugs with `preferred_alternatives: []` (empty arrays) for all entries.
- Severity classifier Rule W1 keys on "alternative exists and is not itself in shortage."
- Empty alternatives → every drug looks alternative-less → biases severity toward Critical.
- Eval cases (now corrected) DO have populated alternatives — so eval ground truth diverges from formulary signal.

**Why it matters**:
- Demo realism: a hospital formulary in real life always has preferred alternatives for shortage-prone drugs (P&T pre-curates). Empty arrays = unrealistic data.
- Severity distribution: with empty alternatives, the demo briefing will show "10 critical, 0 watch" instead of a realistic mix. Customer asked for triageable distribution.
- Eval scoring: cases assert `severity: Watch` for drugs with alternatives; if synthetic formulary reports no alternatives for those same drugs, the rule-based pre-filter overrides → severity wrong → eval fails.

**v0.1 proposed default**:
- At H1, populate `preferred_alternatives` for the 5 demo drugs by hand-curating from RxClass class members of each drug's ATC code (already a v0.1 tool capability).
- Document remaining 25 drugs as "demo subset has alternatives, full 30 use empty as 'no preferred alt' signal."

**Decision needed**:
- (A) Hand-populate 5 demo drugs only (proposed — 10 min at H1, demo-defensible)
- (B) Programmatically fetch RxClass alternatives for all 30 (~20 min H1, more work, more demo-realistic)
- (C) Leave empty, surface limitation in demo script ("synthetic formulary intentionally sparse")
- (D) Other

**Recommendation**: (A) for v0.1. (B) is v0.2 quality-of-life.

---

## Q4 — Honest cost target reporting

**Date raised**: 2026-05-01

**Context**:
- PRD NFR-2 specifies <$0.05 per briefing.
- Three docs cite three numbers: COST-MATH.md ($0.08), CLAUDE.md ($0.08-$0.10), `03-agent-loop/LESSON.md` ($0.20).
- Realistic v0.1 cost (with Tier 1 + 2 caching, 30-drug briefing, ~3-5 tool calls per drug) modeled at ~$0.10.
- User chose to drop Tier 3 caching (architectural simplicity > additional cost reduction).

**Why it matters**:
- Customer will see this in the eval tab (PRD §13.3 audit trail requires cost surfaced).
- Three different numbers in three docs = customer notices inconsistency = trust hit per Principle 7.
- Missing the $0.05 NFR by 2x is acceptable if surfaced honestly; missing it by 4x with no acknowledgment is not.

**v0.1 proposed default**:
- Reconcile to single number: ~$0.10 per briefing for v0.1 (claude-sonnet-4-6, Tier 1+2 caching enabled, 30-drug demo).
- Update all three docs to cite this same number.
- In eval tab: display actual cost from `BriefingRun.total_cost_usd` field per PRD §11.1 schema.
- Demo script line: "v0.1 lands at ~$0.10/briefing vs $0.05 NFR. v0.2 path: Haiku screening + Sonnet detail (mixture-of-models) targets $0.04."

**Decision needed**:
- Approve single number (~$0.10) and v0.2 mitigation plan, OR
- Provide alternative target / mitigation framing.

**Recommendation**: lock $0.10 + cite v0.2 mixture-of-models path. 5 min of documentation cleanup tomorrow morning.

---
