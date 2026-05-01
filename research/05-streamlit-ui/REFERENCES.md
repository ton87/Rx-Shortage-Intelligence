# Streamlit UI — References

## Streamlit core

- Docs home: https://docs.streamlit.io/
- API reference: https://docs.streamlit.io/develop/api-reference
- Layout primitives: https://docs.streamlit.io/develop/api-reference/layout
- Caching: https://docs.streamlit.io/develop/concepts/architecture/caching
- Session state: https://docs.streamlit.io/develop/concepts/architecture/session-state

## Components used

- `st.container(border=True)`: https://docs.streamlit.io/develop/api-reference/layout/st.container
- `st.expander`: https://docs.streamlit.io/develop/api-reference/layout/st.expander
- `st.metric`: https://docs.streamlit.io/develop/api-reference/data/st.metric
- `st.status`: https://docs.streamlit.io/develop/api-reference/status/st.status
- `st.dataframe` styling: https://docs.streamlit.io/develop/api-reference/data/st.dataframe

## Threading + async

- Multithreading caveats: https://docs.streamlit.io/develop/concepts/design/multithreading
- "ScriptRunContext" error explanation: https://discuss.streamlit.io/

## PRD anchors

- §10.1 Desired UX (briefing not chatbot)
- §10.2 Critical user flows (morning briefing, drill-down, eval)
- §10.3 Visual aesthetic
- §10.4 Anti-patterns we reject
- §10.5 Animation/motion (restrained)
- FR-8 / FR-9 / FR-10 / FR-11

## Internal POCs

- `POC-dashboard-layout.py` — main briefing page
- `POC-drilldown-trace.py` — agent reasoning + tool-call console
- `POC-eval-tab.py` — 15-case grid + aggregate metrics
