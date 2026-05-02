"""
Unit tests for src/cache.py and src/data_loader.py.

=============================================================================
CODE REVIEW FINDINGS
=============================================================================

src/cache.py
------------
No bugs found.
- Sentinel pattern (_MISS = object()) is correct; distinguishes cached None
  from a true cache miss.
- cached_get() correctly caches None results so failed lookups aren't
  re-fetched on every call.
- Module-level Cache singleton is fine for production use; tests patch it.

src/data_loader.py
------------------

BUG-1 (FIXED): generate_yesterday_snapshot() appends fake RESOLVED records
  with raw openFDA shape:
    {"generic_name": ..., "openfda": {"rxcui": ["..."]}, ...}
  but all other records in `yesterday` are already _trim()-processed:
    {"generic_name": ..., "rxcui": [...], ...}
  Any consumer reading snapshot["results"] and accessing record["rxcui"]
  will get a KeyError on the fake records. The fake records must use the
  same trimmed shape as the rest of the list.
  FIX: Changed fake record structure to use trimmed shape (rxcui as top-level
  list, no openfda wrapper).

BUG-2 (minor, not fixed — design choice): synthesize_formulary() writes
  "rxcui": d["rxcui"][0] (primary RxCUI scalar) into each formulary entry
  alongside "rxcui_list": d["rxcui"]. This means the formulary's `rxcui`
  field is a scalar, not a list — which is intentional per Q2 design notes
  ("primary RxCUI heuristic = open Q"). No fix applied; flagged for awareness.

BUG-3 (not fixed — design gap): _fetch_shortages_raw() returns cached_get()
  which could theoretically return None if something external corrupts the
  cache entry. sample_drugs_from_feed() would then crash with TypeError on
  `for rec in raw:`. In practice _fetch always returns a list ([] on 404,
  list from .get("results", [])), so this is a theoretical concern. A
  defensive `or []` guard on the return would be belt-and-suspenders.

EDGE CASES NOTED (no bugs):
- fetch_class_alternatives() correctly swallows all Exception subclasses and
  returns [] — never raises. KeyboardInterrupt / SystemExit are not swallowed
  (they're BaseException), which is correct.
- index_by_rxcui() correctly handles multi-RxCUI records; later RxCUIs in
  the list overwrite earlier ones if two drugs share a secondary RxCUI — this
  is an acknowledged Q2 trade-off, not a bug.
- _trim() always returns rxcui as a list (never coerced to scalar).
- sample_drugs_from_feed() dedupes correctly on primary RxCUI (first element).
- R6 mitigation in main() correctly gates on YESTERDAY_PATH.exists().
=============================================================================
"""

import json
import random
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# A representative raw FDA record (openFDA shape).
RAW_RECORD_MULTI = {
    "generic_name": "Cisplatin Injection",
    "status": "Current",
    "shortage_reason": "Demand increase",
    "openfda": {
        "rxcui": ["309311", "1049502"],
        "brand_name": ["Platinol"],
        "route": ["INTRAVENOUS"],
    },
}

RAW_RECORD_SINGLE = {
    "generic_name": "Methotrexate Injection",
    "status": "Current",
    "shortage_reason": "Manufacturing delay",
    "openfda": {
        "rxcui": ["105585"],
        "brand_name": ["Rheumatrex"],
        "route": ["INTRAVENOUS"],
    },
}

RAW_RECORD_NO_RXCUI = {
    "generic_name": "Some Drug",
    "status": "Current",
    "shortage_reason": "Other",
    "openfda": {},
}

RAW_RECORD_NO_OPENFDA = {
    "generic_name": "Another Drug",
    "status": "Current",
    "shortage_reason": "Other",
}


def make_trimmed(generic_name="Cisplatin Injection", rxcui=None, status="Current"):
    """Helper: build a _trim()-shaped drug record."""
    return {
        "generic_name": generic_name,
        "status": status,
        "shortage_reason": "Demand increase",
        "rxcui": rxcui if rxcui is not None else ["309311", "1049502"],
        "brand_name": "Platinol",
        "route": "INTRAVENOUS",
    }


def make_drug_list(n=10):
    """Return n distinct trimmed drug records with unique primary RxCUIs."""
    return [
        make_trimmed(
            generic_name=f"Drug {i}",
            rxcui=[str(1000 + i), str(2000 + i)],
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# src/cache.py tests
# ---------------------------------------------------------------------------

class TestCachedGet:
    """Tests for cache.cached_get() sentinel pattern."""

    def setup_method(self):
        """Use a fresh in-memory diskcache for each test."""
        import diskcache
        self.raw_cache = diskcache.Cache()  # tmpdir, in-memory-like

    def teardown_method(self):
        self.raw_cache.close()

    def _make_cached_get(self):
        """Return a cached_get bound to our test cache."""
        from src import cache as cache_mod
        # We'll monkey-patch the module-level _cache for isolation.
        return self.raw_cache

    def test_cache_hit_returns_value(self):
        """cached_get returns stored value on second call without invoking fetch_fn."""
        from src import cache as cache_mod
        original_cache = cache_mod._cache
        cache_mod._cache = self.raw_cache
        try:
            fetch_fn = MagicMock(return_value={"result": "data"})
            key = "test:hit"

            v1 = cache_mod.cached_get(key, fetch_fn, ttl=60)
            v2 = cache_mod.cached_get(key, fetch_fn, ttl=60)

            assert v1 == {"result": "data"}
            assert v2 == {"result": "data"}
            fetch_fn.assert_called_once()  # only one real fetch
        finally:
            cache_mod._cache = original_cache

    def test_cache_miss_calls_fetch_fn(self):
        """cached_get calls fetch_fn on a cold cache."""
        from src import cache as cache_mod
        original_cache = cache_mod._cache
        cache_mod._cache = self.raw_cache
        try:
            fetch_fn = MagicMock(return_value=42)
            result = cache_mod.cached_get("test:miss", fetch_fn, ttl=60)
            assert result == 42
            fetch_fn.assert_called_once()
        finally:
            cache_mod._cache = original_cache

    def test_none_result_is_cached(self):
        """cached_get caches None — second call must NOT invoke fetch_fn again."""
        from src import cache as cache_mod
        original_cache = cache_mod._cache
        cache_mod._cache = self.raw_cache
        try:
            fetch_fn = MagicMock(return_value=None)
            key = "test:none"

            v1 = cache_mod.cached_get(key, fetch_fn, ttl=60)
            v2 = cache_mod.cached_get(key, fetch_fn, ttl=60)

            assert v1 is None
            assert v2 is None
            fetch_fn.assert_called_once()  # sentinel: None must be cached, not re-fetched
        finally:
            cache_mod._cache = original_cache

    def test_empty_list_result_is_cached(self):
        """cached_get caches empty list — second call does not re-fetch."""
        from src import cache as cache_mod
        original_cache = cache_mod._cache
        cache_mod._cache = self.raw_cache
        try:
            fetch_fn = MagicMock(return_value=[])
            key = "test:empty_list"

            cache_mod.cached_get(key, fetch_fn, ttl=60)
            cache_mod.cached_get(key, fetch_fn, ttl=60)

            fetch_fn.assert_called_once()
        finally:
            cache_mod._cache = original_cache

    def test_false_result_is_cached(self):
        """cached_get caches falsy non-None values (False, 0) correctly."""
        from src import cache as cache_mod
        original_cache = cache_mod._cache
        cache_mod._cache = self.raw_cache
        try:
            fetch_fn = MagicMock(return_value=False)
            key = "test:false"

            v1 = cache_mod.cached_get(key, fetch_fn, ttl=60)
            v2 = cache_mod.cached_get(key, fetch_fn, ttl=60)

            assert v1 is False
            assert v2 is False
            fetch_fn.assert_called_once()
        finally:
            cache_mod._cache = original_cache

    def test_different_keys_independent(self):
        """Two different keys don't collide."""
        from src import cache as cache_mod
        original_cache = cache_mod._cache
        cache_mod._cache = self.raw_cache
        try:
            fetch_a = MagicMock(return_value="alpha")
            fetch_b = MagicMock(return_value="beta")

            va = cache_mod.cached_get("key:a", fetch_a, ttl=60)
            vb = cache_mod.cached_get("key:b", fetch_b, ttl=60)

            assert va == "alpha"
            assert vb == "beta"
        finally:
            cache_mod._cache = original_cache

    def test_clear_key_forces_refetch(self):
        """clear_key() removes entry so next cached_get re-invokes fetch_fn."""
        from src import cache as cache_mod
        original_cache = cache_mod._cache
        cache_mod._cache = self.raw_cache
        try:
            fetch_fn = MagicMock(side_effect=["first", "second"])
            key = "test:clear"

            v1 = cache_mod.cached_get(key, fetch_fn, ttl=60)
            cache_mod.clear_key(key)
            v2 = cache_mod.cached_get(key, fetch_fn, ttl=60)

            assert v1 == "first"
            assert v2 == "second"
            assert fetch_fn.call_count == 2
        finally:
            cache_mod._cache = original_cache

    def test_cache_info_returns_dict_with_required_keys(self):
        """cache_info() returns dict with directory, size_bytes, item_count."""
        from src.cache import cache_info
        info = cache_info()
        assert "directory" in info
        assert "size_bytes" in info
        assert "item_count" in info
        assert isinstance(info["item_count"], int)


# ---------------------------------------------------------------------------
# src/data_loader._trim() tests
# ---------------------------------------------------------------------------

class TestTrim:
    """Tests for the _trim() helper."""

    def test_rxcui_preserved_as_list_multi(self):
        """_trim() keeps rxcui as a list when multiple RxCUIs present."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_MULTI)
        assert isinstance(result["rxcui"], list)
        assert result["rxcui"] == ["309311", "1049502"]

    def test_rxcui_preserved_as_list_single(self):
        """_trim() keeps rxcui as a list even with a single RxCUI."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_SINGLE)
        assert isinstance(result["rxcui"], list)
        assert len(result["rxcui"]) == 1

    def test_rxcui_empty_when_no_openfda(self):
        """_trim() returns empty list for rxcui when openfda key is missing."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_NO_OPENFDA)
        assert result["rxcui"] == []

    def test_rxcui_empty_when_openfda_has_no_rxcui(self):
        """_trim() returns empty list for rxcui when openfda.rxcui is absent."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_NO_RXCUI)
        assert result["rxcui"] == []

    def test_brand_name_is_scalar(self):
        """_trim() extracts first brand_name as a scalar string."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_MULTI)
        assert isinstance(result["brand_name"], str)
        assert result["brand_name"] == "Platinol"

    def test_route_is_scalar(self):
        """_trim() extracts first route as a scalar string."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_MULTI)
        assert isinstance(result["route"], str)
        assert result["route"] == "INTRAVENOUS"

    def test_generic_name_preserved(self):
        """_trim() preserves generic_name."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_MULTI)
        assert result["generic_name"] == "Cisplatin Injection"

    def test_unknown_generic_name_default(self):
        """_trim() defaults generic_name to 'Unknown' when field is absent."""
        from src.io_.data_loader import _trim
        result = _trim({"openfda": {"rxcui": ["123"]}})
        assert result["generic_name"] == "Unknown"

    def test_status_preserved(self):
        """_trim() preserves status field."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_MULTI)
        assert result["status"] == "Current"

    def test_openfda_noise_stripped(self):
        """_trim() removes the openfda wrapper; top-level keys only in output."""
        from src.io_.data_loader import _trim
        result = _trim(RAW_RECORD_MULTI)
        assert "openfda" not in result

    def test_null_openfda_treated_as_empty(self):
        """_trim() handles openfda: null gracefully."""
        from src.io_.data_loader import _trim
        record = {"generic_name": "Drug X", "openfda": None}
        result = _trim(record)
        assert result["rxcui"] == []
        assert result["brand_name"] == ""
        assert result["route"] == ""


# ---------------------------------------------------------------------------
# src/data_loader.index_by_rxcui() tests
# ---------------------------------------------------------------------------

class TestIndexByRxcui:
    """Tests for index_by_rxcui()."""

    def test_single_rxcui_indexed(self):
        """A single-RxCUI drug produces one index entry."""
        from src.io_.data_loader import index_by_rxcui
        drugs = [make_trimmed(rxcui=["AAA"])]
        idx = index_by_rxcui(drugs)
        assert "AAA" in idx
        assert idx["AAA"] is drugs[0]

    def test_multi_rxcui_all_indexed(self):
        """A multi-RxCUI drug produces one entry per RxCUI."""
        from src.io_.data_loader import index_by_rxcui
        drugs = [make_trimmed(rxcui=["AAA", "BBB", "CCC"])]
        idx = index_by_rxcui(drugs)
        assert "AAA" in idx
        assert "BBB" in idx
        assert "CCC" in idx
        # All point to same record
        assert idx["AAA"] is idx["BBB"] is idx["CCC"] is drugs[0]

    def test_multiple_drugs_indexed(self):
        """Multiple drugs each get their own entries."""
        from src.io_.data_loader import index_by_rxcui
        drug_a = make_trimmed(generic_name="Drug A", rxcui=["111"])
        drug_b = make_trimmed(generic_name="Drug B", rxcui=["222"])
        idx = index_by_rxcui([drug_a, drug_b])
        assert idx["111"] is drug_a
        assert idx["222"] is drug_b

    def test_empty_rxcui_drug_excluded(self):
        """Drug with empty rxcui list produces no index entries."""
        from src.io_.data_loader import index_by_rxcui
        drug = make_trimmed(rxcui=[])
        idx = index_by_rxcui([drug])
        assert idx == {}

    def test_empty_input(self):
        """Empty drug list returns empty index."""
        from src.io_.data_loader import index_by_rxcui
        assert index_by_rxcui([]) == {}

    def test_later_drug_overwrites_shared_rxcui(self):
        """If two drugs share a RxCUI, last one wins (acknowledged Q2 trade-off)."""
        from src.io_.data_loader import index_by_rxcui
        drug_a = make_trimmed(generic_name="Drug A", rxcui=["SHARED"])
        drug_b = make_trimmed(generic_name="Drug B", rxcui=["SHARED"])
        idx = index_by_rxcui([drug_a, drug_b])
        # Last writer wins — this is the expected behavior, not a bug
        assert idx["SHARED"] is drug_b


# ---------------------------------------------------------------------------
# src/data_loader.sample_drugs_from_feed() tests
# ---------------------------------------------------------------------------

class TestSampleDrugsFromFeed:
    """Tests for sample_drugs_from_feed() with mocked HTTP."""

    def _patch_fetch_raw(self, records):
        """Patch _fetch_shortages_raw to return `records` directly."""
        return patch("src.io_.data_loader._fetch_shortages_raw", return_value=records)

    def test_filters_records_without_rxcui(self):
        """Records with no RxCUI are excluded."""
        from src.io_.data_loader import sample_drugs_from_feed
        raw = [RAW_RECORD_MULTI, RAW_RECORD_NO_RXCUI, RAW_RECORD_SINGLE]
        with self._patch_fetch_raw(raw):
            drugs = sample_drugs_from_feed(target=30)
        names = [d["generic_name"] for d in drugs]
        assert "Some Drug" not in names
        assert len(drugs) == 2

    def test_dedupes_by_primary_rxcui(self):
        """Two records sharing the same primary RxCUI produce only one entry."""
        from src.io_.data_loader import sample_drugs_from_feed
        dup_a = deepcopy(RAW_RECORD_MULTI)
        dup_b = deepcopy(RAW_RECORD_MULTI)
        dup_b["generic_name"] = "Cisplatin Variant"
        # Both have same primary RxCUI ("309311")
        with self._patch_fetch_raw([dup_a, dup_b]):
            drugs = sample_drugs_from_feed(target=30)
        assert len(drugs) == 1

    def test_respects_target_limit(self):
        """Returns at most `target` records."""
        from src.io_.data_loader import sample_drugs_from_feed
        # 20 records, each with unique primary RxCUI
        raw = [
            {
                "generic_name": f"Drug {i}",
                "status": "Current",
                "shortage_reason": "X",
                "openfda": {"rxcui": [str(i)]},
            }
            for i in range(20)
        ]
        with self._patch_fetch_raw(raw):
            drugs = sample_drugs_from_feed(target=5)
        assert len(drugs) == 5

    def test_returns_trimmed_records(self):
        """Returned records are _trim()-shaped (no openfda wrapper)."""
        from src.io_.data_loader import sample_drugs_from_feed
        with self._patch_fetch_raw([RAW_RECORD_MULTI]):
            drugs = sample_drugs_from_feed()
        assert len(drugs) == 1
        assert "openfda" not in drugs[0]
        assert isinstance(drugs[0]["rxcui"], list)

    def test_empty_feed_returns_empty_list(self):
        """Empty FDA feed returns empty list without error."""
        from src.io_.data_loader import sample_drugs_from_feed
        with self._patch_fetch_raw([]):
            drugs = sample_drugs_from_feed()
        assert drugs == []

    def test_deduplication_uses_first_rxcui(self):
        """Deduplication key is rxcui[0] (primary), not rxcui[1]."""
        from src.io_.data_loader import sample_drugs_from_feed
        # Two records: same secondary RxCUI but different primary → both included
        rec_a = {
            "generic_name": "Drug A",
            "status": "Current",
            "shortage_reason": "X",
            "openfda": {"rxcui": ["PRIMAARY_A", "SHARED_SECONDARY"]},
        }
        rec_b = {
            "generic_name": "Drug B",
            "status": "Current",
            "shortage_reason": "X",
            "openfda": {"rxcui": ["PRIMARY_B", "SHARED_SECONDARY"]},
        }
        with self._patch_fetch_raw([rec_a, rec_b]):
            drugs = sample_drugs_from_feed(target=30)
        assert len(drugs) == 2


# ---------------------------------------------------------------------------
# src/data_loader.fetch_class_alternatives() tests
# ---------------------------------------------------------------------------

class TestFetchClassAlternatives:
    """Tests for fetch_class_alternatives() with mocked HTTP."""

    def test_returns_list_of_strings(self):
        """Happy path: returns a list of drug name strings."""
        from src.io_.data_loader import fetch_class_alternatives
        with patch("src.io_.data_loader._normalize_to_rxcui", return_value="2555"), \
             patch("src.io_.data_loader._get_atc_class", return_value={"classId": "L01XA01", "className": "CISPLATIN"}), \
             patch("src.io_.data_loader._get_class_members", return_value=[
                 {"rxcui": "99999", "name": "Carboplatin"},
                 {"rxcui": "88888", "name": "Oxaliplatin"},
             ]):
            result = fetch_class_alternatives("cisplatin")
        assert isinstance(result, list)
        assert "Carboplatin" in result
        assert "Oxaliplatin" in result

    def test_excludes_queried_drug_itself(self):
        """The drug being queried (same rxcui) is excluded from results."""
        from src.io_.data_loader import fetch_class_alternatives
        with patch("src.io_.data_loader._normalize_to_rxcui", return_value="2555"), \
             patch("src.io_.data_loader._get_atc_class", return_value={"classId": "L01XA01", "className": "CISPLATIN"}), \
             patch("src.io_.data_loader._get_class_members", return_value=[
                 {"rxcui": "2555", "name": "Cisplatin"},   # same rxcui → excluded
                 {"rxcui": "99999", "name": "Carboplatin"},
             ]):
            result = fetch_class_alternatives("cisplatin")
        assert "Cisplatin" not in result
        assert "Carboplatin" in result

    def test_caps_at_10_results(self):
        """At most 10 alternatives are returned."""
        from src.io_.data_loader import fetch_class_alternatives
        members = [{"rxcui": str(i), "name": f"Drug{i}"} for i in range(20)]
        with patch("src.io_.data_loader._normalize_to_rxcui", return_value="2555"), \
             patch("src.io_.data_loader._get_atc_class", return_value={"classId": "L01XA01", "className": "X"}), \
             patch("src.io_.data_loader._get_class_members", return_value=members):
            result = fetch_class_alternatives("cisplatin")
        assert len(result) <= 10

    def test_returns_empty_when_rxcui_not_found(self):
        """Returns [] when drug name cannot be resolved to a RxCUI."""
        from src.io_.data_loader import fetch_class_alternatives
        with patch("src.io_.data_loader._normalize_to_rxcui", return_value=None):
            result = fetch_class_alternatives("unknown_drug_xyz")
        assert result == []

    def test_returns_empty_when_no_atc_class(self):
        """Returns [] when no ATC class is found for the RxCUI."""
        from src.io_.data_loader import fetch_class_alternatives
        with patch("src.io_.data_loader._normalize_to_rxcui", return_value="2555"), \
             patch("src.io_.data_loader._get_atc_class", return_value=None):
            result = fetch_class_alternatives("cisplatin")
        assert result == []

    def test_returns_empty_on_http_exception(self):
        """Returns [] silently if any underlying call raises an exception."""
        from src.io_.data_loader import fetch_class_alternatives
        with patch("src.io_.data_loader._normalize_to_rxcui", side_effect=Exception("network error")):
            result = fetch_class_alternatives("cisplatin")
        assert result == []

    def test_returns_empty_on_key_error(self):
        """Returns [] if member dict is malformed (missing keys)."""
        from src.io_.data_loader import fetch_class_alternatives
        with patch("src.io_.data_loader._normalize_to_rxcui", return_value="2555"), \
             patch("src.io_.data_loader._get_atc_class", return_value={"classId": "L01XA01"}), \
             patch("src.io_.data_loader._get_class_members", side_effect=KeyError("classId")):
            result = fetch_class_alternatives("cisplatin")
        assert result == []

    def test_never_raises(self):
        """fetch_class_alternatives() never propagates any Exception."""
        from src.io_.data_loader import fetch_class_alternatives
        errors = [
            RuntimeError("boom"),
            ValueError("bad"),
            ConnectionError("net"),
            json.JSONDecodeError("msg", "", 0),
        ]
        for err in errors:
            with patch("src.io_.data_loader._normalize_to_rxcui", side_effect=err):
                try:
                    result = fetch_class_alternatives("any")
                    assert result == []
                except Exception as e:
                    pytest.fail(f"fetch_class_alternatives raised {e!r}")


# ---------------------------------------------------------------------------
# src/data_loader.generate_yesterday_snapshot() tests
# ---------------------------------------------------------------------------

class TestGenerateYesterdaySnapshot:
    """Tests for generate_yesterday_snapshot()."""

    def test_returns_dict_with_required_keys(self):
        """Output has snapshot_date, label, and results keys."""
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        snap = generate_yesterday_snapshot(drugs)
        assert "snapshot_date" in snap
        assert "label" in snap
        assert "results" in snap

    def test_two_records_dropped_new_today(self):
        """Yesterday has 2 fewer records than today (the 2 NEW shortages)."""
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        snap = generate_yesterday_snapshot(drugs)
        # 15 original - 2 dropped + 2 fake resolved = 15 total
        # The net count = original_count - 2 dropped + 2 fake appended
        assert len(snap["results"]) == len(drugs)  # 15 - 2 + 2 = 15

    def test_two_fake_resolved_appended(self):
        """Yesterday snapshot includes 2 FAKE_RESOLVED records."""
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        snap = generate_yesterday_snapshot(drugs)
        fake_names = [r["generic_name"] for r in snap["results"]
                      if "FAKE_RESOLVED" in r.get("generic_name", "")]
        assert len(fake_names) == 2

    def test_status_flips_applied(self):
        """Two records have status flipped to Resolved / Available with limitations."""
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        snap = generate_yesterday_snapshot(drugs)
        statuses = [r["status"] for r in snap["results"]]
        assert "Resolved" in statuses
        assert "Available with limitations" in statuses

    def test_fake_resolved_records_have_consistent_shape(self):
        """BUG-1: Fake RESOLVED records must use trimmed shape (rxcui as list),
        not raw openFDA shape (openfda.rxcui), so consumers can access record['rxcui'].
        """
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        snap = generate_yesterday_snapshot(drugs)
        for record in snap["results"]:
            # Every record must have top-level 'rxcui' as a list
            assert "rxcui" in record, (
                f"Record missing top-level 'rxcui': {record['generic_name']}"
            )
            assert isinstance(record["rxcui"], list), (
                f"'rxcui' is not a list for: {record['generic_name']}"
            )
            # openfda wrapper must not be present (trimmed shape)
            assert "openfda" not in record, (
                f"Record has raw 'openfda' key instead of trimmed shape: {record['generic_name']}"
            )

    def test_sparse_path_when_fewer_than_10(self):
        """With <10 drugs the function returns without applying diff scenarios."""
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(5)
        snap = generate_yesterday_snapshot(drugs)
        # Should return early — no fake records added
        assert "results" in snap
        assert len(snap["results"]) == 5  # unchanged copy

    def test_snapshot_date_is_yesterday(self):
        """snapshot_date is one day before today."""
        from datetime import datetime, timezone, timedelta
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        snap = generate_yesterday_snapshot(drugs)
        today = datetime.now(timezone.utc).date()
        expected_yesterday = (today - timedelta(days=1)).isoformat()
        assert snap["snapshot_date"] == expected_yesterday

    def test_does_not_mutate_input(self):
        """generate_yesterday_snapshot() does not mutate the input drug list."""
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        original = deepcopy(drugs)
        generate_yesterday_snapshot(drugs)
        assert drugs == original

    def test_deterministic_with_same_seed(self):
        """Two calls on same input produce identical results (seed=44)."""
        from src.io_.data_loader import generate_yesterday_snapshot
        drugs = make_drug_list(15)
        snap1 = generate_yesterday_snapshot(drugs)
        snap2 = generate_yesterday_snapshot(drugs)
        assert snap1["results"] == snap2["results"]


# ---------------------------------------------------------------------------
# src/data_loader.synthesize_formulary() tests
# ---------------------------------------------------------------------------

class TestSynthesizeFormulary:
    """Tests for synthesize_formulary()."""

    def test_returns_dict_with_required_keys(self):
        """Output has customer_id, label, generated_at, drugs."""
        from src.io_.data_loader import synthesize_formulary
        drugs = make_drug_list(5)
        with patch("src.io_.data_loader.fetch_class_alternatives", return_value=[]):
            formulary = synthesize_formulary(drugs)
        assert "customer_id" in formulary
        assert "label" in formulary
        assert "generated_at" in formulary
        assert "drugs" in formulary

    def test_drug_count_matches_input(self):
        """Output contains one formulary entry per input drug."""
        from src.io_.data_loader import synthesize_formulary
        drugs = make_drug_list(8)
        with patch("src.io_.data_loader.fetch_class_alternatives", return_value=[]):
            formulary = synthesize_formulary(drugs)
        assert len(formulary["drugs"]) == 8

    def test_primary_rxcui_is_scalar(self):
        """Each formulary entry has rxcui as a scalar string (primary RxCUI)."""
        from src.io_.data_loader import synthesize_formulary
        drugs = [make_trimmed(rxcui=["309311", "1049502"])]
        with patch("src.io_.data_loader.fetch_class_alternatives", return_value=[]):
            formulary = synthesize_formulary(drugs)
        entry = formulary["drugs"][0]
        assert isinstance(entry["rxcui"], str)
        assert entry["rxcui"] == "309311"

    def test_rxcui_list_preserved(self):
        """Each formulary entry has rxcui_list preserving all RxCUIs."""
        from src.io_.data_loader import synthesize_formulary
        drugs = [make_trimmed(rxcui=["309311", "1049502"])]
        with patch("src.io_.data_loader.fetch_class_alternatives", return_value=[]):
            formulary = synthesize_formulary(drugs)
        entry = formulary["drugs"][0]
        assert entry["rxcui_list"] == ["309311", "1049502"]

    def test_demo_drug_alternatives_populated(self):
        """DEMO_DRUG_NAMES get their alternatives pre-populated."""
        from src.io_.data_loader import synthesize_formulary
        cisplatin_drug = make_trimmed(
            generic_name="Cisplatin Injection",
            rxcui=["309311"],
        )
        with patch("src.io_.data_loader.fetch_class_alternatives",
                   return_value=["Carboplatin", "Oxaliplatin"]):
            formulary = synthesize_formulary([cisplatin_drug])
        entry = formulary["drugs"][0]
        assert "Carboplatin" in entry["preferred_alternatives"]

    def test_deterministic_with_seed_42(self):
        """synthesize_formulary uses seed=42 — same input → same formulary_status."""
        from src.io_.data_loader import synthesize_formulary
        drugs = make_drug_list(5)
        with patch("src.io_.data_loader.fetch_class_alternatives", return_value=[]):
            f1 = synthesize_formulary(drugs)
            f2 = synthesize_formulary(drugs)
        statuses1 = [d["formulary_status"] for d in f1["drugs"]]
        statuses2 = [d["formulary_status"] for d in f2["drugs"]]
        assert statuses1 == statuses2


# ---------------------------------------------------------------------------
# src/data_loader.synthesize_orders() tests
# ---------------------------------------------------------------------------

class TestSynthesizeOrders:
    """Tests for synthesize_orders()."""

    def test_returns_dict_with_required_keys(self):
        """Output has customer_id, snapshot_date, label, orders."""
        from src.io_.data_loader import synthesize_orders
        drugs = make_drug_list(5)
        orders = synthesize_orders(drugs)
        assert "customer_id" in orders
        assert "snapshot_date" in orders
        assert "label" in orders
        assert "orders" in orders

    def test_order_count_matches_input(self):
        """One order per input drug."""
        from src.io_.data_loader import synthesize_orders
        drugs = make_drug_list(7)
        orders = synthesize_orders(drugs)
        assert len(orders["orders"]) == 7

    def test_orders_have_required_fields(self):
        """Each order has rxcui, count_last_30_days, departments."""
        from src.io_.data_loader import synthesize_orders
        drugs = make_drug_list(3)
        orders = synthesize_orders(drugs)
        for order in orders["orders"]:
            assert "rxcui" in order
            assert "count_last_30_days" in order
            assert "departments" in order
            assert isinstance(order["departments"], list)

    def test_deterministic_with_seed_43(self):
        """synthesize_orders uses seed=43 — same input → same counts."""
        from src.io_.data_loader import synthesize_orders
        drugs = make_drug_list(5)
        o1 = synthesize_orders(drugs)
        o2 = synthesize_orders(drugs)
        assert o1["orders"] == o2["orders"]


# ---------------------------------------------------------------------------
# src/data_loader.main() R6 mitigation test
# ---------------------------------------------------------------------------

class TestMainR6Mitigation:
    """R6: yesterday_snapshot.json is skipped if it already exists."""

    def test_skips_snapshot_generation_when_file_exists(self, tmp_path, monkeypatch):
        """main() does not overwrite yesterday_snapshot.json if it already exists."""
        from src.io_ import data_loader as dl_mod

        # Redirect all data paths to tmp_path
        monkeypatch.setattr(dl_mod, "DATA_DIR", tmp_path)
        monkeypatch.setattr(dl_mod, "FORMULARY_PATH", tmp_path / "synthetic_formulary.json")
        monkeypatch.setattr(dl_mod, "ORDERS_PATH", tmp_path / "active_orders.json")
        yesterday_path = tmp_path / "yesterday_snapshot.json"
        monkeypatch.setattr(dl_mod, "YESTERDAY_PATH", yesterday_path)

        # Pre-create the yesterday snapshot with sentinel content
        sentinel_content = {"sentinel": True, "results": []}
        yesterday_path.write_text(json.dumps(sentinel_content))

        drugs = make_drug_list(10)

        fake_drugs = [
            {
                "rxcui": "111", "name": "Drug 0",
                "formulary_status": "preferred",
                "preferred_alternatives": [],
            }
            for _ in drugs
        ]
        with patch.object(dl_mod, "sample_drugs_from_feed", return_value=drugs), \
             patch.object(dl_mod, "synthesize_formulary", return_value={
                 "customer_id": "x", "label": "SYNTHETIC", "generated_at": "now",
                 "drugs": fake_drugs,
             }), \
             patch.object(dl_mod, "synthesize_orders", return_value={
                 "customer_id": "x", "snapshot_date": "2026-01-01",
                 "label": "SYNTHETIC", "orders": [],
             }), \
             patch.object(dl_mod, "generate_yesterday_snapshot") as mock_gen:
            dl_mod.main()

        # generate_yesterday_snapshot must NOT have been called
        mock_gen.assert_not_called()

        # File content must be unchanged (sentinel preserved)
        actual = json.loads(yesterday_path.read_text())
        assert actual == sentinel_content

    def test_generates_snapshot_when_file_missing(self, tmp_path, monkeypatch):
        """main() calls generate_yesterday_snapshot() when file does not exist."""
        from src.io_ import data_loader as dl_mod

        monkeypatch.setattr(dl_mod, "DATA_DIR", tmp_path)
        monkeypatch.setattr(dl_mod, "FORMULARY_PATH", tmp_path / "synthetic_formulary.json")
        monkeypatch.setattr(dl_mod, "ORDERS_PATH", tmp_path / "active_orders.json")
        yesterday_path = tmp_path / "yesterday_snapshot.json"
        monkeypatch.setattr(dl_mod, "YESTERDAY_PATH", yesterday_path)

        assert not yesterday_path.exists()

        drugs = make_drug_list(10)
        fake_snapshot = {"snapshot_date": "2026-04-30", "label": "SYNTHETIC", "results": []}

        fake_drugs = [
            {
                "rxcui": "111", "name": "Drug 0",
                "formulary_status": "preferred",
                "preferred_alternatives": [],
            }
            for _ in drugs
        ]
        with patch.object(dl_mod, "sample_drugs_from_feed", return_value=drugs), \
             patch.object(dl_mod, "synthesize_formulary", return_value={
                 "customer_id": "x", "label": "SYNTHETIC", "generated_at": "now",
                 "drugs": fake_drugs,
             }), \
             patch.object(dl_mod, "synthesize_orders", return_value={
                 "customer_id": "x", "snapshot_date": "2026-01-01",
                 "label": "SYNTHETIC", "orders": [],
             }), \
             patch.object(dl_mod, "generate_yesterday_snapshot", return_value=fake_snapshot) as mock_gen:
            dl_mod.main()

        mock_gen.assert_called_once()
        assert yesterday_path.exists()


# ---------------------------------------------------------------------------
# HTTP-level integration: _fetch_shortages_raw() + cached_get wiring
# ---------------------------------------------------------------------------

class TestFetchShortagesRaw:
    """Tests for _fetch_shortages_raw() with mocked httpx."""

    def test_returns_results_on_200(self):
        """Returns results list from FDA JSON on HTTP 200."""
        from src.io_.data_loader import _fetch_shortages_raw

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [RAW_RECORD_MULTI, RAW_RECORD_SINGLE]}

        # Bypass the disk cache entirely for this test
        with patch("src.io_.data_loader.cached_get", side_effect=lambda key, fn, ttl: fn()), \
             patch("httpx.get", return_value=mock_resp):
            result = _fetch_shortages_raw(limit=10)

        assert len(result) == 2

    def test_returns_empty_list_on_404(self):
        """Returns [] when FDA returns HTTP 404 (no records for query)."""
        from src.io_.data_loader import _fetch_shortages_raw

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("src.io_.data_loader.cached_get", side_effect=lambda key, fn, ttl: fn()), \
             patch("httpx.get", return_value=mock_resp):
            result = _fetch_shortages_raw(limit=10)

        assert result == []

    def test_raises_on_non_404_http_error(self):
        """Non-404 HTTP errors propagate (raise_for_status)."""
        import httpx as httpx_mod
        from src.io_.data_loader import _fetch_shortages_raw

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx_mod.HTTPStatusError(
            "server error", request=MagicMock(), response=mock_resp
        )

        with patch("src.io_.data_loader.cached_get", side_effect=lambda key, fn, ttl: fn()), \
             patch("httpx.get", return_value=mock_resp):
            with pytest.raises(httpx_mod.HTTPStatusError):
                _fetch_shortages_raw(limit=10)
