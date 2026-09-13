"""Spend metrics from the publisher's per-age summary.

`replay_summary_raw` holds counts of what a player trained, built and researched
in each age. Multiplying those by the cost tables gives resources spent per age
exactly - no simulation, no resource-state reconstruction, no guessing.

The distinction that matters:

* **Spend is computed.** Counts are the publisher's (EXTERNAL_DERIVED), but
  turning counts into resources is arithmetic over a published cost table, and
  is exact up to the civilisation caveat below.
* **Income is a proxy.** Dividing spend by age duration assumes a player spends
  roughly what they gather. That makes it a *lower bound* on income, biased low
  exactly when someone floats - which is the behaviour it would most be used to
  study. It carries `PROXY` provenance and that assumption travels with it.

Float, idle time and gather rates need resource-state simulation and are
deliberately not attempted here.

**Civilisation costs are not applied.** Goths pay less for infantry, Persians
less for Town Centers. The cost table is standard-cost, so spend is exact for
most civs and slightly off for the rest. Rather than silently absorbing that,
every result carries `civ_adjusted=False`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.costs import ResourceCost, cost_of_building, cost_of_tech, cost_of_unit
from app.services.costs.tables import is_military_unit
from app.services.parser.types import Availability

log = get_logger(__name__)

AGES = ("dark", "feudal", "castle", "imperial")


@dataclass
class AgeSpend:
    """What one player spent during one age."""

    age: str
    units: ResourceCost = field(default_factory=ResourceCost)
    buildings: ResourceCost = field(default_factory=ResourceCost)
    techs: ResourceCost = field(default_factory=ResourceCost)
    military: ResourceCost = field(default_factory=ResourceCost)
    #: Counts by entity id, kept for composition clustering later.
    composition: dict[str, int] = field(default_factory=dict)
    #: Entity ids the cost table did not recognise. Their spend is missing, so
    #: this is reported rather than rounded away.
    unknown_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> ResourceCost:
        return self.units + self.buildings + self.techs

    @property
    def military_share(self) -> float | None:
        """Military spend as a share of all spend, or None when nothing was spent."""
        total = self.total.total
        return self.military.total / total if total else None

    @property
    def tech_share(self) -> float | None:
        total = self.total.total
        return self.techs.total / total if total else None

    def income_proxy(self, age_seconds: float | None) -> float | None:
        """Resources spent per minute during this age. A lower bound on income."""
        if not age_seconds or age_seconds <= 0:
            return None
        return self.total.total / (age_seconds / 60)


@dataclass
class SpendBreakdown:
    """Per-age spend for one player, with what could not be resolved."""

    ages: dict[str, AgeSpend] = field(default_factory=dict)
    civ_adjusted: bool = False
    provenance: Availability = Availability.EXTERNAL_DERIVED
    unresolved_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> ResourceCost:
        out = ResourceCost()
        for age in self.ages.values():
            out = out + age.total
        return out

    def as_dict(self) -> dict:
        return {
            "civ_adjusted": self.civ_adjusted,
            "provenance": self.provenance.value,
            "unresolved_ids": self.unresolved_ids,
            "total": self.total.as_dict(),
            "ages": {
                name: {
                    "total": age.total.as_dict(),
                    "units": age.units.as_dict(),
                    "buildings": age.buildings.as_dict(),
                    "techs": age.techs.as_dict(),
                    "military": age.military.as_dict(),
                    "military_share": age.military_share,
                    "tech_share": age.tech_share,
                    "composition": age.composition,
                }
                for name, age in self.ages.items()
            },
        }


def age_durations(
    duration_seconds: float,
    feudal_uptime: float | None,
    castle_uptime: float | None,
    imperial_uptime: float | None,
) -> dict[str, float]:
    """How long each age lasted, from the age-up timestamps.

    An age the player never reached gets no entry - not a zero, which would
    divide into a misleading income figure.
    """
    marks: list[tuple[str, float]] = [("dark", 0.0)]
    for name, uptime in (
        ("feudal", feudal_uptime),
        ("castle", castle_uptime),
        ("imperial", imperial_uptime),
    ):
        if uptime is not None and uptime < duration_seconds:
            marks.append((name, float(uptime)))

    out: dict[str, float] = {}
    for index, (name, start) in enumerate(marks):
        end = marks[index + 1][1] if index + 1 < len(marks) else duration_seconds
        if end > start:
            out[name] = end - start
    return out


def parse_summary(raw: str | None) -> dict[str, dict[str, dict[str, int]]]:
    """Normalise `replay_summary_raw` into age -> kind -> id -> count.

    Tolerant of shape: the publisher's exact nesting is not pinned down from
    here, so anything unrecognised yields an empty result and a warning rather
    than an exception that would fail a whole ingest.
    """
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        log.warning("spend.summary_unparseable", error=str(exc))
        return {}
    if not isinstance(payload, dict):
        log.warning("spend.summary_unexpected_shape", shape=type(payload).__name__)
        return {}

    out: dict[str, dict[str, dict[str, int]]] = {}
    for age, sections in payload.items():
        if age not in AGES or not isinstance(sections, dict):
            continue
        normalised: dict[str, dict[str, int]] = {}
        for kind in ("units", "buildings", "techs"):
            entries = sections.get(kind)
            if isinstance(entries, dict):
                normalised[kind] = {str(k): int(v) for k, v in entries.items() if _is_count(v)}
        if normalised:
            out[age] = normalised
    return out


def _is_count(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value >= 0


def compute_spend(raw: str | None) -> SpendBreakdown:
    """Turn a summary blob into per-age resource spend."""
    parsed = parse_summary(raw)
    breakdown = SpendBreakdown()
    unresolved: set[str] = set()

    for age, sections in parsed.items():
        entry = AgeSpend(age=age)

        for unit_id, count in sections.get("units", {}).items():
            cost = cost_of_unit(int(unit_id)) if unit_id.isdigit() else None
            if cost is None:
                unresolved.add(f"unit:{unit_id}")
                entry.unknown_ids.append(f"unit:{unit_id}")
                continue
            scaled = cost.scaled(count)
            entry.units = entry.units + scaled
            entry.composition[unit_id] = entry.composition.get(unit_id, 0) + count
            # An unrecognised unit is not counted as economy by default; that
            # would quietly deflate military share.
            if is_military_unit(int(unit_id)):
                entry.military = entry.military + scaled

        for building_id, count in sections.get("buildings", {}).items():
            cost = cost_of_building(int(building_id)) if building_id.isdigit() else None
            if cost is None:
                unresolved.add(f"building:{building_id}")
                entry.unknown_ids.append(f"building:{building_id}")
                continue
            entry.buildings = entry.buildings + cost.scaled(count)

        for tech_id, count in sections.get("techs", {}).items():
            cost = cost_of_tech(int(tech_id)) if tech_id.isdigit() else None
            if cost is None:
                unresolved.add(f"tech:{tech_id}")
                entry.unknown_ids.append(f"tech:{tech_id}")
                continue
            entry.techs = entry.techs + cost.scaled(count)

        breakdown.ages[age] = entry

    breakdown.unresolved_ids = sorted(unresolved)
    return breakdown
