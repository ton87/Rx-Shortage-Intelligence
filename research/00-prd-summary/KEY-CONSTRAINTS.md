# Key Constraints — What v0.1 Must Hit and Cannot Drop

## Hard constraints (cutting these = failing PRD)

| Constraint | Source | Test |
|------------|--------|------|
| Real public APIs (FDA, openFDA, RxNorm) | §11.2 | Tool calls hit live URLs |
| Anthropic Claude (claude-sonnet-4-6) | §12.1 | Model ID in code |
| 3 MCP servers in Python | §12.3 | `ls src/servers/*.py` shows 3 |
| Citation on every claim | Principle 5, FR-4 | Eval: 100% citation accuracy |
| HITL accept/override on every item | Principle 6, FR-6 | UI buttons present |
| Synthetic data labeled synthetic | Principle 7, NFR-5 | UI banner says "Synthetic formulary" |
| Cost <$0.05/briefing | NFR-2 | Token math + Anthropic usage report |
| Latency <60 sec | NFR-1 | Wall-clock measurement |
| Audit log per action | NFR-4 | BriefingRun JSON has tool_calls[] |

## Soft constraints (would be nice, drop if behind)

| Constraint | Drop strategy |
|------------|---------------|
| 30-drug formulary | Cut to 5-10, label as "demo subset" |
| 15 eval cases | Cut to 5, hardcode v2 |
| Drill-down agent trace | Show citations only |
| Resolved severity bucket | Skip; only Critical/Watch |
| RAG over labels | Pass full label as text |
| `rxnorm_server` (3rd MCP) | Fold into label server |

## Scope cuts already made (PRD §9.4)

These are *deliberately* deferred. Don't accidentally build:

- Background scheduler
- Push notifications
- Real customer formulary integration
- EHR/CDS Hooks
- Multi-tenancy / auth
- Drug pricing
- Prior auth
- Real inventory data

If during the build you find yourself touching any of these — stop. They're v0.2+.

## Anti-patterns (PRD §10.4)

Documented competitor failures we explicitly invert:

- Multi-tab hierarchies → single-screen scannable dashboard
- Search-first → briefing-first (no search needed)
- Show-everything → show-only-what-affects-this-hospital
- Feature-first nav → outcome-first surface
- Modal stacks → inline expansion (max 1 click to source)
- Conversational chatbot → structured briefing (scan, don't type)

## What "done" looks like

A pharmacist opens `streamlit run src/main.py`, sees a pre-rendered briefing, identifies the most critical item in <30 sec, drills down to see the agent's reasoning + citations, accepts or overrides, and closes — all without reading documentation. Eval tab shows 15 cases scored across 5 dims with <2% hallucination rate.

## What "shipped but flawed" looks like (acceptable)

- 5 demo drugs instead of 30
- 5 eval cases instead of 15
- One MCP server instead of 3 (folded)
- Eval tab shows mocked v2 placeholder
- No drill-down trace; citations only

## What "not done" looks like (unacceptable)

- No live API calls (all synthetic)
- No citations
- No HITL controls
- Model ID wrong
- Synthetic data not labeled
- Crashes on first run
