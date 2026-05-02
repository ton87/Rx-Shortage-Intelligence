"""
Tests for src/io_/briefing_store.py

TDD: written before implementation is wired into production code.

Covers:
  - find_latest_briefing() returns None on missing directory
  - find_latest_briefing() picks newest by run_timestamp, not filename
  - load_briefing() parses JSON correctly
  - write_briefing() writes atomically (tmp + rename, final file correct)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_briefing(run_timestamp: str, items: list | None = None) -> dict:
    """Build a minimal briefing run dict."""
    return {
        "run_id": "test-run",
        "run_timestamp": run_timestamp,
        "date": run_timestamp[:10],
        "items": items or [],
        "tool_calls": [],
        "latency_ms": 0,
    }


# ---------------------------------------------------------------------------
# find_latest_briefing()
# ---------------------------------------------------------------------------

class TestFindLatestBriefing:

    def test_returns_none_when_directory_missing(self, tmp_path):
        """Returns None if the briefings directory does not exist."""
        from src.io_.briefing_store import find_latest_briefing
        missing_dir = tmp_path / "briefings"
        assert not missing_dir.exists()

        with patch("src.io_.briefing_store.BRIEFINGS_DIR", missing_dir):
            result = find_latest_briefing()

        assert result is None

    def test_returns_none_when_directory_empty(self, tmp_path):
        """Returns None if the briefings directory exists but has no JSON files."""
        from src.io_.briefing_store import find_latest_briefing
        briefings_dir = tmp_path / "briefings"
        briefings_dir.mkdir()

        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            result = find_latest_briefing()

        assert result is None

    def test_picks_newest_by_run_timestamp_not_filename(self, tmp_path):
        """Selects the file with the latest run_timestamp, not lexicographic filename.

        Scenario: 2026-05-02.json has an OLDER timestamp than 2026-05-01.json.
        (This simulates a file written with a future-named file but stale content.)
        find_latest_briefing() must return 2026-05-01.json.
        """
        from src.io_.briefing_store import find_latest_briefing
        briefings_dir = tmp_path / "briefings"
        briefings_dir.mkdir()

        # Older timestamp, newer filename
        file_a = briefings_dir / "2026-05-02.json"
        file_a.write_text(json.dumps(_make_briefing("2026-05-01T10:00:00+00:00")))

        # Newer timestamp, older filename
        file_b = briefings_dir / "2026-05-01.json"
        file_b.write_text(json.dumps(_make_briefing("2026-05-02T08:00:00+00:00")))

        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            result = find_latest_briefing()

        assert result == file_b, (
            f"Expected {file_b.name} (newer run_timestamp) but got {result.name}"
        )

    def test_picks_single_file_when_only_one(self, tmp_path):
        """Returns the only file when exactly one JSON is present."""
        from src.io_.briefing_store import find_latest_briefing
        briefings_dir = tmp_path / "briefings"
        briefings_dir.mkdir()

        only_file = briefings_dir / "2026-05-01.json"
        only_file.write_text(json.dumps(_make_briefing("2026-05-01T09:00:00+00:00")))

        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            result = find_latest_briefing()

        assert result == only_file

    def test_falls_back_to_filename_sort_on_unreadable_file(self, tmp_path):
        """Unreadable files fall back to filename sort (treated as empty string ts)."""
        from src.io_.briefing_store import find_latest_briefing
        briefings_dir = tmp_path / "briefings"
        briefings_dir.mkdir()

        # Good file with a real timestamp
        good = briefings_dir / "2026-05-02.json"
        good.write_text(json.dumps(_make_briefing("2026-05-02T09:00:00+00:00")))

        # Corrupt file — JSON parse fails → ts = "" → sorts lower
        bad = briefings_dir / "2026-05-03.json"
        bad.write_text("NOT VALID JSON {{{")

        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            result = find_latest_briefing()

        # good has a real timestamp; bad has "" which sorts lower than any real ts.
        # So good wins on ts; bad wins on name. Tie-break: ("", "2026-05-03.json")
        # vs ("2026-05-02T09:00:00+00:00", "2026-05-02.json").
        # "2026-05-02T..." > "" so good wins.
        assert result == good


# ---------------------------------------------------------------------------
# load_briefing()
# ---------------------------------------------------------------------------

class TestLoadBriefing:

    def test_parses_json_correctly(self, tmp_path):
        """load_briefing() returns parsed dict from a JSON file."""
        from src.io_.briefing_store import load_briefing
        data = _make_briefing("2026-05-01T08:00:00+00:00", items=[{"rxcui": "123"}])
        path = tmp_path / "2026-05-01.json"
        path.write_text(json.dumps(data))

        result = load_briefing(path)

        assert result["run_timestamp"] == "2026-05-01T08:00:00+00:00"
        assert result["items"] == [{"rxcui": "123"}]

    def test_raises_on_invalid_json(self, tmp_path):
        """load_briefing() propagates JSONDecodeError on corrupt files."""
        from src.io_.briefing_store import load_briefing
        bad = tmp_path / "bad.json"
        bad.write_text("not json")

        with pytest.raises(json.JSONDecodeError):
            load_briefing(bad)

    def test_raises_on_missing_file(self, tmp_path):
        """load_briefing() propagates OSError when file does not exist."""
        from src.io_.briefing_store import load_briefing
        missing = tmp_path / "missing.json"

        with pytest.raises(OSError):
            load_briefing(missing)


# ---------------------------------------------------------------------------
# write_briefing()
# ---------------------------------------------------------------------------

class TestWriteBriefing:

    def test_writes_correct_json(self, tmp_path):
        """write_briefing() produces a valid JSON file with the run contents."""
        from src.io_.briefing_store import write_briefing
        briefings_dir = tmp_path / "briefings"

        run = _make_briefing("2026-05-01T08:00:00+00:00")
        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            out_path = write_briefing(run, "2026-05-01")

        assert out_path.exists()
        loaded = json.loads(out_path.read_text())
        assert loaded["run_timestamp"] == "2026-05-01T08:00:00+00:00"

    def test_creates_briefings_dir_if_missing(self, tmp_path):
        """write_briefing() creates BRIEFINGS_DIR if it does not exist."""
        from src.io_.briefing_store import write_briefing
        briefings_dir = tmp_path / "briefings"
        assert not briefings_dir.exists()

        run = _make_briefing("2026-05-01T08:00:00+00:00")
        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            write_briefing(run, "2026-05-01")

        assert briefings_dir.exists()

    def test_atomic_write_no_tmp_file_after_success(self, tmp_path):
        """After a successful write, the .tmp file is gone (rename was atomic)."""
        from src.io_.briefing_store import write_briefing
        briefings_dir = tmp_path / "briefings"

        run = _make_briefing("2026-05-01T08:00:00+00:00")
        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            out_path = write_briefing(run, "2026-05-01")

        tmp_path_check = out_path.with_suffix(".json.tmp")
        assert not tmp_path_check.exists(), ".tmp file must not remain after successful write"

    def test_returns_correct_path(self, tmp_path):
        """write_briefing() returns the final .json path, not the .tmp path."""
        from src.io_.briefing_store import write_briefing
        briefings_dir = tmp_path / "briefings"

        run = _make_briefing("2026-05-01T08:00:00+00:00")
        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            out_path = write_briefing(run, "2026-05-01")

        assert out_path.suffix == ".json"
        assert out_path.name == "2026-05-01.json"

    def test_overwrites_existing_file(self, tmp_path):
        """write_briefing() replaces an existing briefing file."""
        from src.io_.briefing_store import write_briefing
        briefings_dir = tmp_path / "briefings"
        briefings_dir.mkdir()

        existing = briefings_dir / "2026-05-01.json"
        existing.write_text(json.dumps({"old": True}))

        run = _make_briefing("2026-05-01T12:00:00+00:00")
        with patch("src.io_.briefing_store.BRIEFINGS_DIR", briefings_dir):
            write_briefing(run, "2026-05-01")

        loaded = json.loads(existing.read_text())
        assert "old" not in loaded
        assert loaded["run_timestamp"] == "2026-05-01T12:00:00+00:00"
