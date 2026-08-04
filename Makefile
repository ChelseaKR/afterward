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
# Emits straight into the web app's public directory, which is where the site reads it.
data:
	uv run camino build --output-dir web/public/data

# Build the site dataset from the committed fixture, with no network access.
# CI uses this: the DOL endpoint refuses GitHub Actions runners, and a build that depends on
# a third party being reachable fails for reasons unrelated to the change under test.
data-offline:
	uv run camino build-offline

# Regenerate the committed fixture from a real dataset. Run after `make data`.
fixture:
	uv run python scripts/make_fixture.py

web-install:
	cd web && npm ci

web-dev:
	cd web && npm run dev

# Static export of the whole site. Requires `make data` to have run at least once.
web-build:
	cd web && npm run build

# Typecheck, unit tests, static export, then an axe pass over the built pages.
web-verify:
	cd web && npm run verify

verify: provenance-check lint typecheck test security audit

build: verify
	uv build
