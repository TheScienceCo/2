"""Unit, building and technology costs.

Sourced from a snapshot of `SiegeEngineers/aoe2techtree`'s machine-readable
`data/data.json` rather than hand-typed, and checksummed against the upstream
file it was taken from. `scripts/refresh_cost_tables.py` regenerates it.

**Civilisation adjustments are not applied.** Several civs change costs (Goths'
cheaper infantry, Persians' cheaper Town Centers, Burgundians' cheaper economic
upgrades) and those bonuses are not in this table. Spend figures computed from it
are therefore the *standard-cost* spend, which is exact for most civs and an
over- or under-estimate for the rest. Anything built on it is labelled
accordingly rather than presented as the player's true expenditure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

COST_TABLE_VERSION = "v1"

_DATA = Path(__file__).parent / "data" / f"costs_{COST_TABLE_VERSION}.json"

#: Unit `internal_name` prefixes that denote economic rather than military units.
#: The tech-tree data has no military flag, so the split is by known identity:
#: villagers, fishing boats, trade units and monks are not army.
_NON_MILITARY_NAMES = frozenset(
    {
        "VMBAS",  # Villager
        "FSHBT",  # Fishing Ship
        "TCART",  # Trade Cart
        "TCOGX",  # Trade Cog
        "MONK",  # Monk
        "SHEEP",
        "HORSE",
    }
)


@dataclass(frozen=True)
class ResourceCost:
    """A cost in the four resources. Absent resources are zero."""

    food: int = 0
    wood: int = 0
    gold: int = 0
    stone: int = 0

    @property
    def total(self) -> int:
        return self.food + self.wood + self.gold + self.stone

    def scaled(self, n: int) -> ResourceCost:
        return ResourceCost(self.food * n, self.wood * n, self.gold * n, self.stone * n)

    def __add__(self, other: ResourceCost) -> ResourceCost:
        return ResourceCost(
            self.food + other.food,
            self.wood + other.wood,
            self.gold + other.gold,
            self.stone + other.stone,
        )

    def as_dict(self) -> dict[str, int]:
        return {"food": self.food, "wood": self.wood, "gold": self.gold, "stone": self.stone}


ZERO = ResourceCost()


@lru_cache(maxsize=1)
def _snapshot() -> dict[str, Any]:
    return json.loads(_DATA.read_text())


def snapshot_provenance() -> dict[str, str]:
    """Where the table came from, for display and for metric provenance."""
    snap = _snapshot()
    return {
        "version": COST_TABLE_VERSION,
        "source": snap["source"],
        "source_file": snap["source_file"],
        "snapshot_taken": snap["snapshot_taken"],
        "upstream_sha256": snap["upstream_sha256"],
    }


def _lookup(kind: str, entity_id: int) -> ResourceCost | None:
    entry = _snapshot()[kind].get(str(entity_id))
    if entry is None:
        return None
    c = entry["cost"]
    return ResourceCost(
        food=c.get("food", 0),
        wood=c.get("wood", 0),
        gold=c.get("gold", 0),
        stone=c.get("stone", 0),
    )


def cost_of_unit(unit_id: int) -> ResourceCost | None:
    """Standard training cost, or None for an id the snapshot does not cover."""
    return _lookup("units", unit_id)


def cost_of_building(building_id: int) -> ResourceCost | None:
    return _lookup("buildings", building_id)


def cost_of_tech(tech_id: int) -> ResourceCost | None:
    return _lookup("techs", tech_id)


def is_military_unit(unit_id: int) -> bool | None:
    """True for army, False for economy, None for an unknown id.

    None is distinct from False on purpose: an unrecognised unit must not be
    silently counted as economy and quietly deflate military-share metrics.
    """
    entry = _snapshot()["units"].get(str(unit_id))
    if entry is None:
        return None
    return entry["name"] not in _NON_MILITARY_NAMES
