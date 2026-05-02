# UI Context — distilled from PRD §10 + §5 + §9

## Audience
- **Primary**: Karen Chen, PharmD MBA, Director of Pharmacy (450-bed system). Buyer.
- **Daily user**: Marcus Patel, PharmD, Clinical Pharmacist. Triages briefing in <5 min, no training.
- **Stakeholders**: P&T Committee, prescribers (downstream), pharmacy purchasing, informaticists, health system leadership.
- **Tools they live in today**: Cerner/Epic EHR, ASHP shortage list, formulary spreadsheets, legacy drug references (UpToDate / Lexicomp / Micromedex).
- **Quietly tired of**: tools that are slow, require training, show data but don't drive action.

## Visual aesthetic (PRD §10.3)
- **Clinical-professional, not consumer-flashy.**
- **Reduced palette**: neutrals primary; reserved red (Critical), amber (Watch), green (Resolved). NO gradients.
- **Typography**: sans-serif system stack, monospace for codes (NDC, RxCUI). High contrast.
- **Citation-first** — citations visible by default, NOT hidden in tooltips/expanders.
- **Tool call traces** rendered as stepped log, like a developer console — transparency IS the trust UX.
- **Empty states**: "No shortages affecting your formulary today" reads as good news, with last-run timestamp.
- **Loading**: skeletons over spinners. Tool calls stream in but don't bounce/animate.
- **No "AI sparkle" iconography** — this is clinical software.

## Anti-patterns (PRD §10.4) — explicit rejections
| Reject                                | Adopt                                       |
|---------------------------------------|---------------------------------------------|
| Multi-tab hierarchies                 | Single-screen scannable dashboard           |
| Search-first                          | Briefing-first; users don't search          |
| Show-everything                       | Show-only-what-affects-this-hospital        |
| Feature-first nav                     | Outcome-first surface that explains itself  |
| Modal stacks / nested menus           | Inline expansion; max 1 click to source     |
| Conversational chatbot                | Structured briefing; pharmacist scans, not types |

## Motion (§10.5)
Restrained. Skeletons not spinners. Severity color transitions instant, not animated. **Speed perception is the priority.**

## Visual scan order (FR-11)
1. Top: stats (date, items by severity, last-run timestamp)
2. Middle: severity-ordered items (Critical → Watch → Resolved)
3. Each item: severity badge → drug name → one-sentence summary → recommended action → expandable detail

## Speed targets (FR-9)
- Dashboard loads with last briefing: <2s
- Drill-down to citation: <1s
- Information density appropriate for power users (FR-10) — pharmacist scans, doesn't read.

## Trust requirements
- Will NOT act on a recommendation without a citation.
- Will NOT trust a tool that has hallucinated even once.
- Confidence score visible per recommendation (high/medium/low).
- Synthetic data labeled as synthetic.

## Formulary visualization needs
- 30-drug synthetic formulary, real RxCUIs, with `formulary_status`, `restriction_criteria`, `preferred_alternatives[]`, `last_pt_review_date`.
- Pharmacist scan needs: which formulary drugs overlap with current FDA shortages? What route/class? What's restricted? What's the preferred alt?
