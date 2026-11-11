PY ?= python3
export PYTHONPATH := src

.PHONY: install demo run report test lint clean

install:
	$(PY) -m pip install -r requirements-dev.txt

## Full demo: 90 days, load, 30 more days arrive, incremental load, charts
demo: clean
	$(PY) -m pipeline generate --days 90
	$(PY) -m pipeline run
	$(PY) -m pipeline run
	$(PY) -m pipeline generate --days 120
	$(PY) -m pipeline run
	$(PY) -m pipeline report

run:
	$(PY) -m pipeline run

report:
	$(PY) -m pipeline report

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests

clean:
	rm -rf data
