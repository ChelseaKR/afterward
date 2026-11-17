"""How IndexNow is wired into the deploy (ADR 0004), checked against the files themselves.

`tests/test_indexnow.py` covers the shared module. This covers what is particular to
Afterward: the key file the export publishes, where in the deploy the selection runs, and
that the job which sends it holds nothing the deploy job holds.
"""

from __future__ import annotations

import re
from pathlib import Path

from afterward import indexnow as ix

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC = REPO_ROOT / "web" / "public"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


def _deploy_text() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def _job(name: str) -> str:
    """The text of one job, from its key to the next top-level job key."""
    text = _deploy_text()
    jobs = text.split("\njobs:\n", 1)[1]
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", jobs, re.M | re.S)
    assert match, f"no job {name!r} in deploy.yml"
    return match.group(1)


def test_the_export_publishes_exactly_one_key_file_at_the_site_root() -> None:
    """`web/public` is copied to the export root, which is where IndexNow looks for it."""
    key = ix.find_key(PUBLIC)
    assert re.fullmatch(r"[0-9a-f]{32}", key)


def test_selection_runs_after_the_sitemap_is_dated_and_before_the_upload() -> None:
    """Before the upload, because the live sitemap is the previous deploy's; after the
    lastmod step, because its <lastmod> is what says which pages changed."""
    steps = re.findall(r"^      - name: (.+)$", _job("deploy"), re.M)
    pick = steps.index("Pick the pages to announce to IndexNow")
    assert steps.index("Date the sitemap from the pages that actually changed") < pick
    assert pick < steps.index("Upload to S3")
    assert steps[pick + 1] == "Keep the IndexNow list for the job after the deploy"


def test_selection_diffs_the_sitemap_of_this_host() -> None:
    job = _job("deploy")
    assert "python3 src/afterward/indexnow.py select" in job
    assert "--site-dir web/out" in job
    assert '--base-url "${SITE_URL}"' in job
    assert "--kind sitemap --file sitemap.xml" in job
    # A live sitemap it cannot read means "unknown", so nothing is sent; a 404 is not
    # allowed to stand for "every page is new" on a site that has had a sitemap for months.
    assert "--missing-is-empty" not in job


def test_the_submit_job_runs_only_after_the_deploy_and_holds_nothing() -> None:
    job = _job("indexnow")
    assert re.search(r"^    needs: deploy$", job, re.M)
    permissions = re.search(r"^    permissions:\n((?:      .*\n)+)", job, re.M)
    assert permissions, "the job must set its own permissions, not inherit id-token: write"
    assert permissions.group(1).strip() == "contents: read"
    for forbidden in (
        "id-token",
        "secrets.",
        "environment:",
        "configure-aws-credentials",
        "role-to-assume",
        "aws ",
    ):
        assert forbidden not in job, forbidden
    assert "persist-credentials: false" in job
    assert "python3 src/afterward/indexnow.py submit" in job


def test_no_permission_is_granted_at_the_workflow_level() -> None:
    """A workflow-level grant reaches every job; the OIDC grant belongs to the deploy job."""
    assert re.search(r"^permissions: \{\}$", _deploy_text(), re.M)
    assert "id-token: write" in _job("deploy")


def test_the_module_the_workflow_calls_by_path_is_stdlib_only() -> None:
    """The submit job checks out this one file and runs it with the runner's python3."""
    source = (REPO_ROOT / "src" / "afterward" / "indexnow.py").read_text(encoding="utf-8")
    imports = re.findall(r"^(?:from|import) ([\w.]+)", source, re.M)
    assert "afterward" not in {name.split(".")[0] for name in imports}
