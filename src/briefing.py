"""
Briefing generation + diff logic.

CLI: python -m src.briefing
  → Generates today's briefing, writes data/briefings/YYYY-MM-DD.json

generate_briefing(date_str=None) → BriefingRun dict
compute_diff(today, yesterday, formulary_rxcuis) → DiffResult dict
"""

import asyncio
import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.domain.diff import compute_diff
from src.domain.indexing import index_formulary, index_orders
from src.domain.constants import (
    DEFAULT_CANDIDATE_CAP,
    FDA_FETCH_LIMIT,
    PER_DRUG_TIMEOUT_S,
    CUSTOMER_ID,
    PROMPT_VERSION,
    SYNTHETIC_LABEL,
)
from src.io_.briefing_store import write_briefing
from src.io_.data_loader import load_briefing_inputs
from src.agent.prompts import (
    build_system_blocks,
    build_user_message,
    build_user_message_prefetch,
    parse_briefing_item,
)

load_dotenv()

DATA_DIR = Path(__file__).parent.parent / "data"


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


# ── Main generate_briefing ──

async def _generate_briefing_async(date_str: str | None = None) -> dict:
    from src.mcp_bridge import MCPBridge
    from src.agent.loop import run_agent

    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = str(uuid.uuid4())
    t_start = time.monotonic()

    def _log(msg: str) -> None:
        elapsed = time.monotonic() - t_start
        print(f"[briefing t={elapsed:5.1f}s] {msg}", flush=True)

    _log(f"phase=start run_id={run_id} date={date_str}")

    formulary, orders_list, yesterday = load_briefing_inputs()
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
        system = build_system_blocks(formulary)

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

    out_path = write_briefing(run, date_str)
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
