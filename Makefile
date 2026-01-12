.PHONY: venv lint format test run

venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

lint:
	.venv/bin/ruff .

format:
	.venv/bin/black .

test:
	.venv/bin/pytest

run:
	.venv/bin/uvicorn quail.web:app --reload
