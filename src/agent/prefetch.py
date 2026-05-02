"""
Parallel pre-fetch of all FDA/openFDA/RxNorm data for shortage candidates.

Extracted from src/briefing.py _prefetch_drug_data (commit d49c45e8).
That commit achieved a 4.7× latency improvement (550s → 116s) by replacing
per-drug serial tool-call loops with two async gather phases before the
Anthropic classification pass.

Phase 1 (parallel per drug):
  shortage detail + label sections + therapeutic alternatives

Phase 2a (parallel across all alts):
  shortage status for every unique alternative RxCUI

Phase 2b (parallel across drugs):
  label sections for top-1 alternative per drug

Public API: prefetch_drug_data(bridge, candidates, formulary_idx) → dict[frxcui, data]
"""

import asyncio
import json


async def prefetch_drug_data(
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
