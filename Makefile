PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: test
test:
	$(PY) -m pytest -q tests validation/tests
