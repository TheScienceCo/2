"""ORM models.

Deliberately small. The full analysis document is a self-contained blob written
once and read whole, so it lives in a JSONB column rather than being shredded
across a dozen tables. What *is* broken out into columns is exactly what we need
to query across replays: who played, what they picked, and when they aged up —
the inputs to peer comparison.

Adding a column here means committing to computing it for every replay. Metrics
that a replay cannot always answer (production timings, anything about combat)
stay inside `analysis` where their `availability` travels with them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin

#: JSONB on Postgres, plain JSON elsewhere so the test suite can run on SQLite.
JSONDoc = JSON().with_variant(JSONB(), "postgresql")


class Replay(Base, TimestampMixin):
    """One analysed replay file."""

    __tablename__ = "replays"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: SHA-256 of the uploaded bytes. De-duplicates re-uploads of the same file.
    replay_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)

    map_name: Mapped[str | None] = mapped_column(String(255))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    game_version: Mapped[str | None] = mapped_column(String(50))

    #: The complete analysis document, as returned by the API.
    analysis: Mapped[dict] = mapped_column(JSONDoc, nullable=False, default=dict)

    players: Mapped[list[ReplayPlayer]] = relationship(
        back_populates="replay", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_replays_created_at", "created_at"),)


class ReplayPlayer(Base):
    """One player's participation, flattened for cross-replay queries."""

    __tablename__ = "replay_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    replay_pk: Mapped[int] = mapped_column(
        ForeignKey("replays.id", ondelete="CASCADE"), nullable=False
    )

    player_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    civilization: Mapped[str] = mapped_column(String(100), nullable=False)
    winner: Mapped[bool | None] = mapped_column(Boolean)

    #: Age timings in ms, or NULL where the player never reached that age.
    feudal_ms: Mapped[int | None] = mapped_column(Integer)
    castle_ms: Mapped[int | None] = mapped_column(Integer)
    imperial_ms: Mapped[int | None] = mapped_column(Integer)
    eapm: Mapped[int | None] = mapped_column(Integer)
    opening: Mapped[str | None] = mapped_column(String(50))

    replay: Mapped[Replay] = relationship(back_populates="players")

    __table_args__ = (
        Index("ix_replay_players_name", "name"),
        Index("ix_replay_players_civilization", "civilization"),
    )


# ---------------------------------------------------------------------------
# External baseline corpus (aoestats.io)
# ---------------------------------------------------------------------------


class CorpusMatch(Base, TimestampMixin):
    """One match from an external dump.

    Kept separate from `replays` on purpose. These rows are someone else's
    derivation of someone else's games; conflating them with replays we parsed
    ourselves is how external inference gets served as our measurement.
    """

    __tablename__ = "corpus_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    map_name: Mapped[str | None] = mapped_column(String(120), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    num_players: Mapped[int] = mapped_column(Integer, nullable=False)
    leaderboard: Mapped[str | None] = mapped_column(String(60), index=True)
    game_type: Mapped[str | None] = mapped_column(String(60))
    game_speed: Mapped[str | None] = mapped_column(String(30))
    starting_age: Mapped[str | None] = mapped_column(String(30))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    #: INFERRED, not observed: attributed from the start time, not read from a
    #: replay header.
    patch: Mapped[str | None] = mapped_column(String(40), index=True)
    #: True when the row sits within the uncertainty window of a patch boundary.
    patch_low_confidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: Only replay-enhanced rows carry age timings and the summary blob.
    replay_enhanced: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    #: True for generated data. Never let a synthetic-backed baseline pass as real.
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    source: Mapped[str] = mapped_column(String(60), nullable=False, default="aoestats.io")
    source_range: Mapped[str | None] = mapped_column(String(40))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    players: Mapped[list[CorpusPlayer]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class CorpusPlayer(Base):
    """One player's row in an external dump."""

    __tablename__ = "corpus_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_pk: Mapped[int] = mapped_column(
        ForeignKey("corpus_matches.id", ondelete="CASCADE"), nullable=False
    )
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    civ: Mapped[str | None] = mapped_column(String(60), index=True)
    winner: Mapped[bool | None] = mapped_column(Boolean)
    team: Mapped[int | None] = mapped_column(Integer)
    old_rating: Mapped[float | None] = mapped_column(Float, index=True)
    new_rating: Mapped[float | None] = mapped_column(Float)
    #: Lower edge of the Elo band `old_rating` falls in; the ladder stratifier.
    elo_band: Mapped[int | None] = mapped_column(Integer, index=True)

    #: EXTERNAL_DERIVED - the publisher's pipeline computed these, not ours.
    feudal_age_uptime: Mapped[float | None] = mapped_column(Float)
    castle_age_uptime: Mapped[float | None] = mapped_column(Float)
    imperial_age_uptime: Mapped[float | None] = mapped_column(Float)
    #: EXTERNAL_LABEL - a stratifier, never ground truth.
    opening: Mapped[str | None] = mapped_column(String(60), index=True)
    #: Raw per-age counts, parsed into spend metrics downstream.
    replay_summary_raw: Mapped[str | None] = mapped_column(Text)

    replay_enhanced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    match: Mapped[CorpusMatch] = relationship(back_populates="players")

    __table_args__ = (
        UniqueConstraint("game_id", "profile_id", name="uq_corpus_player"),
        Index("ix_corpus_players_band_civ", "elo_band", "civ"),
    )


class CorpusRejection(Base, TimestampMixin):
    """A row the cleaning pass refused, and why.

    Every drop is recorded. A pipeline that discards input silently will report
    healthy baselines built on a fraction of the data.
    """

    __tablename__ = "corpus_rejections"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    source_range: Mapped[str | None] = mapped_column(String(40), index=True)


class CohortBaseline(Base, TimestampMixin):
    """A peer baseline for one metric within one cohort.

    `source` is mandatory and never silently blended: a baseline drawn from the
    external corpus and one drawn from our own replays answer subtly different
    questions, and a reader has to be able to tell which they are looking at.
    """

    __tablename__ = "cohort_baselines"

    id: Mapped[int] = mapped_column(primary_key=True)

    metric: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    #: EXTERNAL_CORPUS | OWN_REPLAYS | BLENDED
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    #: The cohort's dimensions, e.g. {"elo_band": 1400, "civ": "Franks"}.
    dimensions: Mapped[dict] = mapped_column(JSONDoc, nullable=False, default=dict)
    #: How many dimensions are pinned; lookups start specific and fall back.
    specificity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Rows contributing to this baseline. For metrics that need replay-enhanced
    #: rows this is smaller than the cohort's match count, which is why it is
    #: recorded separately rather than inferred.
    n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean: Mapped[float | None] = mapped_column(Float)
    std: Mapped[float | None] = mapped_column(Float)
    p10: Mapped[float | None] = mapped_column(Float)
    p25: Mapped[float | None] = mapped_column(Float)
    p50: Mapped[float | None] = mapped_column(Float)
    p75: Mapped[float | None] = mapped_column(Float)
    p90: Mapped[float | None] = mapped_column(Float)

    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("metric", "source", "specificity", "cohort_key", name="uq_baseline_cell"),
        Index("ix_baseline_lookup", "metric", "source", "specificity"),
    )

    #: Stable hash of `dimensions`, so the uniqueness constraint can key on it.
    cohort_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")


__all__ = [
    "Base",
    "CohortBaseline",
    "CorpusMatch",
    "CorpusPlayer",
    "CorpusRejection",
    "Replay",
    "ReplayPlayer",
]
