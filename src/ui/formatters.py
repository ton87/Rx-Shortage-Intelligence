"""Display-only formatters. No streamlit imports — pure str → str."""

from datetime import datetime


def format_timestamp(iso: str) -> str:
    """Render ISO timestamp in user's local timezone with tz abbreviation."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%b %d, %Y · %H:%M %Z").strip()
    except (ValueError, TypeError):
        return iso


def format_int_or_dash(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "—"
    return "—" if n == 0 else f"{n:,}"


def format_latency_or_dash(latency_ms) -> str:
    try:
        ms = int(latency_ms)
    except (TypeError, ValueError):
        return "—"
    if ms == 0:
        return "—"
    return f"{ms // 1000}s" if ms >= 1000 else f"{ms} ms"
