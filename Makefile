.PHONY: help setup install-dev lint format test test-cov build check pre-commit clean

help:
	@echo "Tri-Arb Makefile Commands:"
	@echo "  make setup        - Complete environment setup (uv + venv + dependencies)"
	@echo "  make install-dev  - Install development dependencies"
	@echo "  make lint         - Run mypy type checking"
	@echo "  make format       - Format code with ruff"
	@echo "  make test         - Run all tests"
	@echo "  make test-cov     - Run tests with coverage report"
	@echo "  make build        - Build binary with PyInstaller"
	@echo "  make check        - Run all quality checks (lint + format + test)"
	@echo "  make pre-commit   - Pre-commit checks (format + check)"
	@echo "  make clean        - Clean build artifacts and caches"

setup:
	@echo "Setting up environment with uv..."
	uv venv --python 3.11
	@echo "Activating virtual environment and installing dependencies..."
	uv pip install -e ".[dev]"
	@echo "Setup complete! Activate with: source .venv/bin/activate"

install-dev:
	uv pip install -e ".[dev]"

lint:
	@echo "Running mypy type checking..."
	uv run mypy src/

format:
	@echo "Formatting code with ruff..."
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

test:
	@echo "Running tests..."
	uv run pytest

test-cov:
	@echo "Running tests with coverage..."
	uv run pytest --cov=src/tri_arb --cov-report=html --cov-report=term

build:
	@echo "Building binary with PyInstaller..."
	./scripts/build.sh

check: lint test
	@echo "All checks passed!"

pre-commit: format check
	@echo "Pre-commit checks complete!"

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ *.spec
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ .coverage
	rm -rf src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete!"
