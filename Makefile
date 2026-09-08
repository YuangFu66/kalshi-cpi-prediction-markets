# Reproduce the whole project.  `make` = rebuild everything from the committed
# raw data (no network).  `make pull` re-downloads the raw data (~10 minutes).
PY ?= python3

.PHONY: all pull build evaluate test help

all: build evaluate

pull:      ## Re-download raw Kalshi, Cleveland Fed and BLS data (network)
	$(PY) src/pull_events.py
	$(PY) src/pull_candles.py
	$(PY) src/pull_cleveland_nowcast.py
	$(PY) src/pull_bls_cpi.py

build:     ## Clean tables + benchmark comparison from data/raw and data/external
	$(PY) src/build_series.py
	$(PY) src/build_benchmarks.py

evaluate:  ## Accuracy tables, Diebold-Mariano tests, chart -> results/
	$(PY) src/evaluate.py
	$(PY) src/make_comparison_chart.py

test:      ## Unit tests + checks that the committed data reproduces the README numbers
	$(PY) -m unittest discover -s tests -v

help:
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/  -/'
