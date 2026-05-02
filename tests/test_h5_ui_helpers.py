"""Tests for UI helper functions (pure logic, no Streamlit rendering)."""

import json
import sys
import unittest.mock as mock
from datetime import datetime, timezone
from pathlib import Path

import pytest

# log_action uses st.error/st.warning — stub streamlit before that import
sys.modules.setdefault("streamlit", mock.MagicMock())

from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.domain.severity import SEVERITY_RANK
from src.ui.actions import log_action


# ── find_latest_briefing ─────────────────────────────────────────────────────

def test_find_latest_briefing_returns_none_when_no_dir(tmp_path, monkeypatch):
    """Returns None when the briefings directory doesn't exist."""
    missing = tmp_path / "briefings"
    monkeypatch.setattr("src.io_.briefing_store.BRIEFINGS_DIR", missing)
    assert find_latest_briefing() is None


def test_find_latest_briefing_returns_most_recent(tmp_path, monkeypatch):
    """Returns the lexicographically latest .json file."""
    monkeypatch.setattr("src.io_.briefing_store.BRIEFINGS_DIR", tmp_path)
    older = tmp_path / "2026-04-30.json"
    newer = tmp_path / "2026-05-01.json"
    older.write_text("{}")
    newer.write_text("{}")
    result = find_latest_briefing()
    assert result == newer


def test_find_latest_briefing_ignores_non_json_files(tmp_path, monkeypatch):
    """Only .json files are considered; .txt files are ignored."""
    monkeypatch.setattr("src.io_.briefing_store.BRIEFINGS_DIR", tmp_path)
    txt_file = tmp_path / "2026-05-02.txt"
    json_file = tmp_path / "2026-04-15.json"
    txt_file.write_text("not json")
    json_file.write_text("{}")
    result = find_latest_briefing()
    assert result == json_file


# ── load_briefing ────────────────────────────────────────────────────────────

def test_load_briefing_parses_json(tmp_path):
    """load_briefing correctly deserialises a JSON file."""
    payload = {"run_id": "test-001", "items": [{"item_id": "x"}]}
    p = tmp_path / "2026-05-01.json"
    p.write_text(json.dumps(payload))
    result = load_briefing(p)
    assert result["run_id"] == "test-001"
    assert len(result["items"]) == 1


# ── log_action ───────────────────────────────────────────────────────────────

def _make_briefing_file(tmp_path: Path, item_id: str = "item-001") -> Path:
    run = {
        "run_id": "test-run",
        "items": [
            {"item_id": item_id, "drug_name": "Cisplatin", "user_action": None}
        ],
    }
    p = tmp_path / "2026-05-01.json"
    p.write_text(json.dumps(run))
    return p


def test_log_action_sets_user_action(tmp_path):
    """log_action writes the action string to the item."""
    p = _make_briefing_file(tmp_path, "item-001")
    log_action(p, "item-001", "accept")
    run = json.loads(p.read_text())
    assert run["items"][0]["user_action"] == "accept"


def test_log_action_sets_timestamp(tmp_path):
    """log_action writes a UTC ISO-8601 timestamp."""
    p = _make_briefing_file(tmp_path, "item-002")
    before = datetime.now(timezone.utc)
    log_action(p, "item-002", "escalate")
    after = datetime.now(timezone.utc)

    run = json.loads(p.read_text())
    ts_str = run["items"][0]["user_action_timestamp"]
    assert ts_str is not None

    # Parse and verify it falls within the test window
    ts = datetime.fromisoformat(ts_str)
    # Normalise to UTC if offset-aware but not UTC-named
    ts_utc = ts.astimezone(timezone.utc)
    assert before <= ts_utc <= after


# ── SEVERITY_RANK ─────────────────────────────────────────────────────────────

def test_severity_rank_critical_before_watch_before_resolved():
    """Critical < Watch < Resolved in sort order."""
    items = [
        {"severity": "Resolved"},
        {"severity": "Critical"},
        {"severity": "Watch"},
    ]
    sorted_items = sorted(items, key=lambda x: SEVERITY_RANK.get(x.get("severity", "Watch"), 1))
    assert [i["severity"] for i in sorted_items] == ["Critical", "Watch", "Resolved"]
