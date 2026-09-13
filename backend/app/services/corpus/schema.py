"""The aoestats corpus schema, and what we are willing to claim about each field.

Provenance is assigned per column, not per table, because a single dump row
mixes things the publisher read straight out of a match record with things their
own replay pipeline derived. Collapsing that distinction is how someone else's
inference ends up presented as our measurement.

The publisher states the data is not clean, so `clean.py` enforces the
plausibility rules and records every rejection.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.parser.types import Availability


@dataclass(frozen=True)
class Column:
    name: str
    provenance: Availability
    required: bool
    note: str = ""


#: Read from the match record. We trust these as observed fact.
_OBSERVED = [
    Column("game_id", Availability.OBSERVED, True, "Join key across both files."),
    Column("profile_id", Availability.OBSERVED, True, "Stable player identifier."),
    Column("civ", Availability.OBSERVED, True),
    Column("winner", Availability.OBSERVED, True),
    Column("team", Availability.OBSERVED, False),
    Column("old_rating", Availability.OBSERVED, False, "Rating before the match."),
    Column("new_rating", Availability.OBSERVED, False, "Rating after the match."),
    Column("map", Availability.OBSERVED, True),
    Column("duration", Availability.OBSERVED, True, "Match length in seconds."),
    Column("leaderboard", Availability.OBSERVED, False, "e.g. random_map, empire_wars."),
    Column("game_type", Availability.OBSERVED, False),
    Column("game_speed", Availability.OBSERVED, False),
    Column("starting_age", Availability.OBSERVED, False),
    Column("num_players", Availability.OBSERVED, True),
    Column("started_timestamp", Availability.OBSERVED, False, "Match start time."),
]

#: Computed by the publisher's own replay pipeline. Not ours, not auditable by
#: us, and only present where `replay_enhanced` is true.
_EXTERNAL_DERIVED = [
    Column("feudal_age_uptime", Availability.EXTERNAL_DERIVED, False),
    Column("castle_age_uptime", Availability.EXTERNAL_DERIVED, False),
    Column("imperial_age_uptime", Availability.EXTERNAL_DERIVED, False),
    Column(
        "replay_summary_raw",
        Availability.EXTERNAL_DERIVED,
        False,
        "JSON of per-age unit/building/tech counts.",
    ),
]

#: A label, not a measurement. Usable to stratify; never ground truth.
_EXTERNAL_LABEL = [
    Column(
        "opening",
        Availability.EXTERNAL_LABEL,
        False,
        "Publisher's opening classification. Compared against ours, never assumed correct.",
    ),
]

#: Derived from the match start time against a patch calendar, not read from a
#: replay header. Rows near a patch boundary are therefore uncertain.
_INFERRED = [
    Column(
        "patch",
        Availability.INFERRED,
        False,
        "Attributed from started_timestamp; ambiguous near a patch boundary.",
    ),
]

#: Marks whether the publisher had a replay for this row. Without it the
#: EXTERNAL_DERIVED columns are absent, and any baseline built on them has a
#: smaller effective n than the match count suggests.
_FLAGS = [
    Column("replay_enhanced", Availability.OBSERVED, False),
]

COLUMNS: dict[str, Column] = {
    c.name: c for c in _OBSERVED + _EXTERNAL_DERIVED + _EXTERNAL_LABEL + _INFERRED + _FLAGS
}

REQUIRED = tuple(c.name for c in COLUMNS.values() if c.required)

#: Fields that only exist on replay-enhanced rows.
REPLAY_ENHANCED_ONLY = tuple(c.name for c in _EXTERNAL_DERIVED + _EXTERNAL_LABEL)


def provenance_of(column: str) -> Availability:
    """How much we are willing to claim for a column. Unknown columns are not trusted."""
    entry = COLUMNS.get(column)
    return entry.provenance if entry else Availability.UNAVAILABLE


@dataclass
class SchemaReport:
    """What a loaded dump actually contained, against what we expected."""

    found: list[str]
    missing_required: list[str]
    missing_optional: list[str]
    unexpected: list[str]

    @property
    def usable(self) -> bool:
        return not self.missing_required

    def summary(self) -> str:
        parts = [f"{len(self.found)} expected columns present"]
        if self.missing_required:
            parts.append(f"MISSING REQUIRED: {', '.join(self.missing_required)}")
        if self.missing_optional:
            parts.append(f"absent optional: {', '.join(self.missing_optional)}")
        if self.unexpected:
            parts.append(f"unrecognised (ignored): {', '.join(self.unexpected[:8])}")
        return " | ".join(parts)


def inspect_columns(present: list[str]) -> SchemaReport:
    """Compare a dump's actual columns against the declared schema.

    Unrecognised columns are reported and ignored rather than ingested blind:
    a column we have not assigned provenance to is a column we cannot honestly
    render.
    """
    present_set = set(present)
    expected = set(COLUMNS)
    return SchemaReport(
        found=sorted(present_set & expected),
        missing_required=sorted(c for c in REQUIRED if c not in present_set),
        missing_optional=sorted(expected - present_set - set(REQUIRED)),
        unexpected=sorted(present_set - expected),
    )
