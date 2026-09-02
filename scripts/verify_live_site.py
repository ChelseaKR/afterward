#!/usr/bin/env python3
"""Fail when the data afterward.chelseakr.com serves is not the dataset it names.

`publish_preflight.py` grades `web/out` before it leaves the runner, deploy.yml
compares the local key set with the bucket's and smoke-tests four routes, and
`deploy_check.py` asks the CDN whether the assets a page references resolve.
Every one of those runs inside the deploy that produced the artifact, or by hand.
Nothing runs afterwards, and nothing has ever compared a published byte with a
byte this project produced.

That matters here because the payload is claims about real training programs:
median earnings, completion rates, employment rates, and a link to the provider.
A partially synced `data/` directory, an interrupted `--delete` pass, or a bucket
half-written from two different snapshots would leave every gate green and serve
a reader one program's outcomes under another program's name.

WHAT THIS COMPARES, AND WHY IT IS THE DATASET RATHER THAN THE PAGES

The deployed HTML is not reproducible from a checkout. Next.js mints a random
`buildId` per build and stamps it into nearly every exported file, so two builds
of the same commit differ in about 40,000 of their 40,000 files; the dataset
itself is not in git, it arrives as a release asset; and nothing published
records which commit or which release the live site was built from except
`data/coverage.json`. Byte equality over the export would therefore fail for
reasons that are not drift.

So this takes the site at its word about which dataset it is serving, and then
holds it to that word exactly:

  1. read `/data/coverage.json` from the live site, and refuse a fixture, a
     missing snapshot date, or a program count below the floor;
  2. take the dataset release the snapshot date names, `dataset-<snapshot>`,
     which is how `make dataset-publish` tags them;
  3. verify the tarball against the `.sha256` published beside it;
  4. compare every file in it, byte for byte, with what the origin serves
     under `/data/`, and fail naming every difference.

That is roughly 3,900 files: the four aggregates and one JSON per program and
per occupation. It is the whole machine-readable claim surface.

Pinning `generateBuildId` in `web/next.config.ts` and publishing a `version.json`
would make the pages comparable too, and would answer "which commit is live". Both
change what gets deployed, so neither is done here.

    make live-check
    python3 scripts/verify_live_site.py --dataset path/to/afterward-dataset-*.tar.gz

Vacuity is the failure mode a check like this is most exposed to, so these are
refused rather than reported as a pass: a fixture dataset, a program count below
the floor, a comparison set below the floor, any fetch that is not HTTP 200, and
an origin that answers a guaranteed-missing path with anything but 404.

Exit codes: 0 the served data is the named dataset, 1 it is not, 4 the check
could not run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import re
import secrets
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

SITE_URL = "https://afterward.chelseakr.com"

# deploy.yml refuses to publish a dataset below 2000 programs. The same floor here
# means a shrunken or truncated dataset fails rather than being compared happily.
MINIMUM_PROGRAMS = 2000
MINIMUM_FILES = 2000

MAXIMUM_FILE_BYTES = 64 * 1024 * 1024
MAXIMUM_TARBALL_BYTES = 256 * 1024 * 1024
SNAPSHOT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

EXIT_DIFFERS = 1
EXIT_CANNOT_RUN = 4


class LiveSiteError(RuntimeError):
    """The served data could not be verified against the dataset the site names."""


class Origin:
    """Bounded HTTPS reads from one fixed public origin, on reused connections.

    One connection per thread. Roughly 3,900 files at 185 ms each is twelve minutes
    on a single connection; a handful of connections brings it to about two, which
    is the difference between a check that runs daily and one that is turned off.
    """

    def __init__(self, url: str, *, timeout_seconds: float) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
            raise LiveSiteError(f"live URL {url!r} is not a canonical HTTPS origin")
        if not 1.0 <= timeout_seconds <= 60.0:
            raise LiveSiteError("timeout must be between 1 and 60 seconds")
        self.host = parts.hostname
        self.base = parts.path.rstrip("/")
        self.url = url
        self._timeout = timeout_seconds
        self._local = threading.local()

    @property
    def _connection(self) -> http.client.HTTPSConnection | None:
        return getattr(self._local, "connection", None)

    @_connection.setter
    def _connection(self, value: http.client.HTTPSConnection | None) -> None:
        self._local.connection = value

    def _connect(self) -> http.client.HTTPSConnection:
        if self._connection is None:
            # The audit rule below is about HTTPSConnection used without certificate
            # verification: Python before 3.4.3 did not verify by default. This call
            # passes ssl.create_default_context(), which verifies both the chain and
            # the hostname, and is the condition the rule exists to require.
            # nosemgrep: httpsconnection-detected
            self._connection = http.client.HTTPSConnection(
                self.host, timeout=self._timeout, context=ssl.create_default_context()
            )
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def get(self, relative: str, *, nonce: str) -> tuple[int, bytes]:
        if relative.startswith("/") or "?" in relative or "#" in relative:
            raise LiveSiteError(f"relative path {relative!r} is not canonical")
        target = f"{self.base}/{relative}?live-integrity={nonce}"
        for attempt in (1, 2):
            connection = self._connect()
            try:
                connection.request(
                    "GET",
                    target,
                    headers={
                        "Accept-Encoding": "identity",
                        "Cache-Control": "no-cache, no-store, max-age=0",
                        "User-Agent": "afterward-live-integrity/1",
                    },
                )
                response = connection.getresponse()
                body = response.read(MAXIMUM_FILE_BYTES + 1)
                if len(body) > MAXIMUM_FILE_BYTES:
                    raise LiveSiteError(f"{target} exceeds the read limit")
                return response.status, body
            except (OSError, http.client.HTTPException) as exc:
                # A reused connection can be closed by the far end between requests.
                # One reconnect, then the failure is real and must not be swallowed.
                self.close()
                if attempt == 2:
                    raise LiveSiteError(f"GET https://{self.host}{target} failed: {exc}") from exc
        raise LiveSiteError("unreachable")


def short(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:16]


def prove_the_origin_discriminates(origin: Origin, nonce: str) -> None:
    """A host that answers everything with 200 makes every comparison vacuous."""
    missing = f".live-integrity-guaranteed-absent-{nonce}"
    status, _ = origin.get(missing, nonce=nonce)
    if status != 404:
        raise LiveSiteError(
            f"the origin answered a guaranteed-missing path with HTTP {status} instead "
            f"of 404, so a matching fetch would prove nothing: /{missing}"
        )


def live_coverage(origin: Origin, nonce: str) -> tuple[str, int]:
    """What the site says it is serving, refused rather than trusted where it cannot be."""
    status, body = origin.get("data/coverage.json", nonce=nonce)
    if status != 200:
        raise LiveSiteError(f"/data/coverage.json returned HTTP {status}")
    try:
        coverage = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveSiteError(f"/data/coverage.json is not valid JSON: {exc}") from exc
    if not isinstance(coverage, dict):
        raise LiveSiteError("/data/coverage.json is not a JSON object")
    if coverage.get("is_fixture"):
        raise LiveSiteError(
            "the live site is serving the CI fixture dataset, not production data. "
            "That is a deploy defect, not a comparison this check should go on to make."
        )
    snapshot = coverage.get("snapshot_date")
    if not isinstance(snapshot, str) or SNAPSHOT.fullmatch(snapshot) is None:
        raise LiveSiteError(f"/data/coverage.json snapshot_date is {snapshot!r}")
    if dt.date.fromisoformat(snapshot) > dt.datetime.now(dt.UTC).date():
        raise LiveSiteError(f"/data/coverage.json snapshot_date {snapshot} is in the future")
    total = coverage.get("total_programs")
    if not isinstance(total, int) or total < MINIMUM_PROGRAMS:
        raise LiveSiteError(
            f"/data/coverage.json reports {total!r} programs, below the floor of "
            f"{MINIMUM_PROGRAMS}. A shrunken dataset is a failure, not a smaller pass."
        )
    return snapshot, total


def download_dataset(tag: str, into: Path) -> Path:
    """Fetch the release asset the live snapshot names, and check it against its digest."""
    into.mkdir(parents=True, exist_ok=True)
    command = [
        "gh",
        "release",
        "download",
        tag,
        "--dir",
        str(into),
        "--pattern",
        "*.tar.gz",
        "--pattern",
        "*.tar.gz.sha256",
        "--clobber",
    ]
    # A fixed argument vector built from a snapshot date this file already validated
    # against ^[0-9]{4}-[0-9]{2}-[0-9]{2}$. No shell.
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise LiveSiteError(
            f"`gh release download {tag}` failed, so the dataset the live site names "
            f"could not be fetched:\n{result.stdout}{result.stderr}"
        )
    tarballs = sorted(into.glob("*.tar.gz"))
    if len(tarballs) != 1:
        raise LiveSiteError(f"release {tag} carries {len(tarballs)} tarballs; expected one")
    return tarballs[0]


def verify_digest(tarball: Path) -> None:
    digest_file = tarball.with_suffix(tarball.suffix + ".sha256")
    if not digest_file.is_file():
        raise LiveSiteError(f"{tarball.name} has no published .sha256 beside it")
    expected = digest_file.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(tarball.read_bytes()).hexdigest()
    if actual != expected:
        raise LiveSiteError(f"{tarball.name} hashes to {actual}, not the published {expected}")


def extract(tarball: Path, into: Path) -> dict[str, bytes]:
    """The dataset as a path-to-bytes map, refusing any member that escapes the root."""
    if tarball.stat().st_size > MAXIMUM_TARBALL_BYTES:
        raise LiveSiteError(f"{tarball.name} exceeds the tarball size limit")
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive.getmembers():
            name = Path(member.name)
            if member.issym() or member.islnk() or name.is_absolute() or ".." in name.parts:
                raise LiveSiteError(f"{tarball.name} contains an unsafe member: {member.name}")
        archive.extractall(into, filter="data")
    files: dict[str, bytes] = {}
    for path in sorted(into.rglob("*")):
        if path.is_file():
            files[path.relative_to(into).as_posix()] = path.read_bytes()
    return files


def _compare_one(origin: Origin, nonce: str, relative: str, expected: bytes) -> str | None:
    status, live = origin.get(f"data/{relative}", nonce=nonce)
    if status != 200:
        return (
            f"data/{relative}: the live origin returned HTTP {status}; the dataset "
            f"holds {len(expected)} bytes"
        )
    if live != expected:
        return (
            f"data/{relative}: live sha256 {short(live)} ({len(live)} bytes) is not "
            f"the dataset's {short(expected)} ({len(expected)} bytes)"
        )
    return None


def compare(origin: Origin, nonce: str, files: dict[str, bytes], workers: int) -> list[str]:
    items = sorted(files.items())
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(
                lambda item: _compare_one(origin, nonce, item[0], item[1]),
                items,
            )
        )
    return [line for line in results if line is not None]


def one_pass(origin: Origin, args: argparse.Namespace) -> tuple[list[str], str, int, int]:
    """One complete look: read what the site claims, fetch that dataset, compare."""
    nonce = secrets.token_hex(16)
    prove_the_origin_discriminates(origin, nonce)
    snapshot, programs = live_coverage(origin, nonce)
    tag = f"dataset-{snapshot}"
    with tempfile.TemporaryDirectory(prefix="afterward-live-") as directory:
        work = Path(directory)
        if args.dataset:
            tarball = Path(args.dataset)
            if not tarball.is_file():
                raise LiveSiteError(f"{tarball} is not a file")
        else:
            tarball = download_dataset(tag, work / "release")
            verify_digest(tarball)
        files = extract(tarball, work / "dataset")
        if len(files) < args.minimum_files:
            raise LiveSiteError(
                f"the dataset holds {len(files)} file(s), below the floor of "
                f"{args.minimum_files}. A check that compares nothing must fail, not pass."
            )
        differences = compare(origin, nonce, files, args.workers)
    return differences, tag, len(files), programs


def validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Bounds on the knobs, so a typo cannot quietly turn the check into nothing."""
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    if not 1 <= args.attempts <= 10:
        parser.error("--attempts must be between 1 and 10")
    if not 0 <= args.retry_seconds <= 120:
        parser.error("--retry-seconds must be between 0 and 120")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=SITE_URL, help=f"live site root (default {SITE_URL})")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--dataset",
        help="a dataset tarball already on disk; without it the release the live "
        "snapshot names is downloaded with gh",
    )
    parser.add_argument(
        "--minimum-files",
        type=int,
        default=MINIMUM_FILES,
        help="refuse to pass on a smaller comparison set than this",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="parallel connections to the origin (default 8)",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="how many times to look before reporting a difference (default 3)",
    )
    parser.add_argument(
        "--retry-seconds",
        type=float,
        default=20.0,
        help="seconds to wait between attempts, for a deploy to settle (default 20)",
    )
    args = parser.parse_args(argv)
    validate(parser, args)

    origin = Origin(args.url, timeout_seconds=args.timeout_seconds)
    last_error: LiveSiteError | None = None
    differences: list[str] = []
    tag, compared, programs = "", 0, 0
    # A bounded retry, for the same reason nearmiss's live check has one: one reset
    # connection in a 3,940-request pass, or a sync still in flight, is not drift,
    # and a check that cries wolf is one people learn to ignore. A real difference
    # is still a difference on the last attempt.
    for attempt in range(1, args.attempts + 1):
        last_error = None
        try:
            differences, tag, compared, programs = one_pass(origin, args)
        except LiveSiteError as exc:
            last_error = exc
            differences = []
        if last_error is None and not differences:
            break
        if attempt < args.attempts:
            reason = last_error if last_error else f"{len(differences)} difference(s)"
            print(
                f"attempt {attempt}/{args.attempts}: {reason}; waiting "
                f"{args.retry_seconds:.0f}s in case a deploy is still settling",
                file=sys.stderr,
            )
            time.sleep(args.retry_seconds)
    origin.close()
    if last_error is not None:
        print(f"live integrity check could not run: {last_error}", file=sys.stderr)
        return EXIT_CANNOT_RUN

    if differences:
        print(
            f"{args.url} is not serving the dataset it says it is serving ({tag}).",
            file=sys.stderr,
        )
        for difference in differences[:50]:
            print(f"  {difference}", file=sys.stderr)
        if len(differences) > 50:
            print(
                f"  ... and {len(differences) - 50} more, of {compared} files compared",
                file=sys.stderr,
            )
        print(
            "\nRe-run Deploy with this dataset tag, or find out why the bucket holds "
            "something else.",
            file=sys.stderr,
        )
        return EXIT_DIFFERS

    print(
        f"{args.url} serves exactly the dataset it names: {tag}, {compared} files, "
        f"{programs} programs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
