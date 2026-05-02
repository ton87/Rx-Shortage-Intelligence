"""Briefing persistence layer.

Handles finding, loading, and atomically writing briefing JSON files.
No Streamlit imports — stays pure I/O.
"""

import json
from pathlib import Path

# Paths computed relative to this file:
#   src/io_/briefing_store.py → parent.parent.parent = repo root
DATA_DIR = Path(__file__).parent.parent.parent / "data"
BRIEFINGS_DIR = DATA_DIR / "briefings"


def find_latest_briefing() -> Path | None:
    """Pick newest briefing by embedded run_timestamp, not filename.

    Filename uses UTC date; run_timestamp is authoritative. Prevents picking
    a stale 'tomorrow-named' file over a real newer run. Falls back to
    filename sort if a file is unreadable.

    Returns None if the briefings directory does not exist or is empty.
    """
    if not BRIEFINGS_DIR.exists():
        return None
    files = list(BRIEFINGS_DIR.glob("*.json"))
    if not files:
        return None

    def _ts(p: Path) -> str:
        try:
            return json.loads(p.read_text()).get("run_timestamp", "") or ""
        except (OSError, json.JSONDecodeError):
            return ""

    return max(files, key=lambda p: (_ts(p), p.name))


def load_briefing(path: Path) -> dict:
    """Parse a briefing JSON file and return the run dict."""
    return json.loads(path.read_text())


def write_briefing(run: dict, date_str: str) -> Path:
    """Atomically write a briefing run dict to data/briefings/<date_str>.json.

    Uses tmp + rename so a concurrent reader never sees a half-written file.
    Returns the final path.
    """
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEFINGS_DIR / f"{date_str}.json"
    tmp_path = out_path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(run, indent=2))
        tmp_path.replace(out_path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
    return out_path
