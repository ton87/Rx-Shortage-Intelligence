---
name: execute-ticket
description: Per-ticket pipeline enforcer. Orchestrator invokes this with a ticket ID. Each step must complete before proceeding. Sequential, direct-to-main, no PR step.
---

# Execute Ticket

Mandatory pipeline for executing a single Rx Shortage Intelligence ticket. Sequential per-ticket, no batching, direct-to-main.

## Usage

`/execute-ticket T-NNN` — orchestrator agent invokes this for every ticket pulled from ISSUES.md.

## Pipeline steps

### Step 1 — Validate ticket (architect)
Spawn `architect` with the ticket ID. Expect `verdict: PASS` or `verdict: BLOCK`.
- BLOCK → STOP, surface reasons to user.
- PASS → move ticket in ISSUES.md from Backlog to In Progress.

Log:
```
| <ts> | T-NNN | architect | completed | PASS — <one-line> |
```

### Step 2 — Research brief (researcher)
Spawn `researcher` with ticket ID and H-block. Receive 60-line brief. Pass it forward verbatim to test-engineer and backend-dev.

Log architect-style entry.

### Step 3 — Contract tests (test-engineer pass 1)
Spawn `test-engineer` with ticket + research brief. Pass parameter `pass: 1-contract`. Expect tests written and RED.

Log entry includes test paths.

### Step 4 — Implementation (backend-dev)
Spawn `backend-dev` with ticket + research brief + contract test paths. Backend-dev reads failing tests, implements until green.

On return, verify backend-dev's `contract_tests_status: green`. If red, treat as failure, respawn with the failing test list.

Log entry includes files modified + final contract status.

### Step 5 — Adversarial tests (test-engineer pass 2)
Fresh-spawn `test-engineer` (do not SendMessage to the pass-1 instance — drops silently). Pass parameter `pass: 2-adversarial`. Expect positive + negative + ambient/degraded coverage.

If any RED: list failing tests, respawn `backend-dev` with the failing test list, return to step 5 after.

Log entry per category counts.

### Step 6 — Mechanical gate (integration)
Spawn `integration`. Run all 9 deterministic checks. Capture verdict.
- FAIL on any hard check → respawn backend-dev with the failing checks.
- FAIL_SOFT (cost only) → continue to reviewer with note.
- PASS → continue.

Log full check matrix.

### Step 7 — Adversarial review (reviewer)
Spawn `reviewer`. Reviewer reads diff + dispatch log + research lessons.
- BLOCK → respawn architect (scope) or backend-dev (impl) per finding dimension. Return to step 5 or 6 as required.
- FLAG → orchestrator decides: fix-now (back to step 4) or file new ticket and continue.
- PASS → continue to commit.

Log reviewer verdict + finding count.

### Step 8 — Commit (orchestrator only)
Orchestrator (not any sub-agent) commits:
- Stage explicit file paths only — never `git add .` or `git add -A`.
- One concern per commit (split if ticket produced multiple concerns).
- Message: `<type>(H<N>): <verb> <subject>`.
- Footer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Direct to main. No branch, no PR.

Log:
```
| <ts> | T-NNN | orchestrator | committed | <short-hash> |
```

### Step 9 — Update ISSUES.md
Move ticket from In Progress to Done. Append commit short-hash and date.

Log:
```
| <ts> | T-NNN | orchestrator | done | <short-hash> |
```

### Step 10 — Checkpoint
Before next ticket:
- [ ] dispatch log has entries for steps 1–9 of THIS ticket
- [ ] ISSUES.md shows ticket = Done
- [ ] `git status` clean
- [ ] On main branch
- [ ] No FAIL_SOFT items un-surfaced to user

Any failure → STOP, do not pull next ticket.

## Halts (mandatory user-stop)

- Reviewer BLOCK twice on same ticket → STOP, ask user.
- Hard constraint at risk (cost ceiling exceeded, citation < 100%, hallucination > 2%) → STOP.
- Out-of-scope work being requested → STOP.
- Architect cannot resolve scope from existing artifacts → STOP.
- Any destructive git op needed (force push, branch delete, rebase) → STOP.

## Anti-patterns this skill prevents

1. "I'll batch the eval run across tickets" — No. Per-ticket.
2. "Reviewer found minor issue, I'll fix and skip re-review" — No. Re-run reviewer after every backend-dev revision.
3. "Test-engineer pass 2 can be lighter for a small ticket" — No. All three categories required, every ticket.
4. "Integration's FAIL_SOFT is fine to hide" — No. Every FAIL_SOFT goes into the user-visible eval tab.
5. "Use `git add -A` to grab all the test files at once" — No. Stage by path, even when many files.
6. "Pass-1 contract test was wrong, rewrite it in pass 2" — No. Pass 1 is the contract. If wrong, file new ticket.
7. "Skip researcher for trivial tickets" — No. 60-line brief is cheap insurance against gotcha re-discovery.
