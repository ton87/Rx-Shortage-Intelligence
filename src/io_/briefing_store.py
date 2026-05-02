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
    """Pick newest briefing by file mtime — set atomically by write_briefing's
    tmp+rename, so it tracks actual write time rather than the date encoded
    in the filename. Filename used as tiebreaker.

    Returns None if the briefings directory does not exist or is empty.
    """
    if not BRIEFINGS_DIR.exists():
        return None
    files = list(BRIEFINGS_DIR.glob("*.json"))
    if not files:
        return None
    return max(files, key=lambda p: (p.stat().st_mtime, p.name))


def load_briefing(path: Path) -> dict:
    """Parse a briefing JSON file and return the run dict."""
    return json.loads(path.read_text())


def atomic_write_json(path: Path, data: dict) -> None:
    """Write data as JSON to path via tmp + rename so readers never see a partial file."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def write_briefing(run: dict, date_str: str) -> Path:
    """Write a briefing run dict to data/briefings/<date_str>.json. Returns the final path."""
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEFINGS_DIR / f"{date_str}.json"
    atomic_write_json(out_path, run)
    return out_path
