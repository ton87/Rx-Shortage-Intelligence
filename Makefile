PY := venv/bin/python3
PIP := venv/bin/pip

.PHONY: install data run briefing test eval smoke

install:
	$(PIP) install -r requirements.txt

data:
	$(PY) -m src.data_loader

run:
	venv/bin/streamlit run src/main.py

briefing:
	$(PY) -m src.briefing

test:
	$(PY) -m pytest tests/ -q

eval:
	$(PY) -m src.eval.runner

smoke:
	$(PY) -m src.mcp_bridge
