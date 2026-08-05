#!/usr/bin/env python3
"""Fail the build if excluded-reference terms appear outside the provenance allowlist.

This enforces the clean-room constraint recorded in PROVENANCE.md: this project must not be
derived from, or reference, the New Jersey workforce products the author previously worked
on as a vendor employee. The check is deliberately blunt -- a substring scan over tracked
text -- because a mechanical guard that cannot be argued with is the point.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files permitted to discuss the exclusion itself.
ALLOWLIST = {
    "PROVENANCE.md",
    "scripts/provenance_check.py",
    "tests/test_provenance_check.py",
    "docs/design-log.md",
}

# Word-boundary patterns. Kept narrow enough to avoid false hits on ordinary English
# ("nj" inside a word, "afterward" containing no trigger) while catching real references.
PATTERNS = [
    re.compile(r"\bmcnj\b", re.I),
    re.compile(r"\bmy\s*career\s*nj\b", re.I),
    re.compile(r"\bmycareer\.nj\b", re.I),
    re.compile(r"\bd4ad\b", re.I),
    re.compile(r"\bnj\.gov\b", re.I),
    re.compile(r"\bnewjersey/", re.I),
    re.compile(r"\bnew\s+jersey\b", re.I),
]

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".cfg",
    ".ini",
    ".sh",
    ".mk",
    ".po",
    ".pot",
}


# Never scanned: third-party code we did not write. Without this the fallback path walks
# .venv and trips over unrelated strings such as the SPDX name "Standard ML of New Jersey".
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "data",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "STANDARDS",
}


def tracked_files() -> list[Path]:
    """Return git-tracked files, falling back to a filtered walk before the first commit."""
    try:
        # Fixed argv, no shell, no user input: the only variable is this file's own repo root.
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(REPO_ROOT), "ls-files"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        paths = [REPO_ROOT / line for line in out.splitlines() if line]
        if paths:
            return paths
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return [
        p
        for p in REPO_ROOT.rglob("*")
        if p.is_file() and not EXCLUDED_DIRS.intersection(p.relative_to(REPO_ROOT).parts)
    ]


def scan() -> list[tuple[str, int, str]]:
    violations: list[tuple[str, int, str]] = []
    for path in tracked_files():
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWLIST or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in PATTERNS:
                if pattern.search(line):
                    violations.append((rel, lineno, line.strip()[:120]))
                    break
    return violations


def main() -> int:
    violations = scan()
    if not violations:
        print(f"provenance-check: clean ({len(tracked_files())} files scanned)")
        return 0
    print("provenance-check: FAILED -- excluded reference(s) found\n", file=sys.stderr)
    for rel, lineno, line in violations:
        print(f"  {rel}:{lineno}: {line}", file=sys.stderr)
    print(
        "\nThis project must not reference or derive from the excluded prior work."
        "\nSee PROVENANCE.md. If a mention is genuinely required, justify it there.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
