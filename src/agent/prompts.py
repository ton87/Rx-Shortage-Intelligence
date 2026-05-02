"""
Agent prompt loader, system block builders, user message builders, and output parser.

Prompt strings live in src/agent/prompts/*.md — byte-stable files extracted verbatim
from the original Python literals in src/briefing.py (Task 4.2). SHA-256 hashes are
captured in docs/superpowers/plans/baseline-2026-05-01.md (R2 mitigation).

load_prompt() is @cache-ed so each markdown file is read from disk exactly once per
process, keeping the same in-memory string as the prompt cache warms against.
"""

import json
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def load_prompt(name: str) -> str:
    """Read prompt markdown file by name (no extension). Cached per process."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


def build_system_blocks(formulary_subset: list[dict]) -> list[dict]:
    """Build cacheable system prompt blocks. Static blocks first, dynamic last.

    Returns 4 blocks matching the original _system_blocks() in briefing.py:
    1. ROLE_AND_RULES   — clinical agent identity, tools, output contract
    2. SEVERITY_RUBRIC  — deterministic severity classification rules
    3. Formulary subset — hospital-specific formulary JSON
    4. PREFETCH MODE override — instructs agent not to call tools
    """
    return [
        {
            "type": "text",
            "text": load_prompt("role_and_rules"),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": load_prompt("severity_rubric"),
            "cache_control": {"type": "ephemeral"},
        },
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


def _format_drug_context(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str,
) -> str:
    """Common header lines for both tool-mode and prefetch-mode user messages."""
    orders_count = orders_entry.get("count_last_30_days", 0) if orders_entry else 0
    departments = orders_entry.get("departments", []) if orders_entry else []
    alts = formulary_entry.get("preferred_alternatives", [])
    return f"""Drug: {drug.get('generic_name') or formulary_entry.get('name')} (RxCUI {drug.get('_formulary_rxcui', '')})
Today's shortage status: {today_status}
Yesterday's status: {yesterday_status or 'not in snapshot'}
Active orders last 30 days: {orders_count}
Departments affected: {', '.join(departments) if departments else 'none recorded'}
Formulary status: {formulary_entry.get('formulary_status', 'unknown')}
Route of administration: {formulary_entry.get('route_of_administration', 'unknown')}
Preferred alternatives on formulary: {alts if alts else 'none'}
Diff bucket: {drug.get('_diff_bucket', 'unknown')}"""


def build_user_message(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str,
) -> str:
    """Build user message for tool-calling mode (non-prefetch)."""
    return _format_drug_context(drug, formulary_entry, orders_entry, today_status, yesterday_status) + (
        "\n\nGenerate one BriefingItem JSON object for this drug. Use tools to fetch shortage detail, "
        "label sections, and therapeutic alternatives. Return ONLY valid JSON matching the BriefingItem "
        "schema — no prose before or after."
    )


def build_user_message_prefetch(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str,
    prefetched: dict,
) -> str:
    """Build user message for prefetch mode — all data inline, no tool calls."""
    header = _format_drug_context(drug, formulary_entry, orders_entry, today_status, yesterday_status)
    return f"""{header}

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
    from src.domain.severity import Severity
    from src.domain.confidence import Confidence
    return {
        "rxcui": rxcui,
        "drug_name": drug_name,
        "severity": Severity.WATCH,
        "summary": "Agent output could not be parsed.",
        "rationale": text[:500] if text else "No output.",
        "alternatives": [],
        "citations": [],
        "confidence": Confidence.LOW,
        "recommended_action": "Manual review required.",
        "tool_call_log": [],
    }
