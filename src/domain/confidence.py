"""Confidence levels — used for pill display + rule-based ceilings."""

from enum import StrEnum


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


CONFIDENCE_LABELS: dict[Confidence, str] = {
    Confidence.HIGH: "HIGH",
    Confidence.MEDIUM: "MED",
    Confidence.LOW: "LOW",
}
