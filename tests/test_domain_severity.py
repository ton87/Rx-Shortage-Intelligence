from src.domain.severity import Severity, SEVERITY_RANK


def test_severity_string_values_match_json_schema():
    assert Severity.CRITICAL == "Critical"
    assert Severity.WATCH == "Watch"
    assert Severity.RESOLVED == "Resolved"


def test_severity_rank_orders_critical_first():
    items = [Severity.RESOLVED, Severity.CRITICAL, Severity.WATCH]
    items.sort(key=lambda s: SEVERITY_RANK[s])
    assert items == [Severity.CRITICAL, Severity.WATCH, Severity.RESOLVED]


def test_severity_str_round_trip_via_json():
    import json
    payload = json.dumps({"severity": Severity.CRITICAL})
    assert json.loads(payload)["severity"] == "Critical"
