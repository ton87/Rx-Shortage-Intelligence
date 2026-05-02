"""Index formulary + orders by RxCUI for O(1) match lookup during briefing."""


def index_formulary(drugs: list[dict]) -> dict[str, dict]:
    """Index formulary by every RxCUI in rxcui_list so any FDA-side match hits.

    Multi-formulation drugs (e.g. methylphenidate ER → 14 RxCUIs) appear
    under each of their RxCUIs in the resulting index.
    """
    idx: dict[str, dict] = {}
    for drug in drugs:
        for rxcui in drug.get("rxcui_list", [drug.get("rxcui", "")]):
            if rxcui:
                idx[rxcui] = drug
    return idx


def index_orders(orders: list[dict]) -> dict[str, dict]:
    """Index active orders by RxCUI. Records without rxcui are dropped."""
    return {o["rxcui"]: o for o in orders if o.get("rxcui")}
