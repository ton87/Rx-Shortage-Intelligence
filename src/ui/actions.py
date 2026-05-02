"""HITL action logging. Atomic read-modify-write of user actions on briefing JSON."""

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.io_.briefing_store import atomic_write_json, load_briefing


def log_action(briefing_path: Path, item_id: str, action: str, reason: str | None = None) -> bool:
    """Stamp user action onto matching item in the briefing JSON.

    Returns True if the item_id matched and the write succeeded. Returns False
    on a stale item_id (briefing regenerated since render — all uuids change),
    corrupt JSON, or any IO error during read/write.
    """
    try:
        run = load_briefing(briefing_path)
    except (OSError, json.JSONDecodeError) as e:
        st.error(f"Could not read briefing: {e}. Try Re-run briefing.")
        return False

    matched = False
    for item in run.get("items", []) or []:
        if item.get("item_id") == item_id:
            item["user_action"] = action
            item["user_action_timestamp"] = datetime.now(timezone.utc).isoformat()
            if reason:
                item["user_action_reason"] = reason
            matched = True
            break

    if not matched:
        st.warning("Action not recorded — briefing was regenerated. Refresh and try again.")
        return False

    try:
        atomic_write_json(briefing_path, run)
        return True
    except OSError as e:
        st.error(f"Could not save action: {e}")
        return False
