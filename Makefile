.PHONY: dev lint fix format check test install install-dev fetch-browser docker-build version

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

# Bump version: make version patch|minor|major|X.Y.Z
version:
	@BMP="$(firstword $(filter-out version,$(MAKECMDGOALS)))"; \
	if [ -z "$$BMP" ]; then echo "Usage: make version patch|minor|major|X.Y.Z"; exit 1; fi; \
	CURRENT=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	if echo "$$BMP" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$$'; then \
	  NEW="$$BMP"; \
	else \
	  MAJOR=$$(echo "$$CURRENT" | cut -d. -f1); MINOR=$$(echo "$$CURRENT" | cut -d. -f2); PATCH=$$(echo "$$CURRENT" | cut -d. -f3); \
	  case "$$BMP" in major) NEW="$$((MAJOR+1)).0.0";; minor) NEW="$$MAJOR.$$((MINOR+1)).0";; patch) NEW="$$MAJOR.$$MINOR.$$((PATCH+1))";; *) echo "Invalid BUMP: $$BMP"; exit 1;; esac; \
	fi; \
	sed -i.bak "s/^version = \".*\"/version = \"$$NEW\"/" pyproject.toml && rm -f pyproject.toml.bak; \
	sed -i.bak "s/\([[:space:]]*__version__ = \)\".*\"/\1\"$$NEW-dev\"/" src/playcha/__init__.py && rm -f src/playcha/__init__.py.bak; \
	echo "Version set to $$NEW"

# Catch-all so "make version patch" doesn't try to build target "patch"
%:
	@:
