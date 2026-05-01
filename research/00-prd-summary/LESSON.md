# PRD Summary — One Page

## What we're building

**Rx Shortage Intelligence**: AI-assisted morning briefing for hospital pharmacy directors. Cross-references live FDA drug shortages against a hospital's formulary + active orders. Classifies severity (Critical / Watch / Resolved). Recommends therapeutic alternatives with citations. Surfaces only what affects *this* hospital, not the universe.

Replaces a ~20-min manual workflow per drug across 4-5 fragmented sources (FDA shortage list, ASHP, formulary spreadsheet, two drug references).

## Who uses it

| Role | What they do | Trust requirement |
|------|--------------|-------------------|
| Pharmacy Director (buyer) | Owns inventory, P&T, shortage response | Decision-making confidence; no black box |
| Clinical Pharmacist (daily user) | Order verification, alt recommendations, prescriber calls | Will not act without citation |

## The core insight

Customers don't want more data. They want **proactive surfacing replacing self-directed querying**. User opens dashboard → briefing already there → scans → drills down on highest-severity item → accepts or overrides → done in <5 min.

**Speed = clinical safety feature**, not UX preference. 7 AM, active shortage, nurse on phone — no time for "I have to know how to navigate it."

## Non-negotiable principles (PRD §5)

1. Proactive over reactive
2. Speed = safety
3. Intuitive on day one (no training)
4. Customer-relevance over universal content
5. Citation-first trust (every claim → source)
6. Human-in-the-loop always (agent never auto-acts)
7. Honest scope (synthetic data labeled synthetic)

## Functional requirements (PRD §9.1)

| FR | One-liner |
|----|-----------|
| FR-1 | Daily briefing: ingest FDA + formulary + orders → diff → output by severity |
| FR-2 | Severity classify: Critical / Watch / Resolved + rationale |
| FR-3 | Therapeutic alternatives ranked by clinical equivalence + formulary status |
| FR-4 | Every claim cited; sources clickable |
| FR-5 | Drill-down agent traces (tool calls, reasoning, classification logic) |
| FR-6 | HITL: confidence scores, accept/override/escalate |
| FR-7 | Eval harness: 15 cases, 5 dims, v1 vs v2 |
| FR-8 | Day-one usable: <5 min first triage, no training |
| FR-9 | Speed: dashboard <2s, citation <1s, rerun <30s |
| FR-10 | Power-user density: scan, don't read |
| FR-11 | Visual scan order: top stats → severity-ordered items → expandable detail |

## NFRs (PRD §9.3)

- Latency <60 sec end-to-end
- Cost <$0.05/briefing
- Reliability: graceful API failure handling
- Auditability: every action logged with timestamp + tool + params + reasoning
- Honest scoping

## Out of scope for v0.1 (PRD §9.4)

Background scheduler, push notifications, real customer formulary, EHR/CDS Hooks, multi-tenancy, auth, drug pricing, prior auth, real inventory data.

## Architecture (PRD §12.2)

```
Streamlit UI
    ↓
Agent orchestrator (Claude + tool-use loop + RAG)
    ↓
3 MCP servers ──→ FDA Shortage / openFDA Labels / RxNorm APIs
    +
RAG index over openFDA label chunks
```

## Why this lecture matters

PRD has 22 pages. During the build you have 6 hours. This one-pager is what you re-read when you forget *why*. Every implementation choice traces back to one of: 7 principles, 11 FRs, 5 NFRs.
