from src.domain.fda import FDAStatus, status_rank


def test_fda_status_canonical_values():
    assert FDAStatus.CURRENT == "Current"
    assert FDAStatus.TBD == "To Be Discontinued"
    assert FDAStatus.RESOLVED == "Resolved"


def test_status_rank_for_diff_escalation():
    assert status_rank("Resolved") == 0
    assert status_rank("Available with limitations") == 1
    assert status_rank("Current") == 2
    assert status_rank("To Be Discontinued") == 3
    assert status_rank("Discontinued") == 3


def test_status_rank_unknown_defaults_to_one():
    assert status_rank("garbage") == 1
    assert status_rank("") == 1
