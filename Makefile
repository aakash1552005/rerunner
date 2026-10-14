.PHONY: help install dev test lint format typecheck check clean

PYTHON ?= python
PYTEST ?= pytest
RUFF ?= ruff
MYPY ?= mypy

help:
	@echo "Rerunner Development & Contribution Commands:"
	@echo "  make install     Install package in editable mode with development dependencies"
	@echo "  make test        Run all unit and integration tests with pytest"
	@echo "  make lint        Check code style and lint rules with ruff"
	@echo "  make format      Auto-format code with ruff"
	@echo "  make typecheck   Run static type checking with mypy"
	@echo "  make check       Run format, lint, typecheck, and test suite in sequence"
	@echo "  make clean       Remove cached bytecode, pytest, and build artifacts"

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTEST)

lint:
	$(RUFF) check src tests

format:
	$(RUFF) format src tests
	$(RUFF) check src tests --fix

typecheck:
	$(MYPY) src tests

check: format lint typecheck test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
