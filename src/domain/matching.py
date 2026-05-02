"""Match formulary entries to briefing shortage items.

Keyed by RxCUI primary, exact-normalized-name fallback. No substring matching —
multi-formulation drugs were over-matching via first-token substring before
this strict gate.
"""

from src.domain.severity import Severity, SEVERITY_RANK


def normalize_drug_name(name: str | None) -> str:
    """Lowercase + strip + collapse whitespace + drop punctuation noise.

    Conservative — only strips formulation tokens, not active-ingredient
    distinguishers. So 'Cefotaxime Sodium Powder, for Solution' matches
    'Cefotaxime Sodium for Injection' siblings.
    """
    if not name:
        return ""
    n = name.lower().strip()
    for token in [",", ";"]:
        n = n.replace(token, " ")
    while "  " in n:
        n = n.replace("  ", " ")
    return n.strip()


def build_shortage_index(items: list[dict]) -> tuple[dict, dict]:
    """Build (rxcui_idx, name_idx) from briefing items for fast formulary lookup.

    rxcui_idx: rxcui (str) → match dict — primary join key.
    name_idx:  normalized name (str) → list[match] — exact-name fallback only.
    """
    rxcui_idx: dict = {}
    name_idx: dict = {}
    for item in items:
        match = {
            "severity":   item.get("severity", Severity.WATCH),
            "summary":    item.get("summary", ""),
            "citation":   primary_citation_url(item),
            "item_id":    item.get("item_id", ""),
        }
        rxcui = str(item.get("rxcui", ""))
        if rxcui:
            rxcui_idx[rxcui] = match
        norm = normalize_drug_name(item.get("drug_name") or "")
        if norm:
            name_idx.setdefault(norm, []).append(match)
    return rxcui_idx, name_idx


def find_shortage_match(drug: dict, rxcui_idx: dict, name_idx: dict) -> dict | None:
    """Match formulary drug to a briefing shortage by RxCUI then exact name.

    Returns None if no exact match — UI shows '—' honestly rather than guessing.
    """
    rxcui_list = drug.get("rxcui_list") or [drug.get("rxcui")]
    for r in rxcui_list:
        if r and str(r) in rxcui_idx:
            return rxcui_idx[str(r)]
    norm = normalize_drug_name(drug.get("name") or "")
    matches = name_idx.get(norm) or []
    if matches:
        return min(matches, key=lambda m: SEVERITY_RANK.get(m.get("severity", Severity.WATCH), 1))
    return None


def primary_citation_url(item: dict) -> str | None:
    """Return the first citation URL from an item's citations list."""
    for c in item.get("citations", []) or []:
        url = c.get("url") or c.get("source_url")
        if url:
            return url
    return None
