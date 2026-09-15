"""Per-minute action timeline, from the command stream.

The radar needs to know *when* a player was doing *what*. The parser already
recovers a timestamped command stream; this bins it into one-minute buckets and
classifies each command into an attention category.

Scouting is deliberately absent. A replay's command stream retains build,
queue, research and administrative orders — it carries no unit movement, so
there is nothing from which to honestly derive scouting attention. Reporting a
zero would read as "this player never scouted" rather than "this file cannot
say", so the category is simply not produced.
"""

from __future__ import annotations

from app.services.parser.types import Command, CommandType

#: Buildings that serve the economy.
_ECONOMY_BUILDINGS = frozenset(
    {
        "House", "Mill", "Lumber Camp", "Mining Camp", "Farm", "Town Center",
        "Market", "Dock", "Fish Trap",
    }
)

#: Buildings that produce or project military force.
_MILITARY_BUILDINGS = frozenset(
    {
        "Barracks", "Archery Range", "Stable", "Siege Workshop", "Castle",
        "Krepost", "Donjon", "Watch Tower", "Guard Tower", "Keep",
        "Bombard Tower", "Outpost",
    }
)

#: Units that work rather than fight.
_ECONOMY_UNITS = frozenset(
    {"Villager", "Fishing Ship", "Trade Cart", "Trade Cog", "Transport Ship"}
)

#: Commands whose category does not depend on their payload.
_FIXED: dict[CommandType, str] = {
    CommandType.RESEARCH: "strategy",
    CommandType.AGE_UP: "strategy",
    CommandType.WALL: "strategy",
    CommandType.DELETE: "strategy",
    CommandType.TRIBUTE: "strategy",
    CommandType.RESIGN: "strategy",
    CommandType.MARKET_BUY: "economy",
    CommandType.MARKET_SELL: "economy",
    CommandType.BACK_TO_WORK: "economy",
    CommandType.TOWN_BELL: "economy",
}

BUCKET_MS = 60_000

CATEGORIES = ("economy", "military", "strategy")


def classify(command: Command) -> str:
    """Which attention category a command belongs to."""
    fixed = _FIXED.get(command.type)
    if fixed:
        return fixed

    if command.type is CommandType.BUILD:
        building = command.payload.get("building")
        if building in _MILITARY_BUILDINGS:
            return "military"
        if building in _ECONOMY_BUILDINGS:
            return "economy"
        # Blacksmith, University, Monastery and friends are tech investments.
        return "strategy"

    if command.type is CommandType.QUEUE_UNIT:
        unit = command.payload.get("unit")
        amount = command.payload.get("amount") or 1
        del amount  # counted by the caller, not here
        return "economy" if unit in _ECONOMY_UNITS else "military"

    return "strategy"


def timeline(commands: list[Command], duration_ms: int) -> list[dict]:
    """One-minute buckets of categorised action counts.

    Every minute of the match is present, including quiet ones — a gap in the
    radar has to mean "nothing happened", which it cannot if empty minutes are
    dropped.
    """
    if duration_ms <= 0:
        return []

    bucket_count = max(1, -(-duration_ms // BUCKET_MS))  # ceil
    buckets: list[dict] = [
        {
            "start_ms": i * BUCKET_MS,
            "end_ms": min((i + 1) * BUCKET_MS, duration_ms),
            **{c: 0 for c in CATEGORIES},
            "total": 0,
        }
        for i in range(bucket_count)
    ]

    for command in commands:
        index = command.timestamp_ms // BUCKET_MS
        if not 0 <= index < bucket_count:
            continue
        # A queue order for five units is five units of intent, not one.
        weight = 1
        if command.type is CommandType.QUEUE_UNIT:
            weight = max(1, int(command.payload.get("amount") or 1))
        bucket = buckets[index]
        bucket[classify(command)] += weight
        bucket["total"] += weight

    return buckets
