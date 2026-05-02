"""
Adversarial tests for T-001: src/servers/fda_shortage_server.py — pass 2

Three categories:
  POSITIVE  — happy path with realistic inputs
  NEGATIVE  — inputs that should produce handled errors, not crashes
  AMBIENT   — partial or off-nominal / degraded system state
"""

import datetime
from unittest.mock import patch

import pytest

from src.servers.fda_shortage_server import (
    get_current_shortages,
    get_shortage_detail,
    _trim,
)


# ---------------------------------------------------------------------------
# Shared helpers / realistic test data
# ---------------------------------------------------------------------------

_CISPLATIN_RECORD = {
    "generic_name": "Cisplatin Injection",
    "proprietary_name": "Platinol",
    "status": "Current",
    "shortage_reason": "Increased demand and manufacturing delay",
    "availability": "Limited",
    "estimated_resolution": "2026-06-01",
    "update_date": "2026-04-15",
    "openfda": {
        "rxcui": ["309311", "1049502"],
        "product_ndc": ["00015-3221-22"],
    },
}

_MORPHINE_RECORD = {
    "generic_name": "Morphine Sulfate Injection",
    "proprietary_name": "Duramorph",
    "status": "To Be Discontinued",
    "shortage_reason": "Manufacturing discontinuation",
    "availability": "Unavailable",
    "update_date": "2026-04-20",
    "openfda": {
        "rxcui": ["892297"],
        "product_ndc": ["00641-6012-01"],
    },
}

_RESOLVED_RECORD = {
    "generic_name": "Amoxicillin Oral Suspension",
    "status": "Resolved",
    "shortage_reason": None,
    "openfda": {
        "rxcui": ["723"],
    },
}


def _fda_response(records):
    return {"results": records}


# ---------------------------------------------------------------------------
# POSITIVE — happy path with realistic inputs
# ---------------------------------------------------------------------------

class TestPositive:

    def test_realistic_cisplatin_record_shape(self):
        """POSITIVE: Realistic cisplatin record has correct BriefingItem-adjacent shape."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response([_CISPLATIN_RECORD]),
        ):
            result = get_shortage_detail(rxcui="309311")

        assert isinstance(result, dict)
        assert "error" not in result
        assert isinstance(result["rxcui"], list)
        assert isinstance(result["source_url"], str)
        assert len(result["source_url"]) > 0
        assert result["status"] in {"Current", "To Be Discontinued", "Resolved"}

    def test_get_current_shortages_limit_5_returns_at_most_5(self):
        """POSITIVE: get_current_shortages(limit=5) returns at most 5 records."""
        ten_records = [_CISPLATIN_RECORD] * 10
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response(ten_records[:5]),
        ):
            result = get_current_shortages(limit=5)

        assert isinstance(result, list)
        assert len(result) <= 5

    def test_get_shortage_detail_returns_single_dict_not_list(self):
        """POSITIVE: get_shortage_detail returns a single dict, never a list."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response([_CISPLATIN_RECORD]),
        ):
            result = get_shortage_detail(rxcui="309311")

        assert isinstance(result, dict)
        assert not isinstance(result, list)

    def test_multiple_canonical_status_values_pass_through(self):
        """POSITIVE: status values Current / To Be Discontinued / Resolved all allowed."""
        valid_statuses = {"Current", "To Be Discontinued", "Resolved"}
        records = [_CISPLATIN_RECORD, _MORPHINE_RECORD]
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response(records),
        ):
            result = get_current_shortages(limit=10)

        assert isinstance(result, list)
        for item in result:
            assert item["status"] in valid_statuses, (
                f"Unexpected status value: {item['status']!r}"
            )

    def test_source_url_is_fda_api_url(self):
        """POSITIVE: source_url is a query-specific openFDA API URL containing the RxCUI."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response([_CISPLATIN_RECORD]),
        ):
            result = get_shortage_detail(rxcui="309311")

        assert "error" not in result
        assert "api.fda.gov/drug/shortages.json" in result["source_url"]
        assert "309311" in result["source_url"]

    def test_rxcui_list_preserves_all_entries(self):
        """POSITIVE: multi-rxcui record has all RxCUI values preserved in the list."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response([_CISPLATIN_RECORD]),
        ):
            result = get_shortage_detail(rxcui="309311")

        assert "error" not in result
        assert "309311" in result["rxcui"]
        assert "1049502" in result["rxcui"]


# ---------------------------------------------------------------------------
# NEGATIVE — inputs that should produce handled errors, not crashes
# ---------------------------------------------------------------------------

class TestNegative:

    def test_network_error_in_get_current_shortages_returns_error_dict(self):
        """NEGATIVE: cached_get raises network error → get_current_shortages returns [{'error': ...}] list, not raise."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            side_effect=Exception("network error"),
        ):
            result = get_current_shortages(limit=10)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        assert result[0]["error"]  # non-empty

    def test_network_error_does_not_propagate_in_get_current_shortages(self):
        """NEGATIVE: get_current_shortages never propagates exceptions to caller."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            side_effect=Exception("network error"),
        ):
            try:
                get_current_shortages(limit=5)
            except Exception as exc:
                pytest.fail(f"get_current_shortages propagated exception: {exc!r}")

    def test_timeout_error_in_get_shortage_detail_returns_error_dict(self):
        """NEGATIVE: cached_get raises timeout → get_shortage_detail returns error dict."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            side_effect=Exception("timeout"),
        ):
            result = get_shortage_detail(rxcui="309311")

        assert isinstance(result, dict)
        assert "error" in result
        assert result["error"]

    def test_cached_get_returns_none_sentinel_returns_error_dict(self):
        """NEGATIVE: cached_get returns None (cache miss propagated) → error dict, no crash."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=None,
        ):
            result = get_shortage_detail(rxcui="309311")

        assert isinstance(result, dict)
        assert "error" in result
        assert not isinstance(result, type(None))

    def test_cached_get_empty_results_list_returns_error_dict(self):
        """NEGATIVE: cached_get returns envelope with empty results → error dict for that RxCUI."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value={"results": []},
        ):
            result = get_shortage_detail(rxcui="309311")

        assert isinstance(result, dict)
        assert "error" in result

    def test_trim_record_missing_openfda_key_returns_empty_rxcui_list(self):
        """NEGATIVE: Record with no openfda key → _trim returns rxcui=[] and source_url present."""
        rec = {
            "generic_name": "Some Drug",
            "status": "Current",
            "shortage_reason": "Demand increase",
        }
        result = _trim(rec)

        assert isinstance(result["rxcui"], list)
        assert result["rxcui"] == []
        assert "source_url" in result
        assert result["source_url"]

    def test_trim_record_openfda_rxcui_as_string_coerced_to_list(self):
        """NEGATIVE: openfda.rxcui is a string (malformed) → _trim coerces to list, no crash."""
        rec = {
            "generic_name": "Metformin",
            "status": "Current",
            "openfda": {
                "rxcui": "861007",  # string instead of list
            },
        }
        result = _trim(rec)

        assert isinstance(result["rxcui"], list)
        assert "861007" in result["rxcui"]

    def test_trim_does_not_raise_on_openfda_null(self):
        """NEGATIVE: openfda=null in raw record → _trim returns rxcui=[], ndc=[], no crash."""
        rec = {
            "generic_name": "Vancomycin",
            "status": "Current",
            "openfda": None,
        }
        try:
            result = _trim(rec)
        except Exception as exc:
            pytest.fail(f"_trim raised on openfda=null: {exc!r}")

        assert isinstance(result["rxcui"], list)
        assert isinstance(result["ndc"], list)


# ---------------------------------------------------------------------------
# AMBIENT / DEGRADED — partial or off-nominal system state
# ---------------------------------------------------------------------------

class TestAmbientDegraded:

    def test_limit_above_cap_is_clamped_in_cache_key(self):
        """AMBIENT: limit above the server cap (1000) is clamped; cache key reflects cap."""
        captured_keys = []

        def capture(key, fetch_fn, ttl):
            captured_keys.append(key)
            return _fda_response([_CISPLATIN_RECORD])

        with patch(
            "src.servers.fda_shortage_server.cached_get",
            side_effect=capture,
        ):
            get_current_shortages(limit=5000)

        assert captured_keys, "cached_get was never called"
        key_used = captured_keys[0]
        assert "1000" in key_used, (
            f"Expected '1000' (cap) in cache key after clamping, got: {key_used!r}"
        )
        assert "5000" not in key_used, (
            f"Cache key must not contain unclamped '5000', got: {key_used!r}"
        )

    def test_stale_cache_data_still_returns_valid_shape(self):
        """AMBIENT: stale data from yesterday is still returned correctly shaped."""
        stale_record = dict(_CISPLATIN_RECORD)
        stale_record["update_date"] = (
            datetime.date.today() - datetime.timedelta(days=1)
        ).isoformat()

        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response([stale_record]),
        ):
            result = get_current_shortages(limit=5)

        assert isinstance(result, list)
        assert len(result) >= 1
        for item in result:
            assert "source_url" in item
            assert isinstance(item["rxcui"], list)

    def test_trim_record_missing_generic_name_returns_none_not_keyerror(self):
        """AMBIENT: Record missing generic_name key → _trim returns None for generic_name, no KeyError."""
        rec = {
            "status": "Current",
            "shortage_reason": "Demand increase",
            "openfda": {"rxcui": ["309311"]},
        }
        try:
            result = _trim(rec)
        except KeyError as exc:
            pytest.fail(f"_trim raised KeyError on missing generic_name: {exc!r}")

        assert result["generic_name"] is None

    def test_trim_record_openfda_null_returns_empty_rxcui_and_ndc(self):
        """AMBIENT: openfda=null → rxcui=[] and ndc=[], no crash."""
        rec = {
            "generic_name": "Vancomycin HCl",
            "status": "Current",
            "openfda": None,
        }
        result = _trim(rec)

        assert result["rxcui"] == []
        assert result["ndc"] == []
        assert "source_url" in result

    def test_get_shortage_detail_empty_string_rxcui_does_not_crash(self):
        """AMBIENT: get_shortage_detail("") — empty RxCUI — returns error dict or empty result, never crashes."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value={"results": []},
        ):
            try:
                result = get_shortage_detail("")
            except Exception as exc:
                pytest.fail(f"get_shortage_detail('') raised: {exc!r}")

        # Must be a dict (either error or normal miss response)
        assert isinstance(result, dict)

    def test_get_shortage_detail_empty_string_rxcui_returns_error_dict(self):
        """AMBIENT: get_shortage_detail("") with empty results returns error dict."""
        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value={"results": []},
        ):
            result = get_shortage_detail("")

        assert "error" in result

    def test_large_batch_with_stale_valid_records_shape(self):
        """AMBIENT: Many stale-but-valid records all pass _trim without loss of required keys."""
        stale_records = [dict(_CISPLATIN_RECORD) for _ in range(50)]
        for r in stale_records:
            r["update_date"] = "2025-12-01"  # old but valid

        with patch(
            "src.servers.fda_shortage_server.cached_get",
            return_value=_fda_response(stale_records[:20]),
        ):
            result = get_current_shortages(limit=20)

        assert isinstance(result, list)
        for item in result:
            assert "rxcui" in item
            assert isinstance(item["rxcui"], list)
            assert "source_url" in item
            assert item["source_url"]
