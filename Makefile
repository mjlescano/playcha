.PHONY: dev lint fix format check test install install-dev fetch-browser docker-build

# Install production dependencies
install:
	pip install -r requirements.txt

# Install package in editable mode with dev dependencies
install-dev:
	pip install -e ".[dev]"

# Download the Camoufox browser binary
fetch-browser:
	python -m camoufox fetch

# Run the app locally
dev:
	python -m playcha

# Run linter
lint:
	ruff check src/ tests/

# Run linter with auto-fix
fix:
	ruff check --fix src/ tests/

# Format source code
format:
	ruff format src/ tests/

# Run linter and check formatting (CI)
check: lint
	ruff format --check src/ tests/

# Run integration tests
test:
	PYTHONPATH=src pytest tests/ -v

# Build the Docker image
docker-build:
	docker build -t playcha .
