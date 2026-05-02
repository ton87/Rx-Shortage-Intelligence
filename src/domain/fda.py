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


_STATUS_RANK: dict[str, int] = {
    "Resolved": 0,
    "Available with limitations": 1,
    "Current": 2,
    "To Be Discontinued": 3,
    "Discontinued": 3,
}


def status_rank(status: str) -> int:
    """Rank for diff escalation comparison. Unknown → 1 (neutral middle)."""
    return _STATUS_RANK.get(status, 1)
