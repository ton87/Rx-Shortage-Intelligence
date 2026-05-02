"""FDA shortage feed status canonical values + diff-escalation rank.

Verified 2026-05-01 against live API: only "Current", "To Be Discontinued",
and "Resolved" appear. "Currently in Shortage" is hallucinated and breaks
the search query (404). Do not introduce new statuses without API check.
"""

from enum import StrEnum


class FDAStatus(StrEnum):
    CURRENT = "Current"
    TBD = "To Be Discontinued"
    RESOLVED = "Resolved"


# Diff escalation rank. FDAStatus members cover the canonical 3 statuses verified
# 2026-05-01. The two extra keys handle (a) historical "Discontinued" snapshots
# from before the API switched to "To Be Discontinued", and (b) "Available with
# limitations" appearing in some legacy yesterday_snapshot.json fixtures. New
# code should use FDAStatus values; status_rank tolerates the legacy strings.
_STATUS_RANK: dict[str, int] = {
    FDAStatus.RESOLVED: 0,
    "Available with limitations": 1,
    FDAStatus.CURRENT: 2,
    FDAStatus.TBD: 3,
    "Discontinued": 3,
}


def status_rank(status: str) -> int:
    """Rank for diff escalation comparison. Unknown → 1 (neutral middle)."""
    return _STATUS_RANK.get(status, 1)
