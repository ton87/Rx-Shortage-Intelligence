from src.domain.confidence import Confidence, CONFIDENCE_LABELS


def test_confidence_string_values_match_json_schema():
    assert Confidence.HIGH == "high"
    assert Confidence.MEDIUM == "medium"
    assert Confidence.LOW == "low"


def test_confidence_labels_for_pill_display():
    assert CONFIDENCE_LABELS[Confidence.HIGH] == "HIGH"
    assert CONFIDENCE_LABELS[Confidence.MEDIUM] == "MED"
    assert CONFIDENCE_LABELS[Confidence.LOW] == "LOW"
