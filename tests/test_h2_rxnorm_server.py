"""
Contract tests for T-003: src/servers/rxnorm_server.py

Each test maps to a specific acceptance criterion (AC) from T-003.
All tests are expected to be RED until the implementation is written.

AC coverage:
  AC-1  FastMCP("rxnorm") server starts without error; name is "rxnorm"
  AC-2  normalize_drug_name() returns dict with rxcui/name/source_url, or {"error": "..."} on miss
  AC-3  get_therapeutic_alternatives() returns ATC class members: same-route, excludes self, caps at 10
  AC-4  All HTTP calls through cached_get with TTL_RXNORM
  AC-5  RxClass used for alternatives (ATC, not getRelatedByType)
  AC-6  Each alternative carries rxcui, name, confidence="class-member"
  AC-7  Both tools wrapped in try/except; return {"error": "..."} / [] on failure
"""

import inspect
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Minimal RxNorm normalize API response
_RXNORM_HIT = {
    "idGroup": {
        "rxnormId": ["1049502", "309311"],
    }
}

_RXNORM_MISS = {
    "idGroup": {}
}

# RxClass byRxcui response
_RXCLASS_BY_RXCUI = {
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

# RxClass classMembers response (>10 items to test cap)
def _make_members(n: int, start_rxcui: int = 2000):
    members = []
    for i in range(n):
        members.append({
            "minConcept": {
                "rxcui": str(start_rxcui + i),
                "name": f"Drug {i}",
            }
        })
    return {
        "drugMemberGroup": {
            "drugMember": members
        }
    }

_RXCLASS_MEMBERS_5 = _make_members(5)
_RXCLASS_MEMBERS_12 = _make_members(12)


# ---------------------------------------------------------------------------
# Imports under test (will fail RED until implementation exists)
# ---------------------------------------------------------------------------

from src.servers.rxnorm_server import (  # noqa: E402
    normalize_drug_name,
    get_therapeutic_alternatives,
    mcp,
)


# ---------------------------------------------------------------------------
# AC-1: FastMCP("rxnorm") instance
# ---------------------------------------------------------------------------

def test_mcp_instance_named_rxnorm():
    """AC-1: mcp must be a FastMCP instance named 'rxnorm'."""
    from mcp.server.fastmcp import FastMCP
    assert isinstance(mcp, FastMCP), f"Expected FastMCP instance, got {type(mcp)}"
    assert mcp.name == "rxnorm", f"Expected name 'rxnorm', got {mcp.name!r}"


# ---------------------------------------------------------------------------
# AC-2: normalize_drug_name — return shape, hit and miss
# ---------------------------------------------------------------------------

def test_normalize_returns_dict_with_rxcui_name_source_url():
    """AC-2: Successful normalize returns dict with rxcui, name, source_url."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=_RXNORM_HIT):
        result = normalize_drug_name("cisplatin")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "rxcui" in result, f"Missing 'rxcui' key: {result}"
    assert "name" in result, f"Missing 'name' key: {result}"
    assert "source_url" in result, f"Missing 'source_url' key: {result}"
    assert "error" not in result, f"Unexpected error on hit: {result}"


def test_normalize_returns_error_when_no_rxcui_found():
    """AC-2: When no rxnormId is found, returns {'error': '...'}."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=_RXNORM_MISS):
        result = normalize_drug_name("unknowndrug999")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "error" in result, f"Expected 'error' key on miss: {result}"
    assert result["error"], "error value must be non-empty"


def test_normalize_includes_source_url():
    """AC-2: source_url is present in successful response."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=_RXNORM_HIT):
        result = normalize_drug_name("cisplatin")
    assert "source_url" in result, f"source_url missing from result: {result}"
    assert isinstance(result["source_url"], str), "source_url must be a string"
    assert result["source_url"], "source_url must be non-empty"


def test_normalize_uses_cached_get():
    """AC-2/AC-4: cached_get is called at least once by normalize_drug_name."""
    with patch("src.servers.rxnorm_server.cached_get", return_value=_RXNORM_HIT) as mock_cg:
        normalize_drug_name("cisplatin")
    mock_cg.assert_called()


# ---------------------------------------------------------------------------
# AC-3: get_therapeutic_alternatives — list of dicts, excludes self, caps at 10
# ---------------------------------------------------------------------------

def test_get_alternatives_returns_list_of_dicts():
    """AC-3: get_therapeutic_alternatives returns a list of dicts."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI, _RXCLASS_MEMBERS_5],
    ):
        result = get_therapeutic_alternatives("309311")
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    for item in result:
        assert isinstance(item, dict), f"Each item must be dict, got {type(item)}"


def test_get_alternatives_each_item_has_rxcui_name_confidence():
    """AC-3/AC-6: Each item has rxcui, name, confidence keys."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI, _RXCLASS_MEMBERS_5],
    ):
        result = get_therapeutic_alternatives("309311")
    assert len(result) > 0, "Expected at least one result"
    for item in result:
        assert "rxcui" in item, f"Missing 'rxcui': {item}"
        assert "name" in item, f"Missing 'name': {item}"
        assert "confidence" in item, f"Missing 'confidence': {item}"


def test_get_alternatives_excludes_self():
    """AC-3: The queried rxcui must not appear in the returned alternatives."""
    # Add self (rxcui=309311) as one of the members
    members_with_self = {
        "drugMemberGroup": {
            "drugMember": [
                {"minConcept": {"rxcui": "309311", "name": "Cisplatin"}},
                {"minConcept": {"rxcui": "2555", "name": "Carboplatin"}},
                {"minConcept": {"rxcui": "3001", "name": "Oxaliplatin"}},
            ]
        }
    }
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI, members_with_self],
    ):
        result = get_therapeutic_alternatives("309311")
    returned_rxcuis = [item["rxcui"] for item in result]
    assert "309311" not in returned_rxcuis, (
        f"Self rxcui '309311' must be excluded, but got: {returned_rxcuis}"
    )


def test_get_alternatives_caps_at_10():
    """AC-3: Returns at most 10 alternatives even when more than 10 members exist."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI, _RXCLASS_MEMBERS_12],
    ):
        result = get_therapeutic_alternatives("309311")
    assert len(result) <= 10, f"Expected at most 10 results, got {len(result)}"


# ---------------------------------------------------------------------------
# AC-4: cached_get + TTL_RXNORM
# ---------------------------------------------------------------------------

def test_normalize_uses_ttl_rxnorm():
    """AC-4: normalize_drug_name calls cached_get with TTL_RXNORM."""
    from src.cache import TTL_RXNORM

    captured_ttls = []

    def capturing_cached_get(key, fetch_fn, ttl):
        captured_ttls.append(ttl)
        return _RXNORM_HIT

    with patch("src.servers.rxnorm_server.cached_get", side_effect=capturing_cached_get):
        normalize_drug_name("cisplatin")

    assert any(ttl == TTL_RXNORM for ttl in captured_ttls), (
        f"Expected TTL_RXNORM ({TTL_RXNORM}) in calls, got: {captured_ttls}"
    )


def test_get_alternatives_uses_cached_get():
    """AC-4: get_therapeutic_alternatives calls cached_get."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI, _RXCLASS_MEMBERS_5],
    ) as mock_cg:
        get_therapeutic_alternatives("309311")
    assert mock_cg.called, "cached_get was never called"
    assert mock_cg.call_count >= 2, (
        f"Expected at least 2 cached_get calls (class + members), got {mock_cg.call_count}"
    )


# ---------------------------------------------------------------------------
# AC-5: RxClass ATC used for alternatives
# ---------------------------------------------------------------------------

def test_get_alternatives_calls_rxclass_api():
    """AC-5: get_therapeutic_alternatives uses RxClass (classId + ATC) not getRelatedByType."""
    captured_keys = []

    def capturing_cached_get(key, fetch_fn, ttl):
        captured_keys.append(key)
        if len(captured_keys) == 1:
            return _RXCLASS_BY_RXCUI
        return _RXCLASS_MEMBERS_5

    with patch("src.servers.rxnorm_server.cached_get", side_effect=capturing_cached_get):
        get_therapeutic_alternatives("309311")

    # Both calls must reference rxclass in the key
    assert len(captured_keys) >= 2, f"Expected 2+ cached_get calls, got {len(captured_keys)}"
    assert any("rxclass" in k.lower() for k in captured_keys), (
        f"Expected at least one key referencing 'rxclass', got: {captured_keys}"
    )


# ---------------------------------------------------------------------------
# AC-6: confidence = "class-member"
# ---------------------------------------------------------------------------

def test_get_alternatives_confidence_is_class_member():
    """AC-6: Every alternative item has confidence='class-member'."""
    with patch(
        "src.servers.rxnorm_server.cached_get",
        side_effect=[_RXCLASS_BY_RXCUI, _RXCLASS_MEMBERS_5],
    ):
        result = get_therapeutic_alternatives("309311")
    assert len(result) > 0, "Expected at least one result"
    for item in result:
        assert item.get("confidence") == "class-member", (
            f"Expected confidence='class-member', got: {item.get('confidence')!r}"
        )


# ---------------------------------------------------------------------------
# AC-7: try/except — no raise on exception, error dict/list returned
# ---------------------------------------------------------------------------

def test_normalize_does_not_raise_on_exception():
    """AC-7: normalize_drug_name must never propagate exceptions to the caller."""
    with patch("src.servers.rxnorm_server.cached_get", side_effect=RuntimeError("network down")):
        try:
            normalize_drug_name("cisplatin")
        except Exception as exc:
            pytest.fail(f"normalize_drug_name raised instead of returning error dict: {exc!r}")


def test_normalize_returns_error_dict_on_exception():
    """AC-7: normalize_drug_name returns {'error': '...'} when exception occurs."""
    with patch("src.servers.rxnorm_server.cached_get", side_effect=ConnectionError("timeout")):
        result = normalize_drug_name("cisplatin")
    assert isinstance(result, dict), f"Expected dict on error, got {type(result)}"
    assert "error" in result, f"Expected 'error' key, got: {result}"
    assert isinstance(result["error"], str), "error must be a string"
    assert len(result["error"]) > 0, "error message must not be empty"


def test_get_alternatives_does_not_raise_on_exception():
    """AC-7: get_therapeutic_alternatives must never propagate exceptions."""
    with patch("src.servers.rxnorm_server.cached_get", side_effect=RuntimeError("boom")):
        try:
            get_therapeutic_alternatives("309311")
        except Exception as exc:
            pytest.fail(f"get_therapeutic_alternatives raised instead of returning error: {exc!r}")


def test_get_alternatives_returns_error_list_on_exception():
    """AC-7: get_therapeutic_alternatives returns [{'error': '...'}] when exception occurs."""
    with patch("src.servers.rxnorm_server.cached_get", side_effect=ConnectionError("refused")):
        result = get_therapeutic_alternatives("309311")
    assert isinstance(result, list), f"Expected list on error, got {type(result)}"
    assert len(result) > 0, "Error response list must not be empty"
    assert "error" in result[0], f"First item must have 'error' key, got: {result[0]}"


def test_get_alternatives_returns_empty_list_when_no_atc_class():
    """AC-7: Returns [] when ATC class lookup returns no drug infos (graceful, not error)."""
    no_class_response = {
        "rxclassDrugInfoList": {
            "rxclassDrugInfo": []
        }
    }
    with patch("src.servers.rxnorm_server.cached_get", return_value=no_class_response):
        result = get_therapeutic_alternatives("309311")
    assert result == [], f"Expected empty list when no ATC class, got: {result}"
