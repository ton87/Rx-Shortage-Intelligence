"""Project-wide tunable constants. Values mirror the v0.1 PRD/CLAUDE.md budget."""

# Briefing pipeline
DEFAULT_CANDIDATE_CAP = 5          # Max drugs surfaced per briefing (latency budget)
FDA_FETCH_LIMIT = 1000             # Max records pulled from FDA shortage feed per call
PER_DRUG_TIMEOUT_S = 90            # Per-drug agent classification timeout
BRIEFING_SUBPROCESS_TIMEOUT_S = 600  # Re-run subprocess wall clock cap

# Re-run lock (prevent concurrent CLI invocations from UI)
LOCK_PATH = "/tmp/rx_briefing.lock"
LOCK_STALE_S = 900                 # 15-min — anything older is stale, can be cleared

# Agent
AGENT_MODEL = "claude-sonnet-4-6"
AGENT_MAX_ITERATIONS = 8
AGENT_MAX_TOKENS = 4096

# Customer (single-tenant v0.1)
CUSTOMER_ID = "memorial-health-450"
PROMPT_VERSION = "v1"
SYNTHETIC_LABEL = "SYNTHETIC — v0.1 demo"
