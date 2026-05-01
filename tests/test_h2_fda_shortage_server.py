"""
Contract tests for T-001: src/servers/fda_shortage_server.py

Each test maps to a specific acceptance criterion (AC) from T-001.
All tests are expected to be RED until the implementation is written.

AC coverage:
  AC-1  Module importable; defines `mcp` or `app` FastMCP instance
  AC-2  get_current_shortages() exists and returns list[dict] with required keys
  AC-3  get_shortage_detail() exists and returns correct shapes (hit and miss)
  AC-4  All HTTP calls go through cached_get (verified via mock)
  AC-5  Both tools wrapped in try/except — httpx error → {"error": "..."}
  AC-6  rxcui field is always a list (never str, never None)
  AC-7  source_url present on every record from both tools
  AC-8  status:Current filter sent to cached_get in get_current_shortages
"""

from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Minimal raw FDA shortage record (openFDA API shape)
_RAW_RECORD = {
    "generic_name": "Cisplatin Injection",
    "status": "Current",
    "shortage_reason": "Demand increase",
    "openfda": {
        "rxcui": ["309311", "1049502"],
    },
}

# A record with no openfda.rxcui (edge case — ~10% of real FDA records)
_RAW_RECORD_NO_RXCUI = {
    "generic_name": "Some Drug",
    "status": "Current",
    "shortage_reason": "Other",
    "openfda": {},
}

# A record with no openfda key at all
_RAW_RECORD_NO_OPENFDA = {
    "generic_name": "Another Drug",
    "status": "Current",
    "shortage_reason": "Other",
}

# FDA API response envelope
def _fda_response(records):
    return {"results": records}


# ---------------------------------------------------------------------------
# AC-1: Module importable; `mcp` or `app` FastMCP instance defined
# ---------------------------------------------------------------------------

def test_module_is_importable():
    """AC-1: fda_shortage_server module must be importable without errors."""
    import importlib
    mod = importlib.import_module("src.servers.fda_shortage_server")
    assert mod is not None


def test_mcp_or_app_instance_exists():
    """AC-1: Module must expose an `mcp` or `app` attribute that is a FastMCP instance."""
    from mcp.server.fastmcp import FastMCP
    import src.servers.fda_shortage_server as mod

    instance = getattr(mod, "mcp", None) or getattr(mod, "app", None)
    assert instance is not None, "Neither `mcp` nor `app` attribute found on module"
    assert isinstance(instance, FastMCP), (
        f"Expected FastMCP instance, got {type(instance)}"
    )


def test_fastmcp_server_named_fda_shortage():
    """AC-1: FastMCP server must be named 'fda-shortage'."""
    from mcp.server.fastmcp import FastMCP
    import src.servers.fda_shortage_server as mod

    instance = getattr(mod, "mcp", None) or getattr(mod, "app", None)
    assert instance is not None
    # FastMCP exposes the name via .name attribute
    assert instance.name == "fda-shortage", (
        f"Expected server name 'fda-shortage', got {instance.name!r}"
    )


# ---------------------------------------------------------------------------
# AC-2: get_current_shortages() — signature, return type, required keys
# ---------------------------------------------------------------------------

def test_get_current_shortages_exists():
    """AC-2: get_current_shortages must be defined in the module."""
    import src.servers.fda_shortage_server as mod
    assert hasattr(mod, "get_current_shortages"), (
        "get_current_shortages not found on module"
    )
    assert callable(mod.get_current_shortages)


def test_get_current_shortages_returns_list():
    """AC-2: get_current_shortages() returns a list."""
    from src.servers.fda_shortage_server import get_current_shortages

    mock_result = [_RAW_RECORD]
    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response(mock_result),
    ):
        result = get_current_shortages(limit=1)

    assert isinstance(result, list)


def test_get_current_shortages_returns_list_of_dicts():
    """AC-2: Every item returned by get_current_shortages() is a dict."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ):
        result = get_current_shortages(limit=1)

    assert len(result) >= 1
    for item in result:
        assert isinstance(item, dict), f"Expected dict, got {type(item)}"


def test_get_current_shortages_has_required_keys():
    """AC-2: Each record must contain generic_name, status, rxcui, shortage_reason, source_url."""
    from src.servers.fda_shortage_server import get_current_shortages

    required_keys = {"generic_name", "status", "rxcui", "shortage_reason", "source_url"}

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ):
        result = get_current_shortages(limit=1)

    assert len(result) >= 1
    for item in result:
        missing = required_keys - item.keys()
        assert not missing, f"Record missing keys: {missing}"


def test_get_current_shortages_default_limit():
    """AC-2: get_current_shortages has default limit=20 (callable with no args)."""
    from src.servers.fda_shortage_server import get_current_shortages
    import inspect

    sig = inspect.signature(get_current_shortages)
    params = sig.parameters
    assert "limit" in params, "limit parameter not found"
    assert params["limit"].default == 20, (
        f"Expected default limit=20, got {params['limit'].default}"
    )


# ---------------------------------------------------------------------------
# AC-3: get_shortage_detail() — signature, hit shape, miss shape
# ---------------------------------------------------------------------------

def test_get_shortage_detail_exists():
    """AC-3: get_shortage_detail must be defined in the module."""
    import src.servers.fda_shortage_server as mod
    assert hasattr(mod, "get_shortage_detail"), (
        "get_shortage_detail not found on module"
    )
    assert callable(mod.get_shortage_detail)


def test_get_shortage_detail_hit_returns_dict_with_required_keys():
    """AC-3: On a hit, returns dict with at least generic_name, rxcui, source_url."""
    from src.servers.fda_shortage_server import get_shortage_detail

    required_keys = {"generic_name", "rxcui", "source_url"}

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ):
        result = get_shortage_detail(rxcui="309311")

    assert isinstance(result, dict)
    missing = required_keys - result.keys()
    assert not missing, f"Hit record missing keys: {missing}"
    assert "error" not in result, "Unexpected error key on a successful hit"


def test_get_shortage_detail_miss_returns_error_dict():
    """AC-3: On a miss (empty results), returns dict with 'error' key."""
    from src.servers.fda_shortage_server import get_shortage_detail

    # 404-equivalent: FDA returns empty results list
    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value={"results": []},
    ):
        result = get_shortage_detail(rxcui="NONEXISTENT")

    assert isinstance(result, dict)
    assert "error" in result, "Miss must return {'error': '...'}"
    assert result["error"], "error value must be non-empty"


def test_get_shortage_detail_404_response_returns_error_dict():
    """AC-3: When cached_get returns None (404-cached), returns {'error': '...'}."""
    from src.servers.fda_shortage_server import get_shortage_detail

    # Simulate a 404 that was cached as None
    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=None,
    ):
        result = get_shortage_detail(rxcui="NOTFOUND")

    assert isinstance(result, dict)
    assert "error" in result


# ---------------------------------------------------------------------------
# AC-4: All HTTP calls go through cached_get
# ---------------------------------------------------------------------------

def test_get_current_shortages_calls_cached_get():
    """AC-4: get_current_shortages() must call cached_get at least once."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ) as mock_cached_get:
        get_current_shortages(limit=5)

    mock_cached_get.assert_called()


def test_get_shortage_detail_calls_cached_get():
    """AC-4: get_shortage_detail() must call cached_get at least once."""
    from src.servers.fda_shortage_server import get_shortage_detail

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ) as mock_cached_get:
        get_shortage_detail(rxcui="309311")

    mock_cached_get.assert_called()


def test_no_direct_httpx_calls_in_get_current_shortages():
    """AC-4: get_current_shortages() must not bypass cached_get and call httpx directly."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch("src.servers.fda_shortage_server.cached_get",
               return_value=_fda_response([_RAW_RECORD])), \
         patch("httpx.get") as mock_httpx:
        get_current_shortages(limit=1)

    mock_httpx.assert_not_called()


def test_no_direct_httpx_calls_in_get_shortage_detail():
    """AC-4: get_shortage_detail() must not bypass cached_get and call httpx directly."""
    from src.servers.fda_shortage_server import get_shortage_detail

    with patch("src.servers.fda_shortage_server.cached_get",
               return_value=_fda_response([_RAW_RECORD])), \
         patch("httpx.get") as mock_httpx:
        get_shortage_detail(rxcui="309311")

    mock_httpx.assert_not_called()


# ---------------------------------------------------------------------------
# AC-5: Both tools wrapped in try/except — exceptions → {"error": "..."}
# ---------------------------------------------------------------------------

def test_get_current_shortages_returns_error_dict_on_exception():
    """AC-5: get_current_shortages() must catch exceptions and return [{'error': '...'}] (list shape preserved)."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        side_effect=Exception("network failure"),
    ):
        result = get_current_shortages(limit=5)

    assert isinstance(result, list), (
        f"Expected list with error dict, got {type(result)}: {result!r}"
    )
    assert len(result) == 1, f"Expected single-element list, got: {result!r}"
    assert "error" in result[0], f"Expected 'error' key in first element, got: {result}"


def test_get_current_shortages_does_not_raise_on_exception():
    """AC-5: get_current_shortages() must never propagate exceptions to the caller."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        side_effect=RuntimeError("unexpected crash"),
    ):
        try:
            get_current_shortages()
        except Exception as exc:
            pytest.fail(f"get_current_shortages raised instead of returning error dict: {exc!r}")


def test_get_shortage_detail_returns_error_dict_on_exception():
    """AC-5: get_shortage_detail() must catch exceptions and return {'error': '...'}."""
    from src.servers.fda_shortage_server import get_shortage_detail

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        side_effect=Exception("timeout"),
    ):
        result = get_shortage_detail(rxcui="309311")

    assert isinstance(result, dict), (
        f"Expected dict with error, got {type(result)}: {result!r}"
    )
    assert "error" in result, f"Expected 'error' key, got: {result}"


def test_get_shortage_detail_does_not_raise_on_exception():
    """AC-5: get_shortage_detail() must never propagate exceptions to the caller."""
    from src.servers.fda_shortage_server import get_shortage_detail

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        side_effect=ConnectionError("refused"),
    ):
        try:
            get_shortage_detail(rxcui="309311")
        except Exception as exc:
            pytest.fail(f"get_shortage_detail raised instead of returning error dict: {exc!r}")


# ---------------------------------------------------------------------------
# AC-6: rxcui field is always a list (never str, never None)
# ---------------------------------------------------------------------------

def test_get_current_shortages_rxcui_is_list_multi():
    """AC-6: rxcui is a list when the record has multiple RxCUIs."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ):
        result = get_current_shortages(limit=1)

    for item in result:
        assert isinstance(item["rxcui"], list), (
            f"rxcui must be list, got {type(item['rxcui'])}: {item['rxcui']!r}"
        )


def test_get_current_shortages_rxcui_is_list_when_no_openfda():
    """AC-6: rxcui defaults to empty list when openfda key is absent."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD_NO_OPENFDA]),
    ):
        result = get_current_shortages(limit=1)

    for item in result:
        assert isinstance(item["rxcui"], list), (
            f"rxcui must be list even when openfda missing, got {type(item['rxcui'])}"
        )
        # Must not be None
        assert item["rxcui"] is not None


def test_get_current_shortages_rxcui_never_none():
    """AC-6: rxcui is never None, even for records with empty openfda.rxcui."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD_NO_RXCUI]),
    ):
        result = get_current_shortages(limit=1)

    for item in result:
        assert item["rxcui"] is not None, "rxcui must never be None"
        assert isinstance(item["rxcui"], list)


def test_get_shortage_detail_rxcui_is_list_on_hit():
    """AC-6: rxcui in get_shortage_detail hit result is always a list."""
    from src.servers.fda_shortage_server import get_shortage_detail

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ):
        result = get_shortage_detail(rxcui="309311")

    if "error" not in result:
        assert isinstance(result["rxcui"], list), (
            f"rxcui must be list on hit, got {type(result['rxcui'])}"
        )
        assert result["rxcui"] is not None


# ---------------------------------------------------------------------------
# AC-7: source_url present on every record from both tools
# ---------------------------------------------------------------------------

def test_get_current_shortages_source_url_present_on_all_records():
    """AC-7: Every record returned by get_current_shortages has a non-empty source_url."""
    from src.servers.fda_shortage_server import get_current_shortages

    records = [_RAW_RECORD, _RAW_RECORD_NO_RXCUI, _RAW_RECORD_NO_OPENFDA]
    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response(records),
    ):
        result = get_current_shortages(limit=10)

    assert len(result) >= 1
    for item in result:
        assert "source_url" in item, f"source_url missing from record: {item}"
        assert item["source_url"], f"source_url is empty/falsy: {item}"


def test_get_shortage_detail_source_url_present_on_hit():
    """AC-7: get_shortage_detail hit result contains a non-empty source_url."""
    from src.servers.fda_shortage_server import get_shortage_detail

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ):
        result = get_shortage_detail(rxcui="309311")

    if "error" not in result:
        assert "source_url" in result, f"source_url missing from hit result: {result}"
        assert result["source_url"], f"source_url is empty/falsy on hit: {result}"


def test_get_current_shortages_source_url_is_string():
    """AC-7: source_url must be a string (a citable URL, not a dict or list)."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ):
        result = get_current_shortages(limit=1)

    for item in result:
        assert isinstance(item["source_url"], str), (
            f"source_url must be str, got {type(item['source_url'])}"
        )


# ---------------------------------------------------------------------------
# AC-8: status:Current filter included in the search param passed to cached_get
# ---------------------------------------------------------------------------

def test_get_current_shortages_passes_status_current_filter():
    """AC-8: cached_get must be called with args containing 'status:Current'."""
    from src.servers.fda_shortage_server import get_current_shortages

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        return_value=_fda_response([_RAW_RECORD]),
    ) as mock_cached_get:
        get_current_shortages(limit=5)

    # Inspect all calls: args and kwargs combined
    assert mock_cached_get.called, "cached_get was never called"

    found_status_current = False
    for call_args in mock_cached_get.call_args_list:
        # cached_get signature: (key, fetch_fn, ttl)
        # The filter may appear in the cache key string or in the fetch_fn closure.
        # We verify it appears somewhere in the call arguments as a string.
        all_arg_strings = " ".join(str(a) for a in call_args.args)
        all_kwarg_strings = " ".join(str(v) for v in call_args.kwargs.values())
        combined = all_arg_strings + " " + all_kwarg_strings
        if "status:Current" in combined:
            found_status_current = True
            break

    assert found_status_current, (
        "No call to cached_get contained 'status:Current'. "
        f"Actual calls: {mock_cached_get.call_args_list}"
    )


def test_get_current_shortages_status_current_in_cache_key():
    """AC-8: The cache key passed to cached_get includes 'status:Current' or 'Current'."""
    from src.servers.fda_shortage_server import get_current_shortages

    captured_keys = []

    def capture_cached_get(key, fetch_fn, ttl):
        captured_keys.append(key)
        return _fda_response([_RAW_RECORD])

    with patch(
        "src.servers.fda_shortage_server.cached_get",
        side_effect=capture_cached_get,
    ):
        get_current_shortages(limit=5)

    assert captured_keys, "cached_get was never called — no cache key to inspect"
    # At least one call must mention Current in its cache key
    any_current = any("Current" in str(k) for k in captured_keys)
    assert any_current, (
        f"No cache key contained 'Current'. Keys seen: {captured_keys}"
    )
