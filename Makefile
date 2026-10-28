PY ?= python3

.PHONY: test eval demo fixtures manifest check

test:
	$(PY) -m pytest -q

eval:            ## synthetic replay; writes evals/report.json
	$(PY) evals/replay.py

fixtures:        ## regenerate synthetic fixtures and labels
	$(PY) scripts/build_fixtures.py

manifest:        ## files the browser demo loads
	$(PY) scripts/build_manifest.py

demo: manifest   ## http://localhost:8000/demo/
	$(PY) -m http.server 8000

check: test
	$(PY) evals/replay.py --check
