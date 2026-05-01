"""
Rx Shortage Intelligence — Streamlit dashboard.

Pattern B: 100% sync. Reads data/briefings/YYYY-MM-DD.json.
Re-run button spawns CLI subprocess, then reloads.

Run: streamlit run src/main.py
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ── Config ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DATA_DIR = Path(__file__).parent.parent / "data"
BRIEFINGS_DIR = DATA_DIR / "briefings"

SEVERITY_COLOR = {"Critical": "🔴", "Watch": "🟡", "Resolved": "🟢"}
CONFIDENCE_COLOR = {"high": "🟢", "medium": "🟡", "low": "🔴"}
SORT_ORDER = {"Critical": 0, "Watch": 1, "Resolved": 2}

# ── Data loading ─────────────────────────────────────────────────────────────

def find_latest_briefing() -> Path | None:
    """Return path to the most recent briefing JSON, or None."""
    if not BRIEFINGS_DIR.exists():
        return None
    files = sorted(BRIEFINGS_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None


def load_briefing(path: Path) -> dict:
    return json.loads(path.read_text())

# ── HITL action logging ──────────────────────────────────────────────────────

def log_action(briefing_path: Path, item_id: str, action: str) -> None:
    """Record accept/override/escalate to the briefing JSON in-place."""
    run = json.loads(briefing_path.read_text())
    for item in run["items"]:
        if item["item_id"] == item_id:
            item["user_action"] = action
            item["user_action_timestamp"] = datetime.now(timezone.utc).isoformat()
            break
    briefing_path.write_text(json.dumps(run, indent=2))

# ── Re-run ───────────────────────────────────────────────────────────────────

def run_briefing_cli() -> tuple[bool, str]:
    """Invoke `python -m src.briefing` as a subprocess. Returns (success, message)."""
    result = subprocess.run(
        [sys.executable, "-m", "src.briefing"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0:
        return True, result.stdout.strip() or "Briefing complete."
    return False, result.stderr.strip() or "Briefing failed (unknown error)."

# ── Rendering helpers ────────────────────────────────────────────────────────

def render_item(item: dict, briefing_path: Path) -> None:
    """Render one BriefingItem with inline expand for drill-down."""
    severity = item.get("severity", "Watch")
    icon = SEVERITY_COLOR.get(severity, "⚪")
    confidence = item.get("confidence", "low")
    conf_icon = CONFIDENCE_COLOR.get(confidence, "⚪")
    action_taken = item.get("user_action")

    with st.container(border=True):
        col_a, col_b = st.columns([5, 1])
        with col_a:
            st.markdown(f"{icon} **{severity.upper()}** — {item.get('drug_name', 'Unknown')}")
            st.write(item.get("summary", ""))
            st.caption(f"→ {item.get('recommended_action', '')}")
        with col_b:
            st.markdown(f"{conf_icon} `{confidence}`")
            if action_taken:
                st.success(f"✓ {action_taken}", icon=None)

        with st.expander("Agent reasoning + citations"):
            st.markdown("**Rationale**")
            st.write(item.get("rationale", ""))

            alts = item.get("alternatives", [])
            if alts:
                st.markdown("**Therapeutic alternatives**")
                for alt in alts:
                    conf_badge = CONFIDENCE_COLOR.get(alt.get("confidence", "low"), "⚪")
                    st.markdown(
                        f"- **{alt.get('name', '')}** (RxCUI `{alt.get('rxcui', '')}`) "
                        f"{conf_badge} `{alt.get('confidence', '')}` — {alt.get('rationale', '')}"
                    )
            else:
                st.info("No therapeutic alternatives identified.")

            cites = item.get("citations", [])
            if cites:
                st.markdown("**Citations**")
                for c in cites:
                    url = c.get("url") or c.get("source_url", "")
                    claim = c.get("claim", "")
                    if url:
                        st.markdown(f"- {claim} — [source]({url})")
                    else:
                        st.markdown(f"- {claim}")

            tool_calls = item.get("tool_call_log", [])
            if tool_calls:
                with st.expander(f"Tool call trace ({len(tool_calls)} calls)"):
                    for tc in tool_calls:
                        st.code(
                            f"{tc.get('tool', '')}({json.dumps(tc.get('args', {}))[:120]})\n"
                            f"→ {str(tc.get('result_preview', ''))[:200]}",
                            language="text",
                        )

            if not action_taken:
                b1, b2, b3 = st.columns(3)
                item_id = item.get("item_id", "")
                if b1.button("✓ Accept", key=f"accept-{item_id}", use_container_width=True):
                    log_action(briefing_path, item_id, "accept")
                    st.rerun()
                if b2.button("✎ Override", key=f"override-{item_id}", use_container_width=True):
                    log_action(briefing_path, item_id, "override")
                    st.rerun()
                if b3.button("⚠ Escalate", key=f"escalate-{item_id}", use_container_width=True):
                    log_action(briefing_path, item_id, "escalate")
                    st.rerun()

# ── Main layout ──────────────────────────────────────────────────────────────

def main():
    # Header
    hcol1, hcol2 = st.columns([4, 1])
    hcol1.title("💊 Rx Shortage Intelligence")
    rerun_clicked = hcol2.button("🔄 Re-run briefing", use_container_width=True)

    # Synthetic data banner (always visible — PRD Principle 7)
    st.warning(
        "⚠️ **SYNTHETIC DATA** — Formulary and active orders are synthetic for v0.1 demo. "
        "FDA shortage feed and RxNorm are live public data.",
        icon=None,
    )

    # Re-run handling
    if rerun_clicked:
        with st.spinner("Running briefing… this takes 30–60s"):
            ok, msg = run_briefing_cli()
        if ok:
            st.success(msg)
        else:
            st.error(f"Briefing failed: {msg}")
        st.rerun()

    # Load briefing
    path = find_latest_briefing()

    if path is None:
        st.info(
            "No briefing found. Click **Re-run briefing** to generate one. "
            "First run takes 30–60 seconds and hits live FDA/RxNorm APIs."
        )
        return

    run = load_briefing(path)
    items = run.get("items", [])

    # Stats bar
    counts = {"Critical": 0, "Watch": 0, "Resolved": 0}
    for it in items:
        counts[it.get("severity", "Watch")] += 1

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("🔴 Critical", counts["Critical"])
    s2.metric("🟡 Watch", counts["Watch"])
    s3.metric("🟢 Resolved", counts["Resolved"])
    s4.metric("Latency", f"{run.get('latency_ms', 0) // 1000}s")
    s5.metric("Tokens used", run.get("total_tokens_used", 0))

    st.caption(
        f"Last run: {run.get('run_timestamp', 'unknown')} · "
        f"{run.get('items_reviewed', 0)} drugs reviewed · "
        f"{run.get('items_surfaced', 0)} items surfaced · "
        f"Customer: {run.get('customer_id', '')}"
    )

    if not items:
        st.info("Briefing ran but produced no items. All formulary drugs may be unaffected today.")
        return

    st.divider()

    # Severity-ordered items
    sorted_items = sorted(items, key=lambda x: SORT_ORDER.get(x.get("severity", "Watch"), 1))
    for item in sorted_items:
        render_item(item, path)


if __name__ == "__main__":
    main()
