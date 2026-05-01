# Briefing Diff — References

## PRD anchors

- §11.1 BriefingRun + BriefingItem schemas
- FR-1: ingest + diff + structured output by severity
- FR-2: severity classification (Critical/Watch/Resolved)
- §13.1: confidence-based routing
- §10.3: visual severity (green/amber/red)

## FDA shortage status enum

Verified values from openFDA shortages records (2026-05-01 via `count=status`):
- `Current` — 1140 records (active shortage)
- `To Be Discontinued` — 498 records (drug being phased out)
- `Resolved` — 29 records (no longer in shortage)

v0.1 filters to `status:Current`. TBD handling = open question (see QUESTIONS-FOR-ANTON.md Q1). Earlier POC used `"Currently in Shortage"` — string never existed in API.

## Internal POCs

- `POC-diff-logic.py` — full diff with bucket semantics
- `POC-severity-classifier.py` — rule-based + ceiling

## Related

- Data shapes: `research/01-data-layer/LESSON.md`
- Agent loop integration: `research/03-agent-loop/LESSON.md`
- UI rendering: `research/05-streamlit-ui/LESSON.md`
