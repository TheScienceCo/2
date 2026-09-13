"""A synthetic stand-in for an aoestats dump.

The environment this was built in cannot reach aoestats.io, and a corpus is a
hard dependency for baselines, the skill ladder and every model. So this
generates dumps in the declared schema with *real* structure in them: stronger
players age up sooner, float less, and spend a larger share on military, with
enough noise that the relationships have to be recovered rather than read off.

That makes the whole pipeline runnable and testable end to end. It is emphatically
not a substitute for the real corpus: every row is stamped `synthetic=True`, and
`corpus status` reports the flag so a synthetic-backed baseline can never be
mistaken for a real one.

The generator is seeded, so a given seed always produces the same dump.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

CIVS = [
    "Britons",
    "Franks",
    "Mayans",
    "Aztecs",
    "Mongols",
    "Huns",
    "Khmer",
    "Chinese",
    "Persians",
    "Berbers",
    "Ethiopians",
    "Vikings",
]
MAPS = ["Arabia", "Arena", "Black Forest", "Islands", "Gold Rush", "Four Lakes"]
OPENINGS = ["scouts", "archers", "men_at_arms", "drush", "fast_castle", "tower_rush"]

#: Elo band lower bounds; the ladder analysis uses the same edges.
ELO_BANDS = [800, 1000, 1200, 1400, 1600, 1800, 2000, 2400]


def _skill(rating: float) -> float:
    """Map a rating onto 0..1, so behaviour can be scaled by it."""
    return float(np.clip((rating - 800) / 1400, 0.0, 1.0))


def _age_uptimes(rng: np.random.Generator, rating: float) -> tuple[float, float, float]:
    """Age-up times in seconds. Stronger players are faster, with real spread."""
    s = _skill(rating)
    feudal = rng.normal(760 - 130 * s, 55)
    castle = feudal + rng.normal(620 - 120 * s, 75)
    imperial = castle + rng.normal(900 - 200 * s, 130)
    return max(300.0, feudal), max(600.0, castle), max(900.0, imperial)


def _opening(rng: np.random.Generator, rating: float) -> str:
    """Opening mix shifts with skill: more drush/FC at the top, more MAA low."""
    s = _skill(rating)
    weights = np.array(
        [
            0.26,  # scouts
            0.24 + 0.04 * s,  # archers
            0.18 - 0.12 * s,  # men_at_arms
            0.08 + 0.12 * s,  # drush
            0.14 + 0.06 * s,  # fast_castle
            0.10 - 0.06 * s,  # tower_rush
        ]
    )
    return str(rng.choice(OPENINGS, p=weights / weights.sum()))


def _replay_summary(rng: np.random.Generator, rating: float, duration: int) -> str:
    """Per-age counts of what was trained, built and researched.

    Shaped like the publisher's `replay_summary_raw`: a nested mapping of age to
    entity id to count. Ids are real ones from the cost tables so that spend
    computed from this is computed the same way it would be from a real dump.
    """
    s = _skill(rating)
    minutes = duration / 60
    ages: dict[str, dict[str, dict[str, int]]] = {}

    for age, share in (("dark", 0.25), ("feudal", 0.3), ("castle", 0.3), ("imperial", 0.15)):
        span = minutes * share
        if span < 1:
            continue
        # Villager production: better players sustain it for longer.
        villagers = int(max(0, rng.normal(span * (1.7 + 0.9 * s), 2.5)))
        units: dict[str, int] = {"83": villagers}

        if age != "dark":
            # Military commitment rises with age and with skill.
            military_scale = {"feudal": 0.6, "castle": 1.3, "imperial": 1.8}[age]
            for unit_id in ("7", "75", "93"):
                n = int(max(0, rng.normal(span * military_scale * (0.5 + 0.7 * s), 2.0)))
                if n:
                    units[unit_id] = n

        buildings: dict[str, int] = {"70": int(max(0, rng.normal(span * 0.5, 1.0)))}
        if age in ("feudal", "castle"):
            buildings["87"] = int(rng.integers(0, 3))
        if age in ("castle", "imperial"):
            # Additional Town Centers: a strong-player behaviour.
            buildings["109"] = int(rng.binomial(3, 0.15 + 0.45 * s))

        techs: dict[str, int] = {}
        for tech_id in ("22", "213", "249"):
            if rng.random() < 0.25 + 0.55 * s:
                techs[tech_id] = 1

        ages[age] = {
            "units": {k: v for k, v in units.items() if v > 0},
            "buildings": {k: v for k, v in buildings.items() if v > 0},
            "techs": techs,
        }

    return json.dumps(ages, separators=(",", ":"))


def generate(
    n_matches: int = 400,
    seed: int = 7,
    replay_enhanced_share: float = 0.62,
    dirty_share: float = 0.06,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a (matches, players) pair in the declared schema.

    `dirty_share` injects the kinds of bad rows the publisher warns about - odd
    player counts, impossible durations and ratings - so the cleaning pass is
    exercised on every run rather than only in its unit tests.
    """
    rng = np.random.default_rng(seed)
    base_time = datetime(2024, 6, 1, tzinfo=UTC)

    match_rows: list[dict] = []
    player_rows: list[dict] = []

    for i in range(n_matches):
        game_id = f"syn-{seed}-{i:06d}"
        duration = int(np.clip(rng.normal(1750, 620), 240, 9000))
        started = base_time + timedelta(minutes=int(rng.integers(0, 60 * 24 * 28)))
        enhanced = bool(rng.random() < replay_enhanced_share)

        # A shared table rating, so the two players are plausible opponents.
        table = float(np.clip(rng.normal(1450, 320), 620, 2600))
        ratings = [
            float(np.clip(rng.normal(table, 70), 400, 2800)),
            float(np.clip(rng.normal(table, 70), 400, 2800)),
        ]
        # Stronger player wins more often, but far from always.
        edge = (ratings[0] - ratings[1]) / 400
        p0_wins = rng.random() < 1 / (1 + np.exp(-edge))

        num_players = 2
        is_dirty = rng.random() < dirty_share
        dirt = rng.integers(0, 3) if is_dirty else -1
        if dirt == 0:
            num_players = 3  # odd
        elif dirt == 1:
            duration = int(rng.integers(1, 50))  # impossibly short

        match_rows.append(
            {
                "game_id": game_id,
                "map": str(rng.choice(MAPS)),
                "duration": duration,
                "num_players": num_players,
                "leaderboard": "random_map",
                "game_type": "random_map",
                "game_speed": "fast",
                "starting_age": "dark",
                "started_timestamp": started,
                "patch": "latest",
                "replay_enhanced": enhanced,
                "synthetic": True,
            }
        )

        # Distinct identities: nobody plays themselves.
        profiles = rng.choice(4000, size=2, replace=False)
        for slot in range(2):
            rating = ratings[slot]
            won = (slot == 0) == p0_wins
            row = {
                "game_id": game_id,
                "profile_id": f"p{int(profiles[slot]) + 1:05d}",
                "civ": str(rng.choice(CIVS)),
                "winner": bool(won),
                "team": slot + 1,
                "old_rating": rating,
                "new_rating": rating + (12 if won else -12),
                "replay_enhanced": enhanced,
                "synthetic": True,
            }
            if dirt == 2 and slot == 0:
                row["old_rating"] = 99999.0  # impossible rating

            if enhanced:
                feudal, castle, imperial = _age_uptimes(rng, rating)
                row["feudal_age_uptime"] = round(feudal, 1)
                row["castle_age_uptime"] = round(castle, 1) if castle < duration else None
                row["imperial_age_uptime"] = round(imperial, 1) if imperial < duration else None
                row["opening"] = _opening(rng, rating)
                row["replay_summary_raw"] = _replay_summary(rng, rating, duration)
            else:
                for absent in (
                    "feudal_age_uptime",
                    "castle_age_uptime",
                    "imperial_age_uptime",
                    "opening",
                    "replay_summary_raw",
                ):
                    row[absent] = None
            player_rows.append(row)

    return pd.DataFrame(match_rows), pd.DataFrame(player_rows)


def write(out_dir: str, **kwargs: object) -> tuple[str, str]:
    """Write a synthetic dump to `out_dir` as parquet."""
    from pathlib import Path

    matches, players = generate(**kwargs)  # type: ignore[arg-type]
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    m_path = directory / "matches.parquet"
    p_path = directory / "players.parquet"
    matches.to_parquet(m_path, index=False)
    players.to_parquet(p_path, index=False)
    return str(m_path), str(p_path)
