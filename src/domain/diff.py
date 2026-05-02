"""Diff today's FDA shortage feed against yesterday's snapshot.

Returns five buckets: new, escalated, improved, resolved, unchanged.
FDA records' rxcui field is a list — index by each element.
"""

from src.domain.fda import status_rank


def compute_diff(today: list[dict], yesterday: list[dict], formulary_rxcuis: set) -> dict:
    """Compare today's shortage feed against yesterday's snapshot.

    Returns {new, escalated, improved, resolved, unchanged}.
    Each item gets _diff_bucket and _formulary_rxcui set.
    Only items whose rxcui list intersects formulary_rxcuis are surfaced.
    """
    def _idx(records: list[dict]) -> dict[str, dict]:
        idx: dict[str, dict] = {}
        for r in records:
            for rxcui in r.get("rxcui", []):
                if rxcui and rxcui in formulary_rxcuis:
                    idx[rxcui] = r
        return idx

    today_idx = _idx(today)
    yest_idx = _idx(yesterday)

    today_keys = set(today_idx)
    yest_keys = set(yest_idx)

    result: dict[str, list[dict]] = {
        "new": [], "escalated": [], "improved": [], "resolved": [], "unchanged": [],
    }

    for k in today_keys - yest_keys:
        item = dict(today_idx[k])
        item["_diff_bucket"] = "new"
        item["_formulary_rxcui"] = k
        result["new"].append(item)

    for k in yest_keys - today_keys:
        item = dict(yest_idx[k])
        item["_diff_bucket"] = "resolved"
        item["_formulary_rxcui"] = k
        result["resolved"].append(item)

    for k in today_keys & yest_keys:
        t, y = today_idx[k], yest_idx[k]
        tr, yr = status_rank(t.get("status", "")), status_rank(y.get("status", ""))
        item = dict(t)
        item["_formulary_rxcui"] = k
        if tr > yr:
            item["_diff_bucket"] = "escalated"
            result["escalated"].append(item)
        elif tr < yr:
            item["_diff_bucket"] = "improved"
            result["improved"].append(item)
        else:
            item["_diff_bucket"] = "unchanged"
            result["unchanged"].append(item)

    return result
