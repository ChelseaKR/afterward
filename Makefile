.DEFAULT_GOAL := help

.PHONY: help install format lint typecheck test security audit provenance-check verify build data \
	link-check dataset-verify dataset-package dataset-publish backup-data deploy-check \
	publish-preflight

# Where `make data` leaves the site dataset, and where `make dataset-package` picks it up.
DATASET_DIR ?= web/public/data
DIST_DIR ?= dist
# Floor for a believable production dataset. Real: 3,266 programs. Fixture: 60.
MIN_PROGRAMS ?= 2000

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
#
# CareerOneStop credentials (.env.local) add two things and are optional for both: the
# occupation descriptions, and the America's Job Centers each program page names as the place
# to ask about having the training paid for. Without them the build is complete and simply
# claims nothing about where the nearest office is -- which is what CI does. The centre
# directory is one request for the whole state and is cached under data/raw/cos-cache.
data:
	uv run camino build --output-dir web/public/data

# Copy the built dataset somewhere a mistake cannot reach.
#
# web/public/data and data/processed are both gitignored, so the working dataset is the only
# copy of roughly 3,300 programs' worth of DOL and EDD fetches. `make data` overwrites it in
# place, the DOL endpoint answers CI with 403, and a full refetch is slow -- so a build that
# goes wrong halfway is not an inconvenience, it is the loss of the data the site publishes.
# Run this before any pipeline change.
# Ask the live site whether every asset its pages reference actually resolves.
#
# Run after every publish. The object-count comparison this replaces matched perfectly while
# 22,528 HTML files on S3 were stale -- a count cannot see a file that was skipped.
#
# NEVER publish this site's HTML with `aws s3 sync --size-only`. Next.js chunk names are
# fixed-length hashes, so a page whose only change is which chunk it loads is byte-identical
# in *length*; --size-only compares length alone and skips it, while the asset sync's
# --delete removes the chunk the stale copy still points at. The result is a page that
# loads, fails to hydrate, and looks fine to every check that counts things.
# Refuse to publish a build made from the test fixture.
#
# deploy.yml guards this and a manual `aws s3 sync` does not go through deploy.yml. Run
# before every hand publish; the dataset is gitignored and sync will ship whatever is in out/.
publish-preflight:
	uv run python scripts/publish_preflight.py web/out

SITE_URL ?= https://camino.chelseakr.com
deploy-check:
	uv run python scripts/deploy_check.py "$(SITE_URL)"

BACKUP_DIR ?= ../camino-dataset-backup
backup-data:
	@mkdir -p "$(BACKUP_DIR)"
	@rsync -a --delete data/processed/ "$(BACKUP_DIR)/processed/"
	@rsync -a --delete web/public/data/ "$(BACKUP_DIR)/webdata/"
	@rsync -a --delete data/raw/ "$(BACKUP_DIR)/raw/"
	@python3 -c "import json,sys; d=json.load(open('$(BACKUP_DIR)/webdata/occupations.json')); \
	  p=json.load(open('$(BACKUP_DIR)/webdata/programs.json')); \
	  print(f\"backup ok: {len(d['occupations'])} occupations, {len(p['programs'])} programs\")"

# Ask every provider URL in the current dataset whether it still goes anywhere, and leave a
# report for the next `make data` to read.
#
# Deliberately NOT part of `data`, and never part of `verify`. It spends ~1,500 HTTP requests
# on small colleges and adult schools, so it belongs to a person who decided to spend them --
# quarterly, alongside a data refresh, not on every build. Results are cached per URL under
# data/raw/link-cache (alive 30 days, dead 7, indeterminate 1), so a re-run asks only about
# what has expired. A build that finds no report publishes every link exactly as filed.
#
# Run `make data` first, then this, then `make data` again to publish the result.
link-check:
	uv run camino check-links --dataset-dir $(DATASET_DIR)

# Build the site dataset from the committed fixture, with no network access.
# CI uses this: the DOL endpoint refuses GitHub Actions runners, and a build that depends on
# a third party being reachable fails for reasons unrelated to the change under test.
data-offline:
	uv run camino build-offline

# Regenerate the committed fixture from a real dataset. Run after `make data`.
fixture:
	uv run python scripts/make_fixture.py

# --- Handing a production dataset to CI -----------------------------------------------
# The deploy workflow cannot build this itself: DOL answers GitHub Actions runners with 403
# and CareerOneStop credentials are per-user. So the dataset is built here, checked here,
# and published as an immutable release asset that .github/workflows/deploy.yml consumes by
# tag. Run `make data` first, then `make dataset-publish`.

# Refuse to package anything that looks like the fixture, a truncated build, or a source
# that has quietly started returning almost nothing.
dataset-verify:
	@test -f $(DATASET_DIR)/coverage.json || { \
		echo "No $(DATASET_DIR)/coverage.json. Run 'make data' first." >&2; exit 1; }
	@set -- $$(uv run python -c 'import json;d=json.load(open("$(DATASET_DIR)/coverage.json"));print(d.get("is_fixture", False), d.get("total_programs", 0), d.get("snapshot_date", "unknown"))'); \
	if [ "$$1" != "False" ]; then \
		echo "REFUSING: $(DATASET_DIR) is the fixture (is_fixture=true)." >&2; \
		echo "Run 'make data' on a machine that can reach the sources." >&2; exit 1; \
	fi; \
	if [ "$$2" -lt $(MIN_PROGRAMS) ]; then \
		echo "REFUSING: total_programs=$$2 is below the $(MIN_PROGRAMS) floor." >&2; exit 1; \
	fi; \
	files=$$(find $(DATASET_DIR)/programs -name '*.json' | wc -l | tr -d ' '); \
	if [ "$$files" -ne "$$2" ]; then \
		echo "REFUSING: $$files program files on disk, coverage.json claims $$2." >&2; exit 1; \
	fi; \
	echo "dataset ok: $$2 programs in $$files files, snapshot $$3"

# Tarball plus checksum, into dist/ (gitignored). COPYFILE_DISABLE keeps macOS from
# packing ._* companions, which would otherwise arrive as bogus programs/*.json.
dataset-package: dataset-verify
	@mkdir -p $(DIST_DIR)
	@snapshot=$$(uv run python -c 'import json;print(json.load(open("$(DATASET_DIR)/coverage.json"))["snapshot_date"])'); \
	tarball=camino-dataset-$$snapshot.tar.gz; \
	COPYFILE_DISABLE=1 tar -czf $(DIST_DIR)/$$tarball -C $(DATASET_DIR) .; \
	( cd $(DIST_DIR) && if command -v sha256sum >/dev/null 2>&1; then \
		sha256sum $$tarball > $$tarball.sha256; else shasum -a 256 $$tarball > $$tarball.sha256; fi ); \
	ls -lh $(DIST_DIR)/$$tarball $(DIST_DIR)/$$tarball.sha256

# Publish the package as a release the deploy workflow can pull. The tag is the snapshot
# date, so every deploy names exactly which dataset it published.
dataset-publish: dataset-package
	@set -- $$(uv run python -c 'import json;d=json.load(open("$(DATASET_DIR)/coverage.json"));print(d["snapshot_date"], d["total_programs"])'); \
	tarball=camino-dataset-$$1.tar.gz; \
	gh release create dataset-$$1 $(DIST_DIR)/$$tarball $(DIST_DIR)/$$tarball.sha256 \
		--title "Dataset $$1" \
		--notes "Site dataset built from the live sources on $$1: $$2 programs."; \
	echo; \
	echo "Now run the Deploy workflow with dataset_tag=dataset-$$1"

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
