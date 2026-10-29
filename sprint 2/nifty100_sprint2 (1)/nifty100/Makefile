PY ?= python3

.PHONY: setup load ratios test validate report api dashboard clean

setup:
	$(PY) -m venv .venv
	.venv/bin/pip install -r requirements.txt
	test -f .env || cp config/.env.template .env

load:
	$(PY) -m src.etl.loader

ratios:
	$(PY) -m src.analytics.engine
	$(PY) -m src.analytics.edge_cases
	$(PY) -m src.analytics.spotcheck
	$(PY) -m src.analytics.screener_preview

validate:
	$(PY) -m src.etl.loader --validate-only

test:
	$(PY) -m pytest tests -q

clean:
	rm -f data/nifty100.db output/load_audit.csv output/validation_failures.csv output/parse_failures.csv output/capital_allocation.csv output/ratio_edge_cases.log output/spot_check.md output/screener_preview.csv

report api dashboard:
	@echo "Not implemented until a later sprint"
