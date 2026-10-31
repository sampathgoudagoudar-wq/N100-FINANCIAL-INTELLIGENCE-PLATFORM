PY ?= python3

load:        ## load/clean raw Excel files into data/nifty100.db
	$(PY) run_sprint4.py
ratios:      ## recompute financial_ratios (part of the DB build)
	$(PY) -c "from src.data.build_db import build; print(build())"
test:        ## all tests + HTML report
	mkdir -p reports && $(PY) -m pytest tests -q --html=reports/pytest_report.html --self-contained-html
report:      ## screener, peer, radar, valuation outputs (tearsheets/sector/portfolio PDFs: not built yet)
	$(PY) run_sprint3.py && $(PY) run_sprint4.py
dashboard:
	streamlit run src/dashboard/app.py --server.port 8501
api:
	@echo "FastAPI server (src/api/main.py) is not built yet" && exit 1
clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} + ; rm -rf .pytest_cache
.PHONY: load ratios test report dashboard api clean
