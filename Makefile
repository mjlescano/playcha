.PHONY: dev lint fix format check install install-dev fetch-browser \
       docker-build docker-build-binary docker-build-builder

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
	ruff check src/

# Run linter with auto-fix
fix:
	ruff check --fix src/

# Format source code
format:
	ruff format src/

# Run linter and check formatting (CI)
check: lint
	ruff format --check src/

# Build the standard Docker image
docker-build:
	docker build -t playcha .

# Build the PyInstaller-based standalone binary image
docker-build-binary:
	docker build -f Dockerfile.binary -t playcha-binary .

# Build only the builder stage (for extracting binaries to embed in other images)
docker-build-builder:
	docker build -f Dockerfile.binary --target builder -t playcha-builder .
