"""Severity classification — single source of truth for the three levels."""

from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "Critical"
    WATCH = "Watch"
    RESOLVED = "Resolved"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.WATCH: 1,
    Severity.RESOLVED: 2,
}
