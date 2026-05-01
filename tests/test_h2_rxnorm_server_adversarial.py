"""
Adversarial tests for T-003: src/servers/rxnorm_server.py — pass 2

Three categories:
  POSITIVE  — happy-path with realistic / boundary inputs
  NEGATIVE  — inputs that should produce graceful handled failures
  AMBIENT   — partial / degraded system state, malformed data
"""

from unittest.mock import patch

import pytest

from src.servers.rxnorm_server import (
    normalize_drug_name,
    get_therapeutic_alternatives,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_members(n: int, self_rxcui: str | None = None, start_rxcui: int = 5000):
    """Build a drugMemberGroup response with n members, optionally inserting self."""
    members = []
    if self_rxcui is not None:
        members.append({"minConcept": {"rxcui": self_rxcui, "name": "Self Drug"}})
    for i in range(n):
        members.append({
            "minConcept": {
                "rxcui": str(start_rxcui + i),
                "name": f"Alt Drug {i}",
            }
        })
    return {"drugMemberGroup": {"drugMember": members}}


_RXCLASS_BY_RXCUI_L01XA = {
    "rxclassDrugInfoList": {
        "rxclassDrugInfo": [
            {
                "rxclassMinConceptItem": {
                    "classId": "L01XA",
                    "className": "Platinum compounds",
                }
            }
        ]
    }
}

_RXNORM_HIT = {
    "idGroup": {"rxnormId": ["1049502"]}
}

_RXNORM_MISS = {
    "idGroup": {}
}


# ===========================================================================
# POSITIVE TESTS
# ===========================================================================

def test_drug_with_multiple_atc_classes_uses_first_only():
    """POSITIVE: When ATC class lookup returns multiple classes, only the first is used."""
    multi_class_response = {
        "rxclassDrugInfoList": {
            "rxclassDrugInfo": [
                {
                    "rxclassMinConceptItem": {
                        "classId": "L01XA",
                        "className": "Platinum compounds",
                    }
                },
                {
                    "rxclassMinConceptItem": {
                        "classId": "L01XX",
                        "className": "Other antineoplastic agents",
                    }
                },
            ]
        }
    }
    members_for_l01xa = _make_members(3, start_rxcui=1000)
    captured_keys = []

    def capturing_cached_get(key, fetch_fn, ttl):
        captured_keys.append(key)
        if "byRxcui" in key:
            return multi_class_response
        return members_for_l01xa

    with patch("src.servers.rxnorm_server.cached_get", side_effect=capturing_cached_get):
        result = get_therapeutic_alternatives("309311")

    # Should only call members for first class (L01XA), not L01XX
    member_keys = [k for k in captured_keys if "members" in k]
    assert len(member_keys) == 1, f"Expected exactly 1 member lookup, got: {member_keys}"
    assert "L01XA" in member_keys[0], (
        f"Expected members key to reference first class 'L01XA', got: {member_keys[0]}"
    )


def test_name_with_spaces_and_mixed_case_normalized_in_cache_key():
    """POSITIVE: Cache key uses lowercased/stripped name to prevent duplicate cache entries."""
    captured_keys = []

    def capturing_cached_get(key, fetch_fn, ttl):
        captured_keys.append(key)
        return _RXNORM_HIT

    with patch("src.servers.rxnorm_server.cached_get", side_effect=capturing_cached_get):
        normalize_drug_name("  Metformin HCl  ")

    assert len(captured_keys) >= 1
    key = captured_keys[0]
    # Key must be lowercased and stripped
    assert key == key.lower(), f"Cache key must be lowercased, got: {key!r}"
    assert not key.startswith(" ") and not key.endswith(" "), (
        f"Cache key must be stripped of leading/trailing spaces: {key!r}"
    )
    assert "metformin hcl" in key, (
        f"Expected normalized name in key, got: {key!r}"
    )


def test_cap_at_10_enforced_when_more_than_10_members():
    """POSITIVE: With 15 ATC class members, exactly 10 results returned."""
    members_15 = _make_members(15)
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, members_15],
    ):
        result = get_therapeutic_alternatives("309311")
    assert len(result) == 10, f"Expected exactly 10 results (capped), got {len(result)}"


def test_normalize_returns_first_rxcui_when_multiple_returned():
    """POSITIVE: When multiple RxCUIs are returned, only the first is used."""
    multi_rxcui_response = {
        "idGroup": {"rxnormId": ["1049502", "309311", "7654"]}
    }
    with patch("src.servers.rxnorm_server.cached_get", return_value=multi_rxcui_response):
        result = normalize_drug_name("cisplatin")
    assert result["rxcui"] == "1049502", (
        f"Expected first RxCUI '1049502', got: {result['rxcui']!r}"
    )


# ===========================================================================
# NEGATIVE TESTS
# ===========================================================================

def test_normalize_with_empty_string_returns_error_dict():
    """NEGATIVE: normalize_drug_name('') returns error dict, no crash."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=_RXNORM_MISS):
        result = normalize_drug_name("")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "error" in result, f"Expected error on empty string, got: {result}"


def test_get_alternatives_where_class_lookup_returns_404_none():
    """NEGATIVE: When class lookup returns None (cached 404), returns empty list."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=None):
        result = get_therapeutic_alternatives("309311")
    assert result == [], f"Expected [] when class lookup returns None, got: {result}"


def test_get_alternatives_where_members_returns_empty_list():
    """NEGATIVE: When classMembers has empty drugMember list, returns []."""
    empty_members = {"drugMemberGroup": {"drugMember": []}}
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, empty_members],
    ):
        result = get_therapeutic_alternatives("309311")
    assert result == [], f"Expected [] when no members, got: {result}"


def test_cached_get_raises_in_normalize_returns_error_dict():
    """NEGATIVE: If cached_get raises in normalize, returns {'error': '...'}, no propagation."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=RuntimeError("disk cache corrupt"),
    ):
        result = normalize_drug_name("cisplatin")
    assert isinstance(result, dict)
    assert "error" in result
    assert "disk cache corrupt" in result["error"]


def test_cached_get_raises_in_alternatives_returns_error_list():
    """NEGATIVE: If cached_get raises in alternatives, returns [{'error': '...'}], no propagation."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=ConnectionError("network unreachable"),
    ):
        result = get_therapeutic_alternatives("309311")
    assert isinstance(result, list)
    assert len(result) == 1
    assert "error" in result[0]


# ===========================================================================
# AMBIENT / DEGRADED TESTS
# ===========================================================================

def test_member_with_missing_min_concept_skipped_gracefully():
    """AMBIENT: Members with no 'minConcept' key are skipped, no crash."""
    members_with_bad_entry = {
        "drugMemberGroup": {
            "drugMember": [
                {},  # no minConcept at all
                {"minConcept": {"rxcui": "5001", "name": "Good Drug"}},
                {"minConcept": {}},  # minConcept present but empty
            ]
        }
    }
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, members_with_bad_entry],
    ):
        result = get_therapeutic_alternatives("309311")
    # Should not raise; should return whatever valid entries exist
    assert isinstance(result, list)
    # The good drug entry should appear
    valid_entries = [r for r in result if r.get("rxcui") == "5001"]
    assert len(valid_entries) == 1


def test_rxclass_returns_no_drug_infos_returns_empty_list():
    """AMBIENT: When rxclassDrugInfo is None/absent in the response, returns []."""
    no_infos_response = {
        "rxclassDrugInfoList": {}
    }
    with patch("src.servers.rxnorm_server.cached_get", return_value=no_infos_response):
        result = get_therapeutic_alternatives("309311")
    assert result == [], f"Expected [] when no drug infos, got: {result}"


def test_large_member_list_returns_exactly_10():
    """AMBIENT: 20 members → exactly 10 returned."""
    members_20 = _make_members(20)
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, members_20],
    ):
        result = get_therapeutic_alternatives("309311")
    assert len(result) == 10, f"Expected exactly 10 results, got {len(result)}"


def test_members_data_malformed_no_drug_member_group_key():
    """AMBIENT: If members response has no 'drugMemberGroup' key, returns []."""
    malformed_response = {"someOtherKey": {}}
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, malformed_response],
    ):
        result = get_therapeutic_alternatives("309311")
    assert result == [], f"Expected [] on malformed members response, got: {result}"


def test_normalize_with_unicode_drug_name_no_crash():
    """AMBIENT: Unicode drug name (e.g. accented chars) should not raise."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=_RXNORM_MISS):
        try:
            result = normalize_drug_name("ibuprofène")
        except Exception as exc:
            pytest.fail(f"normalize_drug_name raised on unicode input: {exc!r}")
    assert isinstance(result, dict)


def test_self_rxcui_in_member_list_filtered_out():
    """AMBIENT: Self rxcui appearing in members list is excluded from results."""
    self_rxcui = "309311"
    members_with_self = _make_members(5, self_rxcui=self_rxcui, start_rxcui=9000)
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, members_with_self],
    ):
        result = get_therapeutic_alternatives(self_rxcui)

    returned_rxcuis = [r["rxcui"] for r in result]
    assert self_rxcui not in returned_rxcuis, (
        f"Self rxcui {self_rxcui!r} must be excluded, but got: {returned_rxcuis}"
    )


def test_get_alternatives_second_cached_get_returns_none():
    """AMBIENT: If members lookup returns None (cached 404), returns []."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, None],
    ):
        result = get_therapeutic_alternatives("309311")
    assert result == [], f"Expected [] when members returns None, got: {result}"


def test_normalize_source_url_contains_drug_name():
    """AMBIENT: source_url in normalize result reflects the queried drug name."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=_RXNORM_HIT):
        result = normalize_drug_name("metformin")
    assert "metformin" in result["source_url"], (
        f"source_url should contain 'metformin', got: {result['source_url']!r}"
    )


def test_get_alternatives_with_exactly_10_members_returns_10():
    """AMBIENT: With exactly 10 ATC class members (none self), returns all 10."""
    members_10 = _make_members(10)
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI_L01XA, members_10],
    ):
        result = get_therapeutic_alternatives("309311")
    assert len(result) == 10, f"Expected exactly 10 results, got {len(result)}"
