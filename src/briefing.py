"""
Briefing generation + diff logic.

CLI: python -m src.briefing
  → Generates today's briefing, writes data/briefings/YYYY-MM-DD.json

generate_briefing(date_str=None) → BriefingRun dict
compute_diff(today, yesterday, formulary_rxcuis) → DiffResult dict
"""

import asyncio
import json
import re
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.domain.fda import status_rank
from src.domain.constants import (
    DEFAULT_CANDIDATE_CAP,
    FDA_FETCH_LIMIT,
    PER_DRUG_TIMEOUT_S,
    CUSTOMER_ID,
    PROMPT_VERSION,
    SYNTHETIC_LABEL,
)

load_dotenv()

DATA_DIR = Path(__file__).parent.parent / "data"
BRIEFINGS_DIR = DATA_DIR / "briefings"

# ── System prompt blocks ──

ROLE_AND_RULES = """You are a clinical pharmacy intelligence agent operating inside the Rx Shortage Intelligence product.
Your audience is hospital pharmacy directors and clinical pharmacists who depend on you to make
shortage-response decisions in minutes, not hours. They will not act on your output without seeing
the source — every recommendation you produce must be traceable to a specific FDA, openFDA, or
RxNorm record. You never act on the customer's behalf; you produce structured briefing items that
a human reviews and accepts, overrides, or escalates.

# Identity and audience

The buyer is the Director of Pharmacy at a 100-450 bed US health system. The daily user is a
clinical pharmacist on shift who opens the dashboard at the start of their day. They are
evidence-driven, conservative on patient safety, and have been burned by drug-information tools
that hallucinated even once. Trust is earned per claim, not per session.

# Mission

For each drug-shortage signal that affects THIS hospital's formulary or active orders, produce
exactly one BriefingItem JSON object. Each item classifies severity, recommends therapeutic
alternatives, cites every factual claim, and exposes the reasoning that led to the classification.
The pharmacist scans, decides, accepts. You never decide for them.

# Tools available

You will be given a set of tools spanning three MCP servers:
- fda_shortage_server: get_current_shortages(), get_shortage_detail(rxcui)
- drug_label_server: get_drug_label_sections(rxcui, sections), search_labels_by_indication(query)
- rxnorm_server: normalize_drug_name(name), get_therapeutic_alternatives(rxcui)

Tool names are namespaced by server in actual calls (e.g. fda_shortage_get_current_shortages).
You must use these tools rather than memory. Memory of drug facts from training is not citable
and not acceptable.

# Tool-use protocol

CALL BUDGET: You have a maximum of 6 tool calls per drug. Plan before calling.

Sequence (strict order, no deviations):
1. Call get_shortage_detail once for the candidate drug. Confirm status and reason.
2. Call get_drug_label_sections once for the candidate drug with ALL needed sections in one call:
   ["indications_and_usage", "warnings", "dosage_and_administration", "contraindications"].
3. Call get_therapeutic_alternatives once to retrieve alternatives list.
4. Call get_shortage_detail ONCE passing ALL alternative RxCUIs together (if the tool supports
   a list) OR call it once per top-2 alternatives only — not once per alternative separately.
   Skip shortage check for alternatives ranked 3+; note "shortage status unverified" in rationale.
5. Call get_drug_label_sections for the top-1 alternative only (one call, targeted sections).
6. Produce output. Do not make additional tool calls after step 5.

If a tool returns {"error": ...}, do not retry. Surface as confidence: low.
Never invent a tool call you were not given. Never fabricate a tool response.

# Data shape rules

- FDA shortage records return rxcui as a list (one generic = many products). Use the list to
  match against formulary; cite the specific RxCUI you reasoned about (the one matching the
  formulary entry's preferred form when possible, otherwise the first list element).
- FDA status field canonical values: "Current" (active shortage), "To Be Discontinued"
  (being phased out), "Resolved" (no longer in shortage). v0.1 focuses on Current; surface
  To Be Discontinued items if encountered with a confidence note.
- Approximately 10% of FDA records lack any RxCUI. If a candidate has no RxCUI, drop it
  from this briefing rather than guessing — record the drop in your reasoning.

# Output contract

Produce one BriefingItem per affected drug. Schema:

{
  "rxcui": "string — the specific RxCUI you reasoned about; required",
  "drug_name": "string — generic name from FDA record",
  "severity": "Critical | Watch | Resolved",
  "summary": "one sentence; what changed and why it matters to this hospital",
  "rationale": "2-4 sentences explaining the severity decision, citing rule(s) from rubric",
  "alternatives": [
    {
      "rxcui": "string",
      "name": "string",
      "rationale": "why this is clinically equivalent or acceptable substitute",
      "formulary_status": "preferred | non-preferred | not-on-formulary | unknown",
      "confidence": "high | medium | low"
    }
  ],
  "citations": [
    {"source": "fda_shortage | openfda_label | rxnorm | rxclass", "url": "string", "claim": "what this URL supports"}
  ],
  "confidence": "high | medium | low",
  "recommended_action": "one sentence — what should the pharmacist do?",
  "tool_call_log": [
    {"server": "...", "tool": "...", "args": {...}, "summary": "..."}
  ]
}

# Confidence discipline (PRD §13.1)

- high (≥85% rule-based + LLM agreement): one-click acceptable
- medium (60-85%): "review recommended" — pharmacist reads before accepting
- low (<60%): "manual review required" — no one-click

Rule-based ceilings (do not exceed even if LLM judgment is strong):
- Therapeutic alternative is an ATC class member only (no clinical equivalence proof) → max medium
- openFDA label data unavailable for the drug or alternative → max low
- RxCUI list ambiguity unresolved (couldn't pick which formulation) → max medium
- Diff bucket is "escalated" but yesterday status string didn't match canonical values → max medium
- Active orders count is unknown (data missing) → max medium

# Citation discipline (PRD Principle 5, FR-4)

Every factual claim about a drug, status, or alternative must have a citation entry. Acceptable
sources are limited to FDA Drug Shortage records, openFDA Drug Label sections, and RxNorm/RxClass
endpoints. The citation URL must be a real URL the pharmacist can click and verify. Do not cite
your own reasoning. Do not cite training data. If you cannot cite a claim, omit the claim.

# Hard prohibitions

- Do not invent RxCUIs. Every RxCUI in your output must have appeared in a tool response during
  this briefing run.
- Do not invent NDC codes, manufacturer names, drug names, or dates.
- Do not recommend an alternative that is itself currently in shortage (cross-check via FDA tool).
- Do not auto-accept on the user's behalf. The schema has no "accepted" field — that is set by the UI.
- Do not skip the alternatives section for Critical or Watch items unless no alternatives exist
  in RxClass; in that case, surface the absence as a finding with confidence low.

# Failure modes you must surface, not hide

- Missing label data → BriefingItem with confidence: low and rationale noting absence
- No therapeutic alternatives found → empty alternatives array, summary notes absence, confidence: low
- Tool error → recorded in tool_call_log with summary of error; do not retry
- Ambiguous severity (rules conflict) → choose the more conservative classification (Watch over Resolved, Critical over Watch) and explain the conflict in rationale

# Tone

Direct, clinical, terse. The pharmacist will read 5-15 BriefingItems back-to-back. Each one
should be scannable in under 10 seconds. No preamble, no qualifiers like "It appears that" or
"It is possible that". State the finding, cite the source."""

SEVERITY_RUBRIC = """This rubric is the deterministic backbone of severity classification. Apply it before letting
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

Final confidence = min(rule floor, all applicable ceilings)."""


def _system_blocks(formulary_subset: list[dict]) -> list[dict]:
    """Build cacheable system prompt blocks. Static blocks first, dynamic last."""
    return [
        {"type": "text", "text": ROLE_AND_RULES, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": SEVERITY_RUBRIC, "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": "FORMULARY SUBSET FOR THIS HOSPITAL:\n" + json.dumps(formulary_subset, indent=2),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                "PREFETCH MODE — OVERRIDE:\n"
                "All FDA, openFDA, and RxNorm data has been pre-fetched in parallel before this "
                "request and is included in the user message. Do NOT call any tools. "
                "Classify using only the pre-fetched data. Set tool_call_log to []."
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]


async def _prefetch_drug_data(
    bridge,
    candidates: list[dict],
    formulary_idx: dict,
) -> dict[str, dict]:
    """Parallel-fetch shortage detail + label + alternatives for all candidates,
    then parallel-fetch alt shortage status and top-1 alt label."""
    frxcuis = [d.get("_formulary_rxcui", "") for d in candidates if d.get("_formulary_rxcui")]

    async def _phase1_one(frxcui: str) -> tuple[str, str, str, str]:
        shortage, label, alts = await asyncio.gather(
            bridge.call_tool("fda_shortage_get_shortage_detail", {"rxcui": frxcui}),
            bridge.call_tool("drug_label_get_drug_label_sections", {
                "rxcui": frxcui,
                "sections": ["indications_and_usage", "warnings", "dosage_and_administration", "contraindications"],
            }),
            bridge.call_tool("rxnorm_get_therapeutic_alternatives", {"rxcui": frxcui}),
        )
        return frxcui, shortage, label, alts

    phase1 = await asyncio.gather(*[_phase1_one(r) for r in frxcuis])

    drug_data: dict[str, dict] = {}
    all_alt_rxcuis: set[str] = set()

    for frxcui, shortage_str, label_str, alts_str in phase1:
        try:
            alts_parsed = json.loads(alts_str)
        except Exception:
            alts_parsed = []
        if isinstance(alts_parsed, dict):
            alts_list = alts_parsed.get("alternatives", alts_parsed.get("drugs", []))
        elif isinstance(alts_parsed, list):
            alts_list = alts_parsed
        else:
            alts_list = []

        drug_data[frxcui] = {
            "shortage_detail": shortage_str,
            "label": label_str,
            "alternatives": alts_list,
            "alt_shortage": {},
            "alt_label_top1": None,
        }
        for alt in alts_list[:2]:
            rxcui = str(alt.get("rxcui", "") or "")
            if rxcui:
                all_alt_rxcuis.add(rxcui)

    # Phase 2a: shortage status for all unique alt RxCUIs
    alt_rxcui_list = list(all_alt_rxcuis)
    if alt_rxcui_list:
        alt_shortage_results = await asyncio.gather(
            *[bridge.call_tool("fda_shortage_get_shortage_detail", {"rxcui": r}) for r in alt_rxcui_list]
        )
        alt_shortage_map = dict(zip(alt_rxcui_list, alt_shortage_results))
    else:
        alt_shortage_map = {}

    # Phase 2b: label for top-1 alternative per drug
    top1_items: list[tuple[str, str]] = []
    for frxcui, data in drug_data.items():
        if data["alternatives"]:
            top1_rxcui = str(data["alternatives"][0].get("rxcui", "") or "")
            if top1_rxcui:
                top1_items.append((frxcui, top1_rxcui))

    if top1_items:
        top1_label_results = await asyncio.gather(
            *[bridge.call_tool("drug_label_get_drug_label_sections", {
                "rxcui": alt_rxcui,
                "sections": ["indications_and_usage", "warnings", "dosage_and_administration"],
                "drug_name": drug_data[frxcui]["alternatives"][0].get("name"),
            }) for frxcui, alt_rxcui in top1_items]
        )
        for (frxcui, _), label_str in zip(top1_items, top1_label_results):
            drug_data[frxcui]["alt_label_top1"] = label_str

    # Attach alt shortage map to each drug
    for frxcui, data in drug_data.items():
        data["alt_shortage"] = {
            str(alt.get("rxcui", "")): alt_shortage_map.get(str(alt.get("rxcui", "")), "{}")
            for alt in data["alternatives"][:2]
            if alt.get("rxcui")
        }

    return drug_data


# ── Data loading ──

def load_data() -> tuple[list, list, list]:
    """Returns (formulary_drugs, orders, yesterday_shortages)."""
    formulary = json.loads((DATA_DIR / "synthetic_formulary.json").read_text())["drugs"]
    orders_data = json.loads((DATA_DIR / "active_orders.json").read_text())["orders"]
    yesterday_path = DATA_DIR / "yesterday_snapshot.json"
    if yesterday_path.exists():
        yesterday = json.loads(yesterday_path.read_text()).get("shortages", [])
    else:
        yesterday = []
    return formulary, orders_data, yesterday


def index_formulary(drugs: list[dict]) -> dict[str, dict]:
    """Index formulary by every RxCUI in rxcui_list so any match hits."""
    idx = {}
    for drug in drugs:
        for rxcui in drug.get("rxcui_list", [drug.get("rxcui", "")]):
            if rxcui:
                idx[rxcui] = drug
    return idx


def index_orders(orders: list[dict]) -> dict[str, dict]:
    return {o["rxcui"]: o for o in orders if o.get("rxcui")}


# ── Diff logic ──


def compute_diff(today: list[dict], yesterday: list[dict], formulary_rxcuis: set) -> dict:
    """
    Compare today's shortage feed against yesterday's snapshot.
    Returns {new, escalated, improved, resolved, unchanged}.
    Each item gets _diff_bucket set.
    FDA rxcui field is a LIST — index by each element.
    """
    def _idx(records):
        idx = {}
        for r in records:
            for rxcui in r.get("rxcui", []):
                if rxcui and rxcui in formulary_rxcuis:
                    idx[rxcui] = r
        return idx

    today_idx = _idx(today)
    yest_idx = _idx(yesterday)

    today_keys = set(today_idx)
    yest_keys = set(yest_idx)

    result = {"new": [], "escalated": [], "improved": [], "resolved": [], "unchanged": []}

    for k in today_keys - yest_keys:
        item = dict(today_idx[k]); item["_diff_bucket"] = "new"; item["_formulary_rxcui"] = k
        result["new"].append(item)

    for k in yest_keys - today_keys:
        item = dict(yest_idx[k]); item["_diff_bucket"] = "resolved"; item["_formulary_rxcui"] = k
        result["resolved"].append(item)

    for k in today_keys & yest_keys:
        t, y = today_idx[k], yest_idx[k]
        tr, yr = status_rank(t.get("status", "")), status_rank(y.get("status", ""))
        item = dict(t); item["_formulary_rxcui"] = k
        if tr > yr:
            item["_diff_bucket"] = "escalated"; result["escalated"].append(item)
        elif tr < yr:
            item["_diff_bucket"] = "improved"; result["improved"].append(item)
        else:
            item["_diff_bucket"] = "unchanged"; result["unchanged"].append(item)

    return result


# ── User message builder ──

def build_user_message(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str
) -> str:
    orders_count = orders_entry.get("count_last_30_days", 0) if orders_entry else 0
    departments = orders_entry.get("departments", []) if orders_entry else []
    alts = formulary_entry.get("preferred_alternatives", [])
    return f"""Drug: {drug.get('generic_name') or formulary_entry.get('name')} (RxCUI {drug.get('_formulary_rxcui')})
Today's shortage status: {today_status}
Yesterday's status: {yesterday_status or 'not in snapshot'}
Active orders last 30 days: {orders_count}
Departments affected: {', '.join(departments) if departments else 'none recorded'}
Formulary status: {formulary_entry.get('formulary_status', 'unknown')}
Route of administration: {formulary_entry.get('route_of_administration', 'unknown')}
Preferred alternatives on formulary: {alts if alts else 'none'}
Diff bucket: {drug.get('_diff_bucket', 'unknown')}

Generate one BriefingItem JSON object for this drug. Use tools to fetch shortage detail, label sections, and therapeutic alternatives. Return ONLY valid JSON matching the BriefingItem schema — no prose before or after."""


def build_user_message_prefetch(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str,
    prefetched: dict,
) -> str:
    orders_count = orders_entry.get("count_last_30_days", 0) if orders_entry else 0
    departments = orders_entry.get("departments", []) if orders_entry else []
    alts = formulary_entry.get("preferred_alternatives", [])
    frxcui = drug.get("_formulary_rxcui", "")
    return f"""Drug: {drug.get('generic_name') or formulary_entry.get('name')} (RxCUI {frxcui})
Today's shortage status: {today_status}
Yesterday's status: {yesterday_status or 'not in snapshot'}
Active orders last 30 days: {orders_count}
Departments affected: {', '.join(departments) if departments else 'none recorded'}
Formulary status: {formulary_entry.get('formulary_status', 'unknown')}
Route of administration: {formulary_entry.get('route_of_administration', 'unknown')}
Preferred alternatives on formulary: {alts if alts else 'none'}
Diff bucket: {drug.get('_diff_bucket', 'unknown')}

PRE-FETCHED DATA — use this, do not call tools:

FDA shortage detail:
{prefetched.get('shortage_detail', '{}')}

openFDA label sections:
{prefetched.get('label', '{}')}

Therapeutic alternatives (RxNorm):
{json.dumps(prefetched.get('alternatives', []), indent=2)}

Alternative shortage status (top-2 checked):
{json.dumps(prefetched.get('alt_shortage', {}), indent=2)}

Top-1 alternative label sections:
{prefetched.get('alt_label_top1') or 'not fetched'}

Generate one BriefingItem JSON object. Cite URLs from the pre-fetched data above. Set tool_call_log to []. Return ONLY valid JSON — no prose before or after."""


# ── JSON extraction ──

def parse_briefing_item(text: str, drug_name: str, rxcui: str) -> dict:
    """Extract JSON from agent output via raw_decode (brace-balanced, prose-tolerant).

    Greedy regex `{[\\s\\S]*}` previously grabbed across embedded JSON in rationale
    fields. raw_decode walks from the first `{` and stops at the first complete
    JSON object; survives trailing prose. Falls through to minimal error item.
    """
    if not text:
        return _fallback_item(text, drug_name, rxcui)
    decoder = json.JSONDecoder()
    start = 0
    while True:
        idx = text.find("{", start)
        if idx < 0:
            break
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = idx + 1
    return _fallback_item(text, drug_name, rxcui)


def _fallback_item(text: str, drug_name: str, rxcui: str) -> dict:
    return {
        "rxcui": rxcui,
        "drug_name": drug_name,
        "severity": "Watch",
        "summary": "Agent output could not be parsed.",
        "rationale": text[:500] if text else "No output.",
        "alternatives": [],
        "citations": [],
        "confidence": "low",
        "recommended_action": "Manual review required.",
        "tool_call_log": [],
    }


# ── Main generate_briefing ──

async def _generate_briefing_async(date_str: str | None = None) -> dict:
    from src.mcp_bridge import MCPBridge
    from src.agent import run_agent

    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = str(uuid.uuid4())
    t_start = time.monotonic()

    def _log(msg: str) -> None:
        elapsed = time.monotonic() - t_start
        print(f"[briefing t={elapsed:5.1f}s] {msg}", flush=True)

    _log(f"phase=start run_id={run_id} date={date_str}")

    formulary, orders_list, yesterday = load_data()
    formulary_idx = index_formulary(formulary)
    orders_idx = index_orders(orders_list)
    formulary_rxcuis = set(formulary_idx.keys())
    _log(f"phase=load_data formulary={len(formulary)} orders={len(orders_list)} yesterday={len(yesterday)}")

    # Fetch today's shortages via MCP bridge
    async with MCPBridge() as bridge:
        _log("phase=mcp_bridge_ready")
        t_fda = time.monotonic()
        today_raw_str = await bridge.call_tool("fda_shortage_get_current_shortages", {"limit": FDA_FETCH_LIMIT})
        fetch_error = None
        try:
            today_raw = json.loads(today_raw_str)
            if isinstance(today_raw, dict) and "error" in today_raw:
                fetch_error = today_raw.get("error", "FDA shortage feed returned error envelope.")
                today_raw = []
        except Exception as e:
            fetch_error = f"FDA shortage feed JSON parse failed: {e}"
            today_raw = []

        if fetch_error:
            _log(f"WARNING fetch_error={fetch_error!r}")
        _log(f"phase=fda_fetch shortages={len(today_raw)} elapsed={time.monotonic()-t_fda:.1f}s")

        diff = compute_diff(today_raw, yesterday, formulary_rxcuis)
        _log(
            f"phase=diff new={len(diff['new'])} escalated={len(diff['escalated'])} "
            f"improved={len(diff['improved'])} resolved={len(diff['resolved'])} "
            f"unchanged={len(diff['unchanged'])}"
        )

        # Surface new + escalated + improved + resolved (skip unchanged).
        # Sort by clinical priority: escalated first (worsening), then new,
        # then improved, then resolved. Within each bucket sort by active
        # orders descending so highest-volume drugs surface first.
        BUCKET_RANK = {"escalated": 0, "new": 1, "improved": 2, "resolved": 3}

        def _candidate_sort_key(drug: dict) -> tuple:
            bucket = drug.get("_diff_bucket", "new")
            frxcui = drug.get("_formulary_rxcui", "")
            orders = orders_idx.get(frxcui, {}).get("count_last_30_days", 0)
            return (BUCKET_RANK.get(bucket, 9), -orders)

        candidates = sorted(
            diff["new"] + diff["escalated"] + diff["improved"] + diff["resolved"],
            key=_candidate_sort_key,
        )

        # Cut line: cap at DEFAULT_CANDIDATE_CAP drugs for v0.1 tier-1 latency budget.
        cap = DEFAULT_CANDIDATE_CAP
        if len(candidates) > cap:
            _log(f"phase=cap_applied total={len(candidates)} kept={cap}")
        candidates = candidates[:cap]
        _log(f"phase=candidates count={len(candidates)} names={[c.get('generic_name') for c in candidates]}")

        # Pre-fetch all data in parallel before the agent loop.
        # Eliminates per-drug tool-call roundtrips (was ~11 Anthropic calls/drug).
        # Each drug now costs 1 classification call (~39s) instead of ~11 calls (~90s).
        t_pre = time.monotonic()
        _log(f"phase=prefetch_start drugs={len(candidates)}")
        prefetch_map = await _prefetch_drug_data(bridge, candidates, formulary_idx)
        _log(
            f"phase=prefetch_done elapsed={time.monotonic()-t_pre:.1f}s "
            f"tool_calls={len(bridge.tool_calls)}"
        )
        system = _system_blocks(formulary)

        # Serial classification: 1 Anthropic call per drug, no tools.
        # sem=1 guards against concurrent cache-miss storms on the system prompt.
        sem = asyncio.Semaphore(1)

        async def _process_drug(drug: dict, drug_idx: int, total: int) -> tuple[dict, int]:
            async with sem:
                t_drug = time.monotonic()
                frxcui = drug.get("_formulary_rxcui", "")
                formulary_entry = formulary_idx.get(frxcui, {})
                orders_entry = orders_idx.get(frxcui)
                yesterday_item = next(
                    (r for r in yesterday if frxcui in r.get("rxcui", [])), None
                )
                yesterday_status = yesterday_item.get("status", "") if yesterday_item else ""
                prefetched = prefetch_map.get(frxcui, {})

                user_msg = build_user_message_prefetch(
                    drug, formulary_entry, orders_entry,
                    drug.get("status", ""), yesterday_status,
                    prefetched,
                )

                drug_name = drug.get("generic_name") or formulary_entry.get("name", "Unknown")
                _log(f"drug={drug_idx}/{total} name={drug_name!r} rxcui={frxcui} started")
                try:
                    final_text, tool_calls, tokens = await asyncio.wait_for(
                        run_agent(
                            system=system,
                            user_msg=user_msg,
                            tools=[],
                            call_tool_fn=bridge.call_tool,
                        ),
                        timeout=PER_DRUG_TIMEOUT_S,
                    )
                except asyncio.TimeoutError:
                    _log(f"drug={drug_idx}/{total} name={drug_name!r} TIMEOUT after {PER_DRUG_TIMEOUT_S}s")
                    return {
                        "rxcui": frxcui,
                        "drug_name": drug_name,
                        "severity": "Watch",
                        "summary": "Agent timed out (>90s). Manual review required.",
                        "rationale": "Agent exceeded per-drug timeout. No automated classification produced.",
                        "alternatives": [],
                        "citations": [],
                        "confidence": "low",
                        "recommended_action": "Manual review required — agent did not complete within time budget.",
                        "tool_call_log": [],
                        "item_id": str(uuid.uuid4()),
                        "_diff_bucket": drug.get("_diff_bucket", "unknown"),
                    }, 0

                item = parse_briefing_item(final_text, drug_name, frxcui)
                item["item_id"] = str(uuid.uuid4())
                item["_diff_bucket"] = drug.get("_diff_bucket", "unknown")
                # Attribute prefetch tool calls to this drug.
                # Match by rxcui in tool args (formulary rxcui or any alt rxcui from prefetch).
                drug_alt_rxcuis = {
                    str(a.get("rxcui", "") or "")
                    for a in (prefetched.get("alternatives") or [])[:2]
                }
                drug_alt_rxcuis.add(str(frxcui))
                item_tool_calls = [
                    tc for tc in bridge.tool_calls
                    if str((tc.get("args") or {}).get("rxcui") or "") in drug_alt_rxcuis
                ]
                # Append the agent's own tool_call_log too (will be empty in prefetch mode)
                item["tool_call_log"] = item_tool_calls + (tool_calls or [])
                _log(
                    f"drug={drug_idx}/{total} name={drug_name!r} done "
                    f"elapsed={time.monotonic()-t_drug:.1f}s tokens={tokens} "
                    f"severity={item.get('severity', '?')!r} confidence={item.get('confidence', '?')!r} "
                    f"alts={len(item.get('alternatives', []) or [])} "
                    f"cites={len(item.get('citations', []) or [])} "
                    f"tool_log={len(item.get('tool_call_log', []) or [])}"
                )
                return item, tokens

        # return_exceptions=True so one drug's failure doesn't cancel siblings
        total = len(candidates)
        gathered = await asyncio.gather(
            *(_process_drug(d, i + 1, total) for i, d in enumerate(candidates)),
            return_exceptions=True,
        )
        results = []
        for d, r in zip(candidates, gathered):
            if isinstance(r, Exception):
                frxcui = d.get("_formulary_rxcui", "")
                drug_name = d.get("generic_name") or formulary_idx.get(frxcui, {}).get("name", "Unknown")
                _log(f"drug name={drug_name!r} rxcui={frxcui} FAILED type={type(r).__name__} error={str(r)[:200]!r}")
                results.append((
                    {
                        "rxcui": frxcui,
                        "drug_name": drug_name,
                        "severity": "Watch",
                        "summary": f"Classification failed for {drug_name}. Manual review required.",
                        "rationale": f"Per-drug pipeline raised {type(r).__name__}: {str(r)[:300]}",
                        "alternatives": [],
                        "citations": [],
                        "confidence": "low",
                        "recommended_action": "Manual review required — automated pipeline failed.",
                        "tool_call_log": [],
                        "item_id": str(uuid.uuid4()),
                        "_diff_bucket": d.get("_diff_bucket", "unknown"),
                    },
                    0,
                ))
            else:
                results.append(r)
        items = [r[0] for r in results]
        total_tokens = sum(r[1] for r in results)
        all_tool_calls = list(bridge.tool_calls)

    latency_ms = int((time.monotonic() - t_start) * 1000)
    run = {
        "run_id": run_id,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_id": CUSTOMER_ID,
        "prompt_version": PROMPT_VERSION,
        "date": date_str,
        "items_reviewed": len(candidates),
        "items_surfaced": len(items),
        "items": items,
        "tool_calls": all_tool_calls,
        "total_tokens_used": total_tokens,
        "latency_ms": latency_ms,
        "label": SYNTHETIC_LABEL,
        "fetch_error": fetch_error,
    }

    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEFINGS_DIR / f"{date_str}.json"
    out_path.write_text(json.dumps(run, indent=2))
    _log(
        f"phase=write path={out_path.name} items={len(items)} "
        f"total_tokens={total_tokens} latency={latency_ms/1000:.1f}s"
    )
    print(f"Briefing written to {out_path} ({len(items)} items, {latency_ms}ms)", flush=True)
    return run


def generate_briefing(date_str: str | None = None) -> dict:
    """Sync wrapper — called from CLI and tests."""
    return asyncio.run(_generate_briefing_async(date_str))


if __name__ == "__main__":
    generate_briefing()
