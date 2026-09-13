"""Command-line interface for corpus and validation operations."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from app.core.logging import get_logger
from app.services.analysis.validate import validate_parser
from app.services.corpus.ingest import IngestService
from app.services.sources.aoestats import AoestatsSource

log = get_logger(__name__)


@click.group()
def cli():
    """AoE2 Lab command-line utilities."""
    pass


@cli.command()
@click.option(
    "--start-date",
    type=str,
    help="Start date (YYYY-MM-DD) for corpus range",
)
@click.option(
    "--end-date",
    type=str,
    help="End date (YYYY-MM-DD) for corpus range",
)
@click.option("--limit", type=int, default=100, help="Max matches to ingest")
@click.option("--force", is_flag=True, help="Re-ingest matches already stored")
def corpus_status(start_date: str | None, end_date: str | None, limit: int, force: bool):
    """Check corpus ingestion status and progress.

    Shows how many replays are in the local corpus, coverage by player rating,
    rejection statistics, and patch coverage.
    """
    from app.db.session import get_session

    session = next(get_session())

    # Query corpus stats
    n_matches = session.query(CorpusMatch).count()
    n_players = session.query(CorpusPlayer).select_distinct("profile_id").count()
    n_rejections = session.query(CorpusRejection).count()

    click.echo(f"Corpus Status:")
    click.echo(f"  Matches:     {n_matches:>6}")
    click.echo(f"  Players:     {n_players:>6}")
    click.echo(f"  Rejections:  {n_rejections:>6}")

    # Show rejection breakdown
    rejection_reasons = (
        session.query(CorpusRejection.reason, func.count())
        .group_by(CorpusRejection.reason)
        .all()
    )
    if rejection_reasons:
        click.echo("\n  Rejection breakdown:")
        for reason, count in rejection_reasons:
            click.echo(f"    {reason:.<30} {count:>5}")

    session.close()


@cli.command()
@click.argument("replay_file", type=click.Path(exists=True))
@click.option("--corpus-file", type=click.Path(), help="Compare against corpus JSON")
def validate_parser_cmd(replay_file: str, corpus_file: str | None):
    """Validate parser output against aoestats.io baseline.

    Compares computed age timings (feudal, castle, imperial) against the corpus
    and reports MAE (mean absolute error) and systematic bias.

    Example:
        aoe2lab validate-parser replays/sample.aoe2record --corpus-file corpus.json
    """
    from app.services.parser.mgz_parser import MgzParser

    try:
        parser = MgzParser()
        parsed = parser.parse(Path(replay_file))

        click.echo(f"Parsed {replay_file}")
        click.echo(f"  Feudal:  {parsed.match_players[0].age_timings_ms.get('feudal', 'N/A')}ms")
        click.echo(f"  Castle:  {parsed.match_players[0].age_timings_ms.get('castle', 'N/A')}ms")
        click.echo(f"  Imperial: {parsed.match_players[0].age_timings_ms.get('imperial', 'N/A')}ms")

        if corpus_file:
            # Load and compare against corpus baseline
            import json

            with open(corpus_file) as f:
                corpus_data = json.load(f)

            click.echo("\nComparison against corpus:")
            for age in ["feudal", "castle", "imperial"]:
                ours = parsed.match_players[0].age_timings_ms.get(age)
                baseline = corpus_data.get(age)
                if ours and baseline:
                    error = ours - baseline
                    error_pct = 100.0 * error / baseline
                    click.echo(f"  {age:8s}: ours={ours:>6}ms, "
                             f"baseline={baseline:>6}ms, error={error:+6.0f}ms ({error_pct:+5.1f}%)")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
