"""Stage 0: load an external dump into Postgres.

Runs independently of per-replay processing. The order is deliberate - inspect
the schema, clean, record every rejection, then write - so that a dump with an
unexpected shape fails at inspection rather than half-populating the corpus.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import CorpusMatch, CorpusPlayer, CorpusRejection
from app.services.corpus.clean import clean
from app.services.corpus.schema import SchemaReport, inspect_columns

log = get_logger(__name__)

#: Elo band lower edges. A rating lands in the highest band it clears.
ELO_BAND_EDGES = (0, 1000, 1200, 1400, 1600, 1800, 2000)

#: A match started within this of a patch release cannot be confidently
#: attributed to either side of the boundary.
PATCH_UNCERTAINTY = timedelta(hours=48)


def elo_band(rating: float | None) -> int | None:
    """The band a rating falls in, by lower edge. None stays None."""
    if rating is None or pd.isna(rating):
        return None
    band = ELO_BAND_EDGES[0]
    for edge in ELO_BAND_EDGES:
        if rating >= edge:
            band = edge
    return band


@dataclass
class IngestReport:
    source_range: str
    schema_matches: SchemaReport | None = None
    schema_players: SchemaReport | None = None
    matches_written: int = 0
    players_written: int = 0
    rejections_written: int = 0
    match_retention: float = 0.0
    player_retention: float = 0.0
    replay_enhanced_share: float = 0.0
    patch_low_confidence: int = 0
    synthetic: bool = False
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        tag = " [SYNTHETIC]" if self.synthetic else ""
        return (
            f"{self.source_range}{tag}: {self.matches_written} matches, "
            f"{self.players_written} players "
            f"({self.match_retention:.1%}/{self.player_retention:.1%} retained), "
            f"replay-enhanced {self.replay_enhanced_share:.1%}, "
            f"{self.rejections_written} rejections {self.rejection_reasons or ''}"
        )


def _read(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _flag_patch_confidence(started: pd.Series, patch_dates: Sequence[date] | None) -> pd.Series:
    """Mark rows too close to a patch release to attribute confidently.

    Without a patch calendar no boundary can be located, so nothing is flagged
    and `corpus status` reports that boundary detection was unavailable - which
    is different from reporting that every row is confident.
    """
    if not patch_dates:
        return pd.Series(False, index=started.index)

    stamps = pd.to_datetime(started, utc=True, errors="coerce")
    flags = pd.Series(False, index=started.index)
    for boundary in patch_dates:
        moment = pd.Timestamp(boundary, tz="UTC")
        flags |= (stamps - moment).abs() <= PATCH_UNCERTAINTY
    return flags.fillna(False)


def ingest_dump(
    session: Session,
    matches_path: str | Path,
    players_path: str | Path,
    *,
    source: str = "aoestats.io",
    source_range: str = "unknown",
    fetched_at: datetime | None = None,
    patch_dates: Sequence[date] | None = None,
    replace: bool = True,
) -> IngestReport:
    """Load one dump. Returns what happened, including everything dropped."""
    matches_raw = _read(matches_path)
    players_raw = _read(players_path)

    report = IngestReport(source_range=source_range)
    report.schema_matches = inspect_columns(list(matches_raw.columns))
    report.schema_players = inspect_columns(list(players_raw.columns))

    # Required columns are split across the two files, so neither report is
    # complete alone; a name missing from both is what actually blocks ingest.
    present = set(matches_raw.columns) | set(players_raw.columns)
    combined = inspect_columns(sorted(present))
    if not combined.usable:
        raise ValueError(
            f"dump is missing required columns: {', '.join(combined.missing_required)}"
        )

    matches_df, players_df, cleaning = clean(matches_raw, players_raw)
    report.match_retention = cleaning.match_retention
    report.player_retention = cleaning.player_retention
    report.rejection_reasons = cleaning.by_reason()

    synthetic = bool(matches_df.get("synthetic", pd.Series([False])).any())
    report.synthetic = synthetic

    if replace:
        existing = session.scalars(
            select(CorpusMatch.id).where(CorpusMatch.source_range == source_range)
        ).all()
        if existing:
            # Delete children explicitly. A bulk DELETE bypasses the ORM's
            # cascade, and SQLite does not enforce ON DELETE without the
            # foreign_keys pragma - so relying on either would leave orphaned
            # player rows that then collide on re-ingest.
            session.execute(delete(CorpusPlayer).where(CorpusPlayer.match_pk.in_(existing)))
            session.execute(delete(CorpusMatch).where(CorpusMatch.id.in_(existing)))
            session.execute(
                delete(CorpusRejection).where(CorpusRejection.source_range == source_range)
            )
            session.flush()

    when = fetched_at or datetime.now(UTC)
    low_conf = _flag_patch_confidence(
        matches_df.get("started_timestamp", pd.Series(index=matches_df.index, dtype="object")),
        patch_dates,
    )

    by_game: dict[str, CorpusMatch] = {}
    for position, row in enumerate(matches_df.itertuples(index=False)):
        game_id = str(row.game_id)
        started = getattr(row, "started_timestamp", None)
        record = CorpusMatch(
            game_id=game_id,
            map_name=_opt_str(getattr(row, "map", None)),
            duration_seconds=int(row.duration),
            num_players=int(row.num_players),
            leaderboard=_opt_str(getattr(row, "leaderboard", None)),
            game_type=_opt_str(getattr(row, "game_type", None)),
            game_speed=_opt_str(getattr(row, "game_speed", None)),
            starting_age=_opt_str(getattr(row, "starting_age", None)),
            started_at=_opt_datetime(started),
            patch=_opt_str(getattr(row, "patch", None)),
            patch_low_confidence=bool(low_conf.iloc[position]) if len(low_conf) else False,
            replay_enhanced=bool(getattr(row, "replay_enhanced", False)),
            synthetic=synthetic,
            source=source,
            source_range=source_range,
            fetched_at=when,
        )
        by_game[game_id] = record
        session.add(record)
    session.flush()

    enhanced_rows = 0
    for row in players_df.itertuples(index=False):
        game_id = str(row.game_id)
        parent = by_game.get(game_id)
        if parent is None:
            continue
        rating = _opt_float(getattr(row, "old_rating", None))
        is_enhanced = bool(getattr(row, "replay_enhanced", False))
        enhanced_rows += int(is_enhanced)
        session.add(
            CorpusPlayer(
                match_pk=parent.id,
                game_id=game_id,
                profile_id=str(row.profile_id),
                civ=_opt_str(getattr(row, "civ", None)),
                winner=_opt_bool(getattr(row, "winner", None)),
                team=_opt_int(getattr(row, "team", None)),
                old_rating=rating,
                new_rating=_opt_float(getattr(row, "new_rating", None)),
                elo_band=elo_band(rating),
                feudal_age_uptime=_opt_float(getattr(row, "feudal_age_uptime", None)),
                castle_age_uptime=_opt_float(getattr(row, "castle_age_uptime", None)),
                imperial_age_uptime=_opt_float(getattr(row, "imperial_age_uptime", None)),
                opening=_opt_str(getattr(row, "opening", None)),
                replay_summary_raw=_opt_str(getattr(row, "replay_summary_raw", None)),
                replay_enhanced=is_enhanced,
                synthetic=synthetic,
            )
        )

    for rejection in cleaning.rejections:
        session.add(
            CorpusRejection(
                game_id=rejection.game_id,
                profile_id=rejection.profile_id,
                reason=rejection.reason.value,
                detail=rejection.detail,
                source_range=source_range,
            )
        )

    session.commit()

    report.matches_written = len(by_game)
    report.players_written = len(players_df)
    report.rejections_written = len(cleaning.rejections)
    report.replay_enhanced_share = (
        enhanced_rows / report.players_written if report.players_written else 0.0
    )
    report.patch_low_confidence = int(low_conf.sum()) if len(low_conf) else 0

    log.info("corpus.ingested", **{"range": source_range, "summary": report.summary()})
    return report


def _opt_str(value: object) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return str(value)


def _opt_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)  # type: ignore[arg-type]


def _opt_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)  # type: ignore[call-overload]


def _opt_bool(value: object) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return bool(value)


def _opt_datetime(value: object) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    stamp = pd.Timestamp(value)  # type: ignore[arg-type]
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime()
