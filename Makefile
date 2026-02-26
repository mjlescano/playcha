.PHONY: dev lint fix format check install install-dev fetch-browser

install:
	pip install -r requirements.txt

install-dev:
	pip install -e ".[dev]"

fetch-browser:
	python -m camoufox fetch

dev:
	python -m playcha

lint:
	ruff check src/

fix:
	ruff check --fix src/

format:
	ruff format src/

check: lint
	ruff format --check src/
