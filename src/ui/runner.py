"""Briefing subprocess runner and lock helpers.

Prevents concurrent CLI invocations from the UI. Lock file at LOCK_PATH;
stale locks older than LOCK_STALE_S or with dead PIDs are auto-cleared.
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.domain.constants import LOCK_PATH, LOCK_STALE_S, BRIEFING_SUBPROCESS_TIMEOUT_S
from src.io_.briefing_store import BRIEFINGS_DIR

BRIEFING_LOCK_PATH = Path(LOCK_PATH)
BRIEFING_LOCK_STALE_SECONDS = LOCK_STALE_S
BRIEFING_LOGS_DIR = BRIEFINGS_DIR / "logs"


def _briefing_lock_held() -> tuple[bool, str | None]:
    """Return (is_held, holder_pid_str). Stale locks (>15min, dead pid) cleared."""
    if not BRIEFING_LOCK_PATH.exists():
        return False, None
    try:
        content = BRIEFING_LOCK_PATH.read_text().strip()
        pid_str, ts_str = content.split(":", 1)
        ts = float(ts_str)
        age = datetime.now(timezone.utc).timestamp() - ts
        if age > BRIEFING_LOCK_STALE_SECONDS:
            BRIEFING_LOCK_PATH.unlink(missing_ok=True)
            return False, None
        # Check pid is alive (best-effort, posix only)
        try:
            import os
            os.kill(int(pid_str), 0)
        except (ProcessLookupError, ValueError):
            BRIEFING_LOCK_PATH.unlink(missing_ok=True)
            return False, None
        except PermissionError:
            pass  # process exists, owned by different user
        return True, pid_str
    except (OSError, ValueError):
        BRIEFING_LOCK_PATH.unlink(missing_ok=True)
        return False, None


def _acquire_briefing_lock() -> bool:
    held, _ = _briefing_lock_held()
    if held:
        return False
    try:
        import os
        BRIEFING_LOCK_PATH.write_text(
            f"{os.getpid()}:{datetime.now(timezone.utc).timestamp()}"
        )
        return True
    except OSError:
        return False


def _release_briefing_lock() -> None:
    try:
        BRIEFING_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _new_log_path() -> Path:
    BRIEFING_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    # Local time so file names match what user sees in `ls`
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return BRIEFING_LOGS_DIR / f"briefing-{ts}.log"


def run_briefing_cli() -> tuple[bool, str, Path | None]:
    """Spawn briefing subprocess. Output inherits parent stdout/stderr so logs
    appear in the terminal running `streamlit run` (not the browser UI).

    Returns (success, summary_message, log_file_path).
    Mirror copy written to data/briefings/logs/briefing-<ts>.log via tee.
    """
    if not _acquire_briefing_lock():
        _, holder = _briefing_lock_held()
        return False, (
            f"Another briefing is already running (pid={holder or 'unknown'}). "
            "Wait for it to finish or close other browser tabs."
        ), None

    log_path = _new_log_path()

    # Tee subprocess output: parent stdout/stderr (terminal) AND log file.
    # Use shell pipe with `tee` so streamlit container shows logs live + file persists.
    cmd = (
        f"{sys.executable} -u -m src.briefing 2>&1 | tee {log_path}"
    )

    try:
        proc = subprocess.run(
            cmd, shell=True, timeout=BRIEFING_SUBPROCESS_TIMEOUT_S,
            stdout=None, stderr=None,  # inherit terminal
        )
    except subprocess.TimeoutExpired:
        _release_briefing_lock()
        return False, "Briefing exceeded 10-minute timeout. Check terminal logs.", log_path
    finally:
        _release_briefing_lock()

    if proc.returncode == 0:
        return True, f"Briefing complete. Log: {log_path.name}", log_path
    return False, (
        f"Briefing failed (exit {proc.returncode}). See terminal running streamlit "
        f"or {log_path} for full output."
    ), log_path


def run_briefing_with_status() -> bool:
    """Run briefing CLI. Logs appear in the terminal running streamlit, not the UI.

    UI shows a single status spinner + final success/failure message with log path.
    Full transcript persisted to data/briefings/logs/briefing-<ts>.log for review.
    """
    with st.status("Running briefing…", expanded=False) as status:
        ok, _msg, log_path = run_briefing_cli()
        if log_path:
            st.session_state["last_briefing_log"] = str(log_path)
        if ok:
            status.update(label="Briefing complete.", state="complete")
            return True
        status.update(label="Briefing failed.", state="error")
        return False
