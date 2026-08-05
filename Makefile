.DEFAULT_GOAL := help

.PHONY: help install format lint typecheck test security audit provenance-check verify build data \
	link-check dataset-verify dataset-package dataset-publish backup-data deploy-check \
	publish-preflight publish dataset-check dataset-manifest

# Where `make data` leaves the site dataset, and where `make dataset-package` picks it up.
DATASET_DIR ?= web/public/data
DIST_DIR ?= dist
# Floor for a believable production dataset. Real: 3,266 programs. Fixture: 60.
MIN_PROGRAMS ?= 2000

help:
	@uv run afterward --help

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
	uv run pytest --cov=afterward --cov-report=term-missing

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
# Backs up first, and the backup refuses to run over a dataset that does not look real.
data: backup-data
	uv run afterward build --output-dir web/public/data
	@$(MAKE) dataset-check

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
# Publish the built site, in the only order that is safe.
#
# Assembled by hand seven times on 2026-08-04 and got wrong three different ways: HTML synced
# with --size-only (which skips a page whose only change is a fixed-length chunk hash, so
# 22,528 files silently stayed stale and the search page served references to chunks the
# asset sync had just deleted); the verification run from web/ where the Makefile is not, so
# it reported success by not running; and no guard at all against publishing the test
# fixture, which deploy.yml protects and a hand-run sync does not.
#
# Order matters more than the flags, and getting it wrong breaks the site in two opposite
# ways. HTML first leaves a window -- ten minutes wide on a full upload -- where published
# pages reference a stylesheet and chunks that are not there yet; that shipped once and the
# site loaded unstyled. Deleting assets first leaves stale HTML pointing at files that have
# just been removed; that shipped too, and the search page went dead.
#
# So: upload new assets (additive, content-hashed, referenced by nothing yet), then HTML
# (every asset it names is already present), then invalidate, and only then prune the assets
# nothing points at any more. There is no moment in that sequence when a served page can
# reference a missing file.
#
# Never with --size-only: chunk names are fixed-length hashes, so a page whose only change is
# which chunk it loads is byte-identical in length and gets skipped.
# The Afterward distribution. The old camino one (E166CPAG407D0L) still serves
# camino.chelseakr.com and is republished deliberately, by overriding these two.
DISTRIBUTION_ID ?= E2WV13UCB2U1MF
SITE_BUCKET ?= afterward.chelseakr.com
publish: publish-preflight
	@echo "1/4 uploading new assets (additive: nothing references them yet)"
	aws s3 sync web/out/_next/static/ "s3://$(SITE_BUCKET)/_next/static/" \
	  --cache-control "public, max-age=31536000, immutable"
	@echo "2/4 uploading HTML (every asset it references is already there)"
	aws s3 sync web/out/ "s3://$(SITE_BUCKET)/" --delete \
	  --cache-control "public, max-age=300, must-revalidate" --exclude "_next/static/*"
	@echo "3/4 invalidating"
	@id=$$(aws cloudfront create-invalidation --distribution-id $(DISTRIBUTION_ID) \
	  --paths "/*" --query 'Invalidation.Id' --output text); \
	  echo "    invalidation $$id"; \
	  aws cloudfront wait invalidation-completed --distribution-id $(DISTRIBUTION_ID) --id "$$id"
	@echo "4/4 pruning assets no longer referenced"
	aws s3 sync web/out/_next/static/ "s3://$(SITE_BUCKET)/_next/static/" --delete \
	  --cache-control "public, max-age=31536000, immutable"
	$(MAKE) deploy-check

# Refuse to publish a build made from the test fixture.
#
# deploy.yml guards this and a manual `aws s3 sync` does not go through deploy.yml. Run
# before every hand publish; the dataset is gitignored and sync will ship whatever is in out/.
publish-preflight:
	uv run python scripts/publish_preflight.py web/out

SITE_URL ?= https://afterward.chelseakr.com
deploy-check:
	uv run python scripts/deploy_check.py "$(SITE_URL)"

# Is the working dataset the real one, or the 60-program fixture?
#
# Guards the direction publish-preflight cannot: `backup-data` mirrors with `rsync --delete`,
# so backing up a corrupted dataset destroys the last good copy. Any automatic backup without
# this check is worse than a manual one.
dataset-check:
	uv run python scripts/dataset_check.py

# Record the current dataset's shape as the thing to compare against. Run after a real
# refresh, never to paper over a check that just failed.
dataset-manifest:
	uv run python scripts/dataset_check.py --write

BACKUP_DIR ?= ../afterward-dataset-backup
backup-data: dataset-check
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
	uv run afterward check-links --dataset-dir $(DATASET_DIR)

# Build the site dataset from the committed fixture, with no network access.
# CI uses this: the DOL endpoint refuses GitHub Actions runners, and a build that depends on
# a third party being reachable fails for reasons unrelated to the change under test.
data-offline:
	uv run afterward build-offline

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
