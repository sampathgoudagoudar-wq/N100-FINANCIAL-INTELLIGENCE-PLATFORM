PY ?= python3

.PHONY: setup load test validate report api dashboard clean

setup:
	$(PY) -m venv .venv
	.venv/bin/pip install -r requirements.txt
	test -f .env || cp config/.env.template .env

load:
	$(PY) -m src.etl.loader

validate:
	$(PY) -m src.etl.loader --validate-only

test:
	$(PY) -m pytest tests -q

clean:
	rm -f data/nifty100.db output/load_audit.csv output/validation_failures.csv output/parse_failures.csv

report api dashboard:
	@echo "Not implemented until a later sprint"
