# Streamlit UI — Tradeoffs

## Streamlit vs alternatives

| Framework | Pro | Con |
|-----------|-----|-----|
| **Streamlit** (chosen) | Single-file Python, hours-to-ship, native widgets | Limited custom layout, threading sharp edges, "looks streamlit" |
| Gradio | Similar simplicity, ML-focus | Less polish on data-dense layouts |
| FastAPI + React | Total control over look | Days-to-ship, two-codebase split |
| Next.js + tRPC | Same as React, plus SSR | Even longer to ship |

PRD §12.1 picks Streamlit explicitly: "Fast to build, professional enough, runs locally." Honored.

## Layout: tabs vs single-page vs sidebar nav

| Approach | Pro | Con |
|----------|-----|-----|
| **Single-page briefing + sidebar for admin pages** (chosen) | PRD §10.4 inverts multi-tab; primary flow uncluttered | Eval tab is sidebar-hidden — admin-style |
| Three top tabs (Briefing/Drilldown/Eval) | Familiar | Inverts our anti-pattern |
| Single page, anchor scroll | Even less click | Eval table dominates layout |

Sidebar nav (Streamlit's `pages/`) for admin-only views. Briefing is the front door.

## Drill-down: inline expander vs separate page vs modal

| Approach | Pro | Con |
|----------|-----|-----|
| **`st.expander` inline** (chosen) | Max 1 click to source per PRD §10.4 | Long expanded items push neighbors down |
| Separate page on click | Detail-rich layout | Multi-click; harder back-nav |
| `st.modal` | Stays on context | PRD anti-pattern (modal stacks) |

Inline expander wins. Pharmacist scans → expands one → reads → collapses → next.

## Tool-call trace: console-style vs prose

| Approach | Pro | Con |
|----------|-----|-----|
| **Console-style stepped log (`st.code`)** (chosen) | "Transparency itself is part of trust UX" — PRD §10.3 | Looks dev-y; might intimidate |
| Prose narrative | Human-friendly | Hides what actually happened |
| Hidden, with link to raw JSON | Clean briefing | Customer can't audit |

Console wins. Pharmacy directors are technical buyers.

## Streaming agent runs

| Approach | Pro | Con |
|----------|-----|-----|
| **`st.status` with streamed `st.write()` per tool call** (chosen) | Live feel; transparency | Blocks main thread |
| Background thread + `st.session_state` polling | Non-blocking | Streamlit ScriptRunContext issues |
| No streaming, show after | Simplest | Feels like nothing's happening for 30+ sec |

Synchronous + `st.status` chosen. v0.1 doesn't need true async.

## Animations

| Approach | Pro | Con |
|----------|-----|-----|
| **None / minimal `st.skeleton`** (chosen) | PRD §10.5 "Restrained" | Less "wow" |
| Spinners | Familiar | Anti-pattern per PRD |
| Custom animations | Visual polish | Time sink |

Restrained.

## Color palette

| Approach | Pro | Con |
|----------|-----|-----|
| **Red/amber/green only, neutrals otherwise** (chosen, per PRD §10.3) | Clinical look | Less differentiation |
| Full data-viz palette | More signal channels | Confusing alongside severity reds |

Severity colors carry the only saturated meaning.

## Threading + async gotchas

- FastMCP Client = async-only. Wrap in `asyncio.run()` inside `@st.cache_resource`.
- Never put async at top level — Streamlit runs synchronously per script execution.
- Never spawn threads — `st.session_state` reads from threads fail with ScriptRunContext error.

## What we'd improve

- Real "first time visitor" empty state with a 1-line "what is this" intro
- Dark mode (Streamlit theme-able but extra work)
- Keyboard shortcuts (J/K to navigate items)
- Server-side rendering for true <2 sec load
- Per-user settings (which severity to expand by default)
