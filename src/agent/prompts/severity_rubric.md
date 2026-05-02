This rubric is the deterministic backbone of severity classification. Apply it before letting
LLM judgment vary. Rules are listed in priority order; the first matching rule sets severity.
After rule-based assignment, you may add nuance via the rationale field, but you may NOT
upgrade or downgrade severity except per the explicit override rules at the end.

# Inputs the classifier sees

Per candidate drug, you have:
- formulary_status: preferred | non-preferred | not-on-formulary
- route_of_administration: IV | IM | SubQ | PO | topical | inhaled | other
- active_orders_30d: integer count of orders for this drug in last 30 days at this hospital
- departments: list of hospital departments ordering it (Oncology, Surgery, ICU, ED, etc.)
- today_status: Current | To Be Discontinued | Resolved
- yesterday_status: Current | To Be Discontinued | Resolved | Available with limitations | (absent)
- preferred_alternatives: list of RxCUIs the formulary lists as substitutes (may be empty)
- has_label_data: bool — did openFDA return any usable sections?
- alts_in_shortage: list of alternatives that are themselves currently in shortage
- alts_route_match: list of alternatives matching the drug's route of administration

# Severity rules (apply in order, first match wins)

Rule C1 (Critical):
  today_status in {"Current", "To Be Discontinued"}
  AND formulary_status == "preferred"
  AND active_orders_30d > 20
  AND (preferred_alternatives - alts_in_shortage) is empty
  → Critical. Reason: high-volume preferred drug with no available alternative.

Rule C2 (Critical):
  today_status in {"Current", "To Be Discontinued"}
  AND route_of_administration in {"IV", "IM"}
  AND any department in {"ICU", "ED", "Oncology", "Surgery", "Anesthesia"}
  AND (preferred_alternatives - alts_in_shortage) is empty
  → Critical. Reason: critical-care route, no alternative.

Rule C3 (Critical — escalation):
  yesterday_status == "Resolved" AND today_status == "Current"
  AND formulary_status in {"preferred", "non-preferred"}
  AND active_orders_30d > 0
  → Critical. Reason: re-occurring shortage on actively-used drug.

Rule C4 (Critical — discontinuation):
  today_status == "To Be Discontinued"
  AND formulary_status == "preferred"
  AND active_orders_30d > 0
  → Critical. Reason: permanent loss of preferred drug; P&T action required.

Rule W1 (Watch):
  today_status in {"Current", "To Be Discontinued"}
  AND formulary_status in {"preferred", "non-preferred"}
  AND active_orders_30d between 1 and 20 inclusive
  AND at least one alternative exists and is not itself in shortage
  → Watch. Reason: moderate volume, alternative available.

Rule W2 (Watch):
  today_status == "Current"
  AND formulary_status == "non-preferred"
  AND active_orders_30d > 0
  → Watch. Reason: non-preferred drug, smaller impact.

Rule W3 (Watch):
  today_status == "Current"
  AND yesterday_status == today_status
  AND no rule above triggered
  → Watch. Reason: ongoing shortage, no change.

Rule R1 (Resolved):
  yesterday_status in {"Current", "To Be Discontinued"}
  AND today_status == "Resolved"
  → Resolved. Reason: shortage cleared. Surface as good news; do not require alternatives.

Rule R2 (Resolved — drop):
  today_status == "Resolved"
  AND yesterday_status is absent or also "Resolved"
  → Do not surface this item. Already cleared, not new information.

Default:
  No rule matched → Watch with confidence: low and rationale noting which inputs were missing.

# Override rules (use sparingly, document reason)

You MAY upgrade Watch → Critical only if:
- The drug is single-source (no clinical alternative exists for its indication) AND has any active orders.

You MAY downgrade Critical → Watch only if:
- All preferred_alternatives are themselves in shortage BUT a non-formulary clinical equivalent
  with abundant supply exists AND can be added to formulary via P&T (rationale must name it).

You MAY NOT downgrade Critical → Resolved or upgrade Resolved → Watch under any circumstance.

# Worked examples

Example 1 — Cisplatin IV shortage, oncology, no alternatives
Inputs: today_status=Current, formulary_status=preferred, route=IV, departments=[Oncology, Surgery],
active_orders_30d=23, preferred_alternatives=[], alts_in_shortage=[]
Rule C2 matches (IV + Oncology + no alt). Severity = Critical. Confidence high if label data
present and at least one cited indication matches active orders.

Example 2 — Methylphenidate ER tablets shortage, low-volume
Inputs: today_status=Current, formulary_status=non-preferred, route=PO, departments=[Outpatient],
active_orders_30d=4, preferred_alternatives=["12345"], alts_in_shortage=[]
Rule W1 matches. Severity = Watch. Confidence medium (PO route + alt available + low volume).

Example 3 — Bupivacaine HCl injection, no RxCUI in FDA record
Inputs: rxcui list is empty.
Drop from briefing per ROLE_AND_RULES rule on missing RxCUI. No BriefingItem produced.

Example 4 — IV saline returning to supply
Inputs: yesterday_status=Current, today_status=Resolved, formulary_status=preferred.
Rule R1 matches. Severity = Resolved. Surface as good news. No alternatives needed.
Confidence high if cleared status confirmed by FDA detail call.

Example 5 — Ondansetron To Be Discontinued
Inputs: today_status=To Be Discontinued, formulary_status=preferred, active_orders_30d=15,
route=IV, departments=[ED, Oncology, Inpatient].
Rule C4 matches (TBD + preferred + active orders). Severity = Critical. Rationale must call
out P&T action needed for permanent formulary replacement.

# Confidence calculation summary

Rule-based confidence floor (the rule itself):
- Rules C1, C2, C3, C4, R1 → high if data complete
- Rules W1, W2, W3 → medium baseline
- Default → low

Then apply ceilings from ROLE_AND_RULES:
- Class-member alt only → max medium
- Missing label data → max low
- RxCUI ambiguity → max medium
- Yesterday status non-canonical → max medium
- Unknown active_orders_30d → max medium

Final confidence = min(rule floor, all applicable ceilings).