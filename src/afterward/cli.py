"""Command line entry point."""

from __future__ import annotations

from pathlib import Path

import typer

from afterward.build import (
    CLOSE_ENOUGH_MILES,
    LINK_CACHE_DIR,
    LINK_CHECK_PATH,
    LocalHelpCoverage,
    ProviderLinkCoverage,
    build,
    build_offline,
    check_provider_links,
)
from afterward.ctdl.export import export_ctdl
from afterward.sources import link_check

app = typer.Typer(
    add_completion=False,
    help="California training-program outcomes and occupation outlook data pipeline.",
)


@app.callback()
def cli() -> None:
    """Keeps subcommand dispatch even while `build` is the only command."""


@app.command("build")
def build_command(
    state: str = typer.Option("CA", "--state", help="Two-letter state code to extract."),
    output_dir: Path = typer.Option(
        Path("data/processed"), "--output-dir", help="Where to write the emitted JSON."
    ),
    link_checks: Path = typer.Option(
        LINK_CHECK_PATH,
        "--link-checks",
        help="Provider-link report to read, if it exists. Produced by `afterward check-links`; "
        "a build that finds none publishes every link exactly as filed.",
    ),
) -> None:
    """Fetch source data, join it, and emit the site dataset."""
    typer.echo(f"Fetching {state} training programs and California occupation projections...")
    report = build(state, output_dir=output_dir, link_checks_path=link_checks)

    typer.echo(f"\nSnapshot {report.snapshot_date} -> {output_dir}")
    typer.echo(f"  programs                  {report.total_programs:>6}")
    typer.echo(f"  providers                 {report.distinct_providers:>6}")
    typer.echo(
        f"  with any outcome          {report.programs_with_any_outcome:>6}"
        f"  ({report.outcome_coverage_pct}%)"
    )
    typer.echo(f"    median earnings         {report.programs_with_median_earnings:>6}")
    typer.echo(f"    employment rate         {report.programs_with_employment_rate:>6}")
    typer.echo(f"    completion rate         {report.programs_with_completion_rate:>6}")
    typer.echo(f"  with cost                 {report.programs_with_cost:>6}")
    typer.echo(
        f"  matched to occupation     {report.programs_matched_to_occupation:>6}"
        f"  ({report.occupation_match_pct}%)"
    )
    typer.echo(f"  distinct occupations      {report.distinct_occupations_matched:>6}")

    # Occupation enrichment (CareerOneStop). All zeros is a legitimate build: with no
    # credentials configured the dataset is complete, and simply carries no descriptions.
    enrichment = report.enrichment
    typer.echo(f"\nOccupations                 {enrichment.occupations:>6}")
    typer.echo(f"  with a description        {enrichment.with_description:>6}")
    typer.echo(f"  with skills               {enrichment.with_skills:>6}")
    typer.echo(f"  with bright outlook       {enrichment.with_bright_outlook:>6}")
    typer.echo("  related occupations from")
    typer.echo(f"    O*NET                   {enrichment.related_from_onet:>6}")
    typer.echo(f"    SOC siblings            {enrichment.related_from_soc_siblings:>6}")
    typer.echo(f"    neither                 {enrichment.without_related:>6}")
    if not enrichment.enriched:
        typer.echo("  (no CareerOneStop credentials configured; enrichment skipped)")

    # Department Spanish titles (O*NET Mi Próximo Paso). A separate credential from
    # CareerOneStop's above, so it gets its own line rather than silently returning nothing
    # with no message at all -- which is what happened before this line existed.
    spanish = report.spanish
    typer.echo(f"  with a Spanish title       {spanish.with_spanish:>6}")
    if not spanish.onet_configured:
        typer.echo("  (no ONET_API_KEY configured; Spanish titles skipped)")
    elif spanish.with_spanish == 0:
        typer.echo(
            "  (ONET_API_KEY is set but returned no Spanish titles at all -- "
            "check the key and the O*NET service status before publishing this dataset)"
        )

    _echo_provider_links(report.provider_links, link_checks)
    _echo_local_help(report.local_help)


def _echo_provider_links(links: ProviderLinkCoverage, report_path: Path) -> None:
    """Say what became of the "Provider's website" links, in our own voice.

    Every line here is a count of what *this build did*, phrased as an observation. Nothing
    printed is a claim about a provider: "we could not reach" is true and checkable, "the
    site is down" would be a statement about a named organisation that this project cannot
    support, and the summary is not the place to start making one.
    """
    typer.echo(f"\nProvider links              {links.programs_with_link:>6}")
    if not links.programs_checked:
        typer.echo(f"  checked                   {0:>6}")
        typer.echo(f"  (no link report at {report_path}; every link published as filed.")
        typer.echo("   Run `afterward check-links` to establish which of them still go anywhere.)")
        return

    typer.echo(
        f"  checked                   {links.programs_checked:>6}"
        f"  ({links.checked_urls} URLs, read {links.earliest_check}"
        + (f" to {links.latest_check}" if links.latest_check != links.earliest_check else "")
        + ")"
    )
    typer.echo(f"    answered                {links.programs_alive:>6}")
    typer.echo(f"    we could not reach      {links.programs_dead:>6}")
    typer.echo(f"    could not be judged     {links.programs_indeterminate:>6}")
    if links.programs_unchecked:
        typer.echo(f"  not checked               {links.programs_unchecked:>6}")
    typer.echo(f"  published as a link       {links.programs_linked:>6}")
    typer.echo(f"    upgraded to https       {links.programs_upgraded_to_https:>6}")
    typer.echo(f"    sent to the front page  {links.programs_sent_to_front_page:>6}")
    typer.echo(f"  published without a link  {links.programs_not_linked:>6}")


def _echo_local_help(centers: LocalHelpCoverage) -> None:
    """Say how many pages can name a real office, and never imply one that was not looked for.

    A build with no credentials prints the directory line as "not read" rather than as 0.
    "We did not look" and "California has no job centres" are different sentences, and the
    summary is where an operator decides whether the dataset they just built is one worth
    publishing.
    """
    if centers.centers_loaded is None:
        typer.echo("\nAmerica's Job Centers     not read")
        typer.echo("  (no CareerOneStop credentials configured, or the finder could not be")
        typer.echo("   reached; no program page in this dataset claims a nearby office)")
        return

    def row(label: str, value: int) -> None:
        typer.echo(f"  {label:<24}{value:>6}")

    radius = int(centers.radius_miles)
    typer.echo(f"\nAmerica's Job Centers       {centers.centers_loaded:>6}")
    row(f"pages with one, {radius} mi", centers.programs_with_a_center)
    row(f"  within {int(CLOSE_ENOUGH_MILES)} miles", centers.programs_with_a_center_within_10_miles)
    row("  a comprehensive one", centers.programs_with_a_comprehensive_center)
    row("none that close", centers.programs_with_none_within_radius)
    if centers.programs_not_searched:
        row("no coordinates to search", centers.programs_not_searched)
    if centers.nearest_median_miles is not None:
        typer.echo(
            f"  median distance {centers.nearest_median_miles} miles, straight line"
            f" (farthest {centers.nearest_farthest_miles})"
        )


@app.command("check-links")
def check_links_command(
    dataset_dir: Path = typer.Option(
        Path("data/processed"),
        "--dataset-dir",
        help="Emitted dataset whose programs.json supplies the URLs to check.",
    ),
    output: Path = typer.Option(
        LINK_CHECK_PATH, "--output", help="Where to leave the report for the next build."
    ),
    cache_dir: Path = typer.Option(
        LINK_CACHE_DIR,
        "--cache-dir",
        help="On-disk cache of per-URL verdicts. Safe to delete; deleting it only costs a "
        "re-check.",
    ),
    max_workers: int = typer.Option(
        link_check.MAX_WORKERS,
        "--max-workers",
        help="Providers read at once. Never two requests to one provider at a time.",
    ),
) -> None:
    """Ask each provider URL in the dataset whether it still goes anywhere.

    Deliberately separate from `build`, and deliberately not run by it. This spends one
    request per provider address -- roughly 1,100 -- on small colleges and adult schools,
    each of them serving at most the front of one page, so it belongs to a person who
    decided to spend them -- on a quarterly refresh cadence, not on every build. Results are
    cached per URL, so a re-run asks only about what has expired.

    Nothing here changes the dataset. It writes a report; the next `afterward build` reads it.
    """
    typer.echo(f"Reading provider links from {dataset_dir}/programs.json...")
    seen = 0

    def progress(_: link_check.LinkCheck) -> None:
        nonlocal seen
        seen += 1
        if seen % 100 == 0:
            typer.echo(f"  {seen} URLs read")

    run = check_provider_links(
        dataset_dir,
        output_path=output,
        cache_dir=cache_dir,
        max_workers=max_workers,
        on_result=progress,
    )

    typer.echo(f"\n{run.urls} provider URLs on {run.pages} program pages -> {run.output_path}")
    wordings: tuple[tuple[link_check.Verdict, str], ...] = (
        ("alive", "answered"),
        ("dead", "we could not reach"),
        ("indeterminate", "could not be judged"),
    )
    for verdict, wording in wordings:
        urls = run.by_verdict.get(verdict, 0)
        pages = run.pages_by_verdict.get(verdict, 0)
        typer.echo(f"  {wording:<22}{urls:>6} URLs {pages:>6} pages")
    typer.echo(
        f"  {'http upgradeable':<22}{run.upgradeable_urls:>6} URLs {run.upgradeable_pages:>6} pages"
    )
    typer.echo(f"\n  front pages read for the 404s   {run.front_pages_checked:>6}")
    typer.echo(f"  HTTP requests these results cost  {run.recorded_requests:>6} (cached entries")
    typer.echo("    carry the cost of the run that made them, not of this one)")
    typer.echo("\nRun `afterward build` again to publish with these results.")


@app.command("build-offline")
def build_offline_command(
    fixture_dir: Path = typer.Option(
        Path("fixtures/data"), "--fixture-dir", help="Committed fixture to build from."
    ),
    output_dir: Path = typer.Option(
        Path("web/public/data"), "--output-dir", help="Where to write the emitted JSON."
    ),
) -> None:
    """Emit the site dataset from the committed fixture, without touching the network."""
    count = build_offline(fixture_dir, output_dir=output_dir)
    typer.echo(f"Built {count} fixture programs from {fixture_dir} -> {output_dir}")


@app.command("export-ctdl")
def export_ctdl_command(
    dataset_dir: Path = typer.Option(
        Path("web/public/data"),
        "--dataset-dir",
        help="Emitted dataset to project; the same files the site serves.",
    ),
    output_dir: Path = typer.Option(
        Path("dist/ctdl"), "--output-dir", help="Where to write the JSON-LD and its coverage."
    ),
) -> None:
    """Project the emitted dataset into CTDL JSON-LD (a demonstration export).

    Reads the dataset the site serves and writes a CTDL JSON-LD graph beside a coverage
    statement counted from that graph. Nothing is published to any registry, and the CTIDs
    are derived locally rather than Registry-assigned. Deterministic: the same dataset
    always produces byte-identical output.
    """
    report = export_ctdl(dataset_dir, output_dir)
    typer.echo(f"Snapshot {report.snapshot_date} -> {report.document_path}")
    typer.echo(f"  ceterms:LearningProgram          {report.programs:>6}")
    typer.echo(f"  ceterms:CredentialOrganization   {report.organizations:>6}")
    typer.echo("  programs carrying")
    for term, count in report.property_counts.items():
        typer.echo(f"    {term:<30}{count:>6}")
    typer.echo(f"  coverage statement -> {report.coverage_path}")
    typer.echo("\nDemonstration export: not published to any registry; CTIDs are locally derived.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
