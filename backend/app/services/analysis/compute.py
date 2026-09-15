"""Pull the analytics layer's inputs out of a stored analysis document.

The document is the same one the API returns for an upload: `players` is a
*list*, and each player's numbers live in a `metrics` dict where every entry
carries its own availability. A metric marked `unavailable` has a null value,
and must stay null here — substituting a zero would turn "this replay cannot
say" into "this player did none of it", which is the one thing the whole
provenance model exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.models import Replay


@dataclass
class PlayerMetrics:
    """One player's inputs to the DVA, playstyle and radar analyses."""

    player_number: int
    name: str
    civilization: str

    # Age timings (ms), absent where the player never reached that age.
    feudal_ms: int | None = None
    castle_ms: int | None = None
    imperial_ms: int | None = None

    #: Effective APM. The parser reports no raw APM, so there is no `apm`.
    eapm: int | None = None
    opening: str | None = None

    # Economy
    resource_float_avg: float | None = None
    resource_float_peak: float | None = None
    time_floating_ms: int | None = None

    # Production. Both are unavailable on replay versions whose unit-queue
    # commands do not decode.
    villagers_queued: int | None = None
    max_production_gap_ms: int | None = None

    # Build
    buildings_placed: int | None = None
    technologies_researched: int | None = None
    #: Town Centres beyond the starting one — the only expansion signal a
    #: command stream actually supports.
    expansion_count: int = 0
    expansion_timing_ms: int | None = None

    #: One-minute categorised command counts.
    action_timeline: list[dict] = field(default_factory=list)

    winner: bool | None = None


def _metric(metrics: dict[str, Any], key: str) -> float | int | None:
    """A metric's value, or None when it is unavailable or missing."""
    entry = metrics.get(key)
    if not isinstance(entry, dict):
        return None
    if entry.get("availability") == "unavailable":
        return None
    return entry.get("value")


def _as_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


class MetricsComputeService:
    """Read a stored analysis document into `PlayerMetrics`."""

    def compute_from_replay(self, replay: Replay) -> dict[int, PlayerMetrics]:
        """Metrics for every player in the replay, keyed by player number.

        Falls back to the flattened `replay_players` columns when the analysis
        document is missing, so a row written by an older pipeline still yields
        the age timings it does have.
        """
        document = replay.analysis if isinstance(replay.analysis, dict) else {}
        by_number = {
            p.get("player_number"): p
            for p in document.get("players", [])
            if isinstance(p, dict)
        }

        out: dict[int, PlayerMetrics] = {}
        for player in replay.players:
            metrics = PlayerMetrics(
                player_number=player.player_number,
                name=player.name,
                civilization=player.civilization,
                feudal_ms=player.feudal_ms,
                castle_ms=player.castle_ms,
                imperial_ms=player.imperial_ms,
                eapm=player.eapm,
                opening=player.opening,
                winner=player.winner,
            )
            document_player = by_number.get(player.player_number)
            if document_player:
                self._merge(document_player, metrics)
            out[player.player_number] = metrics

        return out

    def _merge(self, source: dict, target: PlayerMetrics) -> None:
        metrics = source.get("metrics") or {}

        ages = source.get("age_timings_ms") or {}
        target.feudal_ms = _as_int(ages.get("feudal")) or target.feudal_ms
        target.castle_ms = _as_int(ages.get("castle")) or target.castle_ms
        target.imperial_ms = _as_int(ages.get("imperial")) or target.imperial_ms

        target.eapm = _as_int(_metric(metrics, "eapm")) or target.eapm
        target.opening = source.get("opening") or target.opening

        float_mean = _metric(metrics, "float_mean")
        float_peak = _metric(metrics, "float_peak")
        target.resource_float_avg = float(float_mean) if float_mean is not None else None
        target.resource_float_peak = float(float_peak) if float_peak is not None else None
        target.time_floating_ms = _as_int(_metric(metrics, "time_floating"))

        target.villagers_queued = _as_int(_metric(metrics, "villagers_queued"))
        target.max_production_gap_ms = _as_int(_metric(metrics, "max_production_gap"))
        target.buildings_placed = _as_int(_metric(metrics, "buildings_placed"))
        target.technologies_researched = _as_int(_metric(metrics, "technologies_researched"))

        target.action_timeline = [
            b for b in (source.get("action_timeline") or []) if isinstance(b, dict)
        ]

        # Every Town Centre after the first is an expansion. The starting one is
        # never placed by a command, so each one seen here is a deliberate one.
        centres = [
            entry
            for entry in (source.get("build_order") or [])
            if isinstance(entry, dict) and entry.get("building") == "Town Center"
        ]
        target.expansion_count = len(centres)
        if centres:
            target.expansion_timing_ms = _as_int(centres[0].get("timestamp_ms"))
