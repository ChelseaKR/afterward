.DEFAULT_GOAL := help

.PHONY: help install format lint typecheck test security audit provenance-check verify build data

help:
	@uv run camino --help

install:
	uv sync --all-groups

format:
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy src

test:
	uv run pytest --cov=camino --cov-report=term-missing

security:
	uv run bandit -q -c pyproject.toml -r src

audit:
	@attempt=1; while [ $$attempt -le 3 ]; do \
		uv run pip-audit && exit 0; \
		echo "pip-audit attempt $$attempt failed; retrying" >&2; \
		attempt=$$((attempt + 1)); \
		sleep 3; \
	done; exit 1

# Enforces the clean-room constraint recorded in PROVENANCE.md.
provenance-check:
	uv run python scripts/provenance_check.py

# Refresh the dataset from DOL and CA EDD. Network-bound; not part of `verify`.
data:
	uv run camino build

verify: provenance-check lint typecheck test security audit

build: verify
	uv build
