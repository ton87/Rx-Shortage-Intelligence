"""HITL action logging. Atomic read-modify-write of user actions on briefing JSON."""

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.io_.briefing_store import load_briefing


def log_action(briefing_path: Path, item_id: str, action: str, reason: str | None = None) -> bool:
    """Atomic read-modify-write of action on briefing JSON.

    Returns True if item_id matched and write succeeded. False on stale item_id
    (briefing regenerated since render — all uuids new), corrupt JSON, or IO error.
    Atomic write via tmp + rename so concurrent re-run can't see half-written file.
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

    tmp_path = briefing_path.with_suffix(briefing_path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(run, indent=2))
        tmp_path.replace(briefing_path)
        return True
    except OSError as e:
        st.error(f"Could not save action: {e}")
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
