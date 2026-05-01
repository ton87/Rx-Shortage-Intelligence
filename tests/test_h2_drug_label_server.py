"""
Contract tests for T-002: src/servers/drug_label_server.py

Each test maps to a specific acceptance criterion (AC) from T-002.
All tests are expected to be RED until the implementation is written.

AC coverage:
  AC-1  FastMCP("drug-label") server starts without error; name is "drug-label"
  AC-2  get_drug_label_sections() exists, correct signature, returns dict, includes source_url
  AC-3  RxCUI fallback: 404/empty triggers second cached_get call with generic_name
  AC-4  search_labels_by_indication() exists, returns list, items have source_url
  AC-5  Only 7 KEEP_SECTIONS returned; explicit sections= filter respected
  AC-6  All HTTP calls go through cached_get (verified via mock)
  AC-7  Both tools wrapped in try/except — exception → {"error": "..."} no raise
  AC-8  source_url present and query-specific on every returned record
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_CISPLATIN_LABEL = {
    "openfda": {
        "rxcui": ["309311"],
        "generic_name": ["cisplatin"],
    },
    "indications_and_usage": ["Cisplatin is indicated for..."],
    "dosage_and_administration": ["Administer by IV..."],
    "contraindications": ["Pre-existing renal impairment..."],
    "warnings": ["Cumulative renal toxicity..."],
    "clinical_pharmacology": ["Cisplatin is an inorganic heavy metal..."],
}


def _label_response(results):
    return {"results": results, "meta": {"results": {"total": len(results)}}}


# ---------------------------------------------------------------------------
# Imports under test (will fail until implementation exists)
# ---------------------------------------------------------------------------

from src.servers.drug_label_server import (  # noqa: E402
    get_drug_label_sections,
    search_labels_by_indication,
    KEEP_SECTIONS,
    mcp,
)

# ---------------------------------------------------------------------------
# AC-1: FastMCP instance
# ---------------------------------------------------------------------------


def test_mcp_instance_is_fastmcp_named_drug_label():
    """Server mcp instance must be a FastMCP named 'drug-label'."""
    from mcp.server.fastmcp import FastMCP

    assert isinstance(mcp, FastMCP), "mcp must be a FastMCP instance"
    assert mcp.name == "drug-label", f"Expected name 'drug-label', got {mcp.name!r}"


# ---------------------------------------------------------------------------
# AC-2: get_drug_label_sections tool
# ---------------------------------------------------------------------------


def test_get_drug_label_sections_signature():
    """Function must exist with params: rxcui (str) and sections (list|None)."""
    sig = inspect.signature(get_drug_label_sections)
    params = sig.parameters
    assert "rxcui" in params, "Missing 'rxcui' parameter"
    assert "sections" in params, "Missing 'sections' parameter"
    assert params["sections"].default is None or params["sections"].default == inspect.Parameter.empty or params["sections"].default is None, \
        "sections must default to None"


def test_get_drug_label_sections_returns_dict():
    """Returns a dict on a successful hit."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = get_drug_label_sections(rxcui="309311")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"


def test_get_drug_label_sections_includes_source_url():
    """Result dict must include a 'source_url' key."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = get_drug_label_sections(rxcui="309311")
    assert "source_url" in result, "Result must include 'source_url'"


# ---------------------------------------------------------------------------
# AC-3: RxCUI fallback
# ---------------------------------------------------------------------------


def test_get_drug_label_sections_falls_back_on_404():
    """When first cached_get returns None (RxCUI 404), a second call is made via generic_name."""
    # First call (rxcui lookup) returns None; second call (generic_name) returns real data
    name_response = _label_response([_CISPLATIN_LABEL])
    call_count = []

    def mock_cached_get(key, fetch_fn, ttl):
        call_count.append(key)
        if len(call_count) == 1:
            return None  # simulate 404 / no result for rxcui lookup
        return name_response

    with patch("src.servers.drug_label_server.cached_get", side_effect=mock_cached_get):
        result = get_drug_label_sections(rxcui="2555")

    assert len(call_count) >= 2, (
        "Expected at least 2 cached_get calls (rxcui lookup + fallback), "
        f"got {len(call_count)}"
    )
    assert "error" not in result, f"Should have recovered via fallback, got error: {result}"


def test_get_drug_label_sections_falls_back_on_empty_results():
    """When first cached_get returns results=[], fallback is triggered."""
    empty_response = _label_response([])
    name_response = _label_response([_CISPLATIN_LABEL])
    call_count = []

    def mock_cached_get(key, fetch_fn, ttl):
        call_count.append(key)
        if len(call_count) == 1:
            return empty_response
        return name_response

    with patch("src.servers.drug_label_server.cached_get", side_effect=mock_cached_get):
        result = get_drug_label_sections(rxcui="2555")

    assert len(call_count) >= 2, (
        f"Expected fallback call when results=[], got {len(call_count)} calls"
    )
    assert "error" not in result, f"Should have recovered via fallback, got error: {result}"


# ---------------------------------------------------------------------------
# AC-4: search_labels_by_indication
# ---------------------------------------------------------------------------


def test_search_labels_by_indication_signature():
    """Function must exist with a 'query' (str) parameter."""
    sig = inspect.signature(search_labels_by_indication)
    params = sig.parameters
    assert "query" in params, "Missing 'query' parameter"


def test_search_labels_by_indication_returns_list():
    """Returns a list on success."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = search_labels_by_indication(query="solid tumor")
    assert isinstance(result, list), f"Expected list, got {type(result)}"


def test_search_labels_by_indication_items_have_source_url():
    """Each item in the returned list must have a 'source_url' key."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = search_labels_by_indication(query="solid tumor")
    assert len(result) > 0, "Expected at least one result item"
    for item in result:
        assert "source_url" in item, f"Item missing 'source_url': {item}"


# ---------------------------------------------------------------------------
# AC-5: Only KEEP_SECTIONS returned
# ---------------------------------------------------------------------------

_ALL_KEEP_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings",
    "boxed_warning",
    "drug_interactions",
    "clinical_pharmacology",
]


def test_keep_sections_constant_has_exactly_7_entries():
    """KEEP_SECTIONS must contain exactly the 7 required section names."""
    assert set(KEEP_SECTIONS) == set(_ALL_KEEP_SECTIONS), (
        f"KEEP_SECTIONS mismatch.\nExpected: {sorted(_ALL_KEEP_SECTIONS)}\nGot: {sorted(KEEP_SECTIONS)}"
    )
    assert len(KEEP_SECTIONS) == 7, f"Expected 7 sections, got {len(KEEP_SECTIONS)}"


def test_get_drug_label_sections_only_returns_keep_sections():
    """No keys outside KEEP_SECTIONS (plus source_url) appear in result."""
    # Add an extra field that should be stripped
    label_with_extra = dict(_CISPLATIN_LABEL)
    label_with_extra["adverse_reactions"] = ["Severe nausea..."]  # NOT in KEEP_SECTIONS
    mock_response = _label_response([label_with_extra])

    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = get_drug_label_sections(rxcui="309311")

    allowed_keys = set(KEEP_SECTIONS) | {"source_url"}
    result_section_keys = {k for k in result if k != "source_url"}
    disallowed = result_section_keys - set(KEEP_SECTIONS)
    assert not disallowed, f"Result contains section keys not in KEEP_SECTIONS: {disallowed}"


def test_get_drug_label_sections_with_explicit_sections_filters():
    """Passing sections=['warnings'] returns only the 'warnings' key (plus source_url)."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = get_drug_label_sections(rxcui="309311", sections=["warnings"])

    result_section_keys = {k for k in result if k != "source_url"}
    assert result_section_keys == {"warnings"}, (
        f"Expected only {{'warnings'}}, got {result_section_keys}"
    )


# ---------------------------------------------------------------------------
# AC-6: All HTTP calls through cached_get with TTL_OPENFDA_LABEL
# ---------------------------------------------------------------------------


def test_get_drug_label_sections_uses_cached_get():
    """cached_get must be called when get_drug_label_sections is invoked."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response) as mock_cg:
        get_drug_label_sections(rxcui="309311")
    assert mock_cg.called, "cached_get was never called"


def test_get_drug_label_sections_uses_ttl_openfda_label():
    """cached_get must be called with TTL_OPENFDA_LABEL."""
    from src.cache import TTL_OPENFDA_LABEL

    mock_response = _label_response([_CISPLATIN_LABEL])
    calls_with_ttl = []

    def capturing_cached_get(key, fetch_fn, ttl):
        calls_with_ttl.append(ttl)
        return mock_response

    with patch("src.servers.drug_label_server.cached_get", side_effect=capturing_cached_get):
        get_drug_label_sections(rxcui="309311")

    assert any(ttl == TTL_OPENFDA_LABEL for ttl in calls_with_ttl), (
        f"cached_get not called with TTL_OPENFDA_LABEL ({TTL_OPENFDA_LABEL}). Got TTLs: {calls_with_ttl}"
    )


def test_search_labels_by_indication_uses_cached_get():
    """cached_get must be called when search_labels_by_indication is invoked."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response) as mock_cg:
        search_labels_by_indication(query="tumor")
    assert mock_cg.called, "cached_get was never called"


def test_search_labels_by_indication_uses_ttl_openfda_label():
    """search_labels_by_indication must pass TTL_OPENFDA_LABEL to cached_get."""
    from src.cache import TTL_OPENFDA_LABEL

    mock_response = _label_response([_CISPLATIN_LABEL])
    calls_with_ttl = []

    def capturing_cached_get(key, fetch_fn, ttl):
        calls_with_ttl.append(ttl)
        return mock_response

    with patch("src.servers.drug_label_server.cached_get", side_effect=capturing_cached_get):
        search_labels_by_indication(query="tumor")

    assert any(ttl == TTL_OPENFDA_LABEL for ttl in calls_with_ttl), (
        f"TTL_OPENFDA_LABEL not used. Got: {calls_with_ttl}"
    )


# ---------------------------------------------------------------------------
# AC-7: try/except — no raise on exception, error dict returned
# ---------------------------------------------------------------------------


def test_get_drug_label_sections_does_not_raise_on_exception():
    """Exception inside the tool must NOT propagate to the caller."""
    with patch("src.servers.drug_label_server.cached_get", side_effect=RuntimeError("boom")):
        try:
            get_drug_label_sections(rxcui="309311")
        except Exception as exc:
            pytest.fail(f"get_drug_label_sections raised an exception: {exc}")


def test_get_drug_label_sections_returns_error_dict_on_exception():
    """Exception must result in {'error': '...'} dict, not a raise."""
    with patch("src.servers.drug_label_server.cached_get", side_effect=RuntimeError("boom")):
        result = get_drug_label_sections(rxcui="309311")
    assert isinstance(result, dict), f"Expected dict on error, got {type(result)}"
    assert "error" in result, f"Expected 'error' key in result, got: {result}"
    assert isinstance(result["error"], str), "error value must be a string"
    assert len(result["error"]) > 0, "error message must not be empty"


def test_search_labels_by_indication_does_not_raise_on_exception():
    """Exception inside the tool must NOT propagate to the caller."""
    with patch("src.servers.drug_label_server.cached_get", side_effect=RuntimeError("boom")):
        try:
            search_labels_by_indication(query="tumor")
        except Exception as exc:
            pytest.fail(f"search_labels_by_indication raised an exception: {exc}")


def test_search_labels_by_indication_returns_error_on_exception():
    """Exception must result in error response (list with error dict or error dict)."""
    with patch("src.servers.drug_label_server.cached_get", side_effect=RuntimeError("boom")):
        result = search_labels_by_indication(query="tumor")
    # Accept either [{"error": "..."}] or {"error": "..."}
    if isinstance(result, list):
        assert len(result) > 0, "Error response list must not be empty"
        assert "error" in result[0], f"First item must have 'error' key, got: {result[0]}"
    elif isinstance(result, dict):
        assert "error" in result, f"Expected 'error' key in result dict, got: {result}"
    else:
        pytest.fail(f"Expected list or dict on error, got {type(result)}: {result}")


# ---------------------------------------------------------------------------
# AC-8: source_url is query-specific
# ---------------------------------------------------------------------------


def test_source_url_contains_rxcui_for_direct_hit():
    """source_url must contain the rxcui that was successfully used for lookup."""
    mock_response = _label_response([_CISPLATIN_LABEL])
    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = get_drug_label_sections(rxcui="309311")
    assert "source_url" in result, "source_url missing from result"
    source_url = result["source_url"]
    assert "309311" in source_url, (
        f"source_url should contain the rxcui '309311', got: {source_url!r}"
    )


def test_source_url_contains_fallback_term_when_rxcui_misses():
    """When fallback is used, source_url must reflect the fallback query (generic_name)."""
    empty_response = _label_response([])
    name_response = _label_response([_CISPLATIN_LABEL])
    call_count = []

    def mock_cached_get(key, fetch_fn, ttl):
        call_count.append(key)
        if len(call_count) == 1:
            return empty_response
        return name_response

    with patch("src.servers.drug_label_server.cached_get", side_effect=mock_cached_get):
        result = get_drug_label_sections(rxcui="2555")

    assert "source_url" in result, "source_url missing from fallback result"
    source_url = result["source_url"]
    # The fallback URL must not just be the failed rxcui=2555 query
    # It should contain "generic_name" or "cisplatin" to reflect the fallback search
    assert "cisplatin" in source_url.lower() or "generic_name" in source_url.lower(), (
        f"source_url should reflect fallback generic_name query, got: {source_url!r}"
    )


def test_source_url_present_in_indication_search():
    """Every item returned by search_labels_by_indication must have source_url."""
    # Provide two results to be thorough
    label2 = dict(_CISPLATIN_LABEL)
    label2["openfda"] = {"rxcui": ["1234"], "generic_name": ["carboplatin"]}
    mock_response = _label_response([_CISPLATIN_LABEL, label2])

    with patch("src.servers.drug_label_server.cached_get", return_value=mock_response):
        result = search_labels_by_indication(query="platinum")

    assert isinstance(result, list) and len(result) > 0, "Expected non-empty list"
    for i, item in enumerate(result):
        assert "source_url" in item, f"Item[{i}] missing source_url: {item}"
        assert item["source_url"], f"Item[{i}] source_url must not be empty"
