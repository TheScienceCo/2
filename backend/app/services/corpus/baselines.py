"""Peer baselines, computed from the corpus.

`source` is recorded on every row and the sources are never silently blended.
A baseline from the external corpus and one from our own replays answer subtly
different questions - different populations, different derivations - and a
reader has to be able to tell which they are looking at. When both exist for a
cell, the external corpus supplies `n` and ours is available as a consistency
check.

Specificity lets a lookup start at the most specific cohort that has enough
samples and fall back: `{elo_band, civ, map}` before `{elo_band, civ}` before
`{elo_band}`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import CohortBaseline, CorpusMatch, CorpusPlayer

log = get_logger(__name__)

#: Below this a cell is too small to be a baseline; the lookup falls back.
MIN_COHORT_N = 30


class BaselineSource(StrEnum):
    EXTERNAL_CORPUS = "EXTERNAL_CORPUS"
    OWN_REPLAYS = "OWN_REPLAYS"
    BLENDED = "BLENDED"


#: Cohort shapes, most specific first.
COHORT_SHAPES: tuple[tuple[str, ...], ...] = (
    ("elo_band", "civ", "map_name"),
    ("elo_band", "civ"),
    ("elo_band", "map_name"),
    ("elo_band",),
)

#: Metrics drawn straight from the corpus columns.
CORPUS_METRICS = ("feudal_age_uptime", "castle_age_uptime", "imperial_age_uptime")


def cohort_key(dimensions: dict) -> str:
    """A stable key for a cohort's dimensions."""
    payload = json.dumps(dimensions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


@dataclass
class BaselineReport:
    written: int = 0
    skipped_small: int = 0
    metrics: tuple[str, ...] = ()
    synthetic: bool = False

    def summary(self) -> str:
        tag = " [SYNTHETIC]" if self.synthetic else ""
        return (
            f"{self.written} baseline cells written{tag}, "
            f"{self.skipped_small} cells below n={MIN_COHORT_N}"
        )


def corpus_frame(session: Session, *, replay_enhanced_only: bool = True) -> pd.DataFrame:
    """Player rows joined to their match, as a frame."""
    query = select(
        CorpusPlayer.game_id,
        CorpusPlayer.profile_id,
        CorpusPlayer.civ,
        CorpusPlayer.winner,
        CorpusPlayer.old_rating,
        CorpusPlayer.elo_band,
        CorpusPlayer.opening,
        CorpusPlayer.feudal_age_uptime,
        CorpusPlayer.castle_age_uptime,
        CorpusPlayer.imperial_age_uptime,
        CorpusPlayer.replay_summary_raw,
        CorpusPlayer.replay_enhanced,
        CorpusPlayer.synthetic,
        CorpusMatch.map_name,
        CorpusMatch.duration_seconds,
        CorpusMatch.patch_low_confidence,
    ).join(CorpusMatch, CorpusPlayer.match_pk == CorpusMatch.id)

    if replay_enhanced_only:
        query = query.where(CorpusPlayer.replay_enhanced.is_(True))

    rows = session.execute(query).all()
    return pd.DataFrame(rows, columns=list(query.selected_columns.keys()))


def rebuild_baselines(
    session: Session,
    *,
    source: BaselineSource = BaselineSource.EXTERNAL_CORPUS,
    exclude_low_confidence_patch: bool = True,
) -> BaselineReport:
    """Recompute baselines for every cohort shape from corpus data."""
    frame = corpus_frame(session, replay_enhanced_only=True)
    report = BaselineReport(metrics=CORPUS_METRICS)
    if frame.empty:
        log.warning("baselines.no_corpus_rows")
        return report

    if exclude_low_confidence_patch and "patch_low_confidence" in frame:
        frame = frame[~frame["patch_low_confidence"].fillna(False)]

    report.synthetic = bool(frame["synthetic"].any())

    session.execute(delete(CohortBaseline).where(CohortBaseline.source == source.value))

    for metric in CORPUS_METRICS:
        if metric not in frame:
            continue
        usable = frame[frame[metric].notna()]
        if usable.empty:
            continue

        for shape in COHORT_SHAPES:
            if any(dimension not in usable for dimension in shape):
                continue
            for values, group in usable.groupby(list(shape), dropna=True):
                series = group[metric].astype(float)
                # n is the count of rows that actually carry this metric, which
                # is smaller than the cohort's match count - recorded, not inferred.
                if len(series) < MIN_COHORT_N:
                    report.skipped_small += 1
                    continue
                dimensions = dict(
                    zip(shape, values if isinstance(values, tuple) else (values,), strict=True)
                )
                dimensions = {k: _plain(v) for k, v in dimensions.items()}
                session.add(
                    CohortBaseline(
                        metric=metric,
                        source=source.value,
                        dimensions=dimensions,
                        cohort_key=cohort_key(dimensions),
                        specificity=len(shape),
                        n=len(series),
                        mean=float(series.mean()),
                        std=float(series.std(ddof=1)) if len(series) > 1 else None,
                        p10=float(series.quantile(0.10)),
                        p25=float(series.quantile(0.25)),
                        p50=float(series.quantile(0.50)),
                        p75=float(series.quantile(0.75)),
                        p90=float(series.quantile(0.90)),
                        synthetic=report.synthetic,
                    )
                )
                report.written += 1

    session.commit()
    log.info("baselines.rebuilt", summary=report.summary())
    return report


def lookup(
    session: Session,
    metric: str,
    dimensions: dict,
    *,
    source: BaselineSource = BaselineSource.EXTERNAL_CORPUS,
) -> CohortBaseline | None:
    """The most specific baseline available for these dimensions.

    Falls back to broader cohorts rather than returning nothing, since a
    less-specific comparison is more useful than none - the caller can read
    `specificity` to see how much conditioning survived.
    """
    for shape in COHORT_SHAPES:
        if not all(d in dimensions for d in shape):
            continue
        subset = {d: _plain(dimensions[d]) for d in shape}
        found = session.scalar(
            select(CohortBaseline).where(
                CohortBaseline.metric == metric,
                CohortBaseline.source == source.value,
                CohortBaseline.cohort_key == cohort_key(subset),
            )
        )
        if found is not None:
            return found
    return None


def _plain(value: object) -> object:
    """Numpy scalars do not round-trip through JSON; unwrap them."""
    if hasattr(value, "item"):
        return value.item()  # type: ignore[union-attr]
    return value
