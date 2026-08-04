"""Command line entry point."""

from __future__ import annotations

from pathlib import Path

import typer

from camino.build import build, build_offline

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
) -> None:
    """Fetch source data, join it, and emit the site dataset."""
    typer.echo(f"Fetching {state} training programs and California occupation projections...")
    report = build(state, output_dir=output_dir)

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
