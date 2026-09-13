"""Test data utilities for development and testing."""

import hashlib
from datetime import datetime, timezone
from app.db.models import Replay, ReplayPlayer


def create_sample_replay(
    match_duration_ms: int = 1800000,  # 30 minutes
    player1_name: str = "TestPlayer1",
    player2_name: str = "TestPlayer2",
    player1_civ: str = "Franks",
    player2_civ: str = "Britons",
    map_name: str = "Arena",
    game_version: str = "101.102",
) -> Replay:
    """Create a sample replay for testing.

    Args:
        match_duration_ms: Duration of the match in milliseconds
        player1_name: Name of first player
        player2_name: Name of second player
        player1_civ: Civilization for player 1
        player2_civ: Civilization for player 2
        map_name: Map name
        game_version: Game version

    Returns:
        Replay instance with sample data
    """
    # Create a unique replay ID based on player names and timestamp
    hash_input = f"{player1_name}{player2_name}{datetime.now(timezone.utc).isoformat()}"
    replay_id = hashlib.sha256(hash_input.encode()).hexdigest()

    # Create sample analysis document
    analysis = {
        "players": {
            "player_1": {
                "resource_float_avg": 1500.0,
                "resource_float_peak": 3000.0,
                "villager_uptime": 0.85,
                "tc_idle_percentage": 0.05,
                "military_spend_pct": 0.30,
                "unit_composition": {
                    "spearman": 15,
                    "archer": 8,
                    "cavalry": 3,
                },
                "army_size": 26,
                "expansions": [
                    {"timestamp_ms": 600000, "x": 100, "y": 100},
                    {"timestamp_ms": 1200000, "x": 200, "y": 200},
                ],
                "apm": 45,
            },
            "player_2": {
                "resource_float_avg": 1200.0,
                "resource_float_peak": 2500.0,
                "villager_uptime": 0.82,
                "tc_idle_percentage": 0.08,
                "military_spend_pct": 0.35,
                "unit_composition": {
                    "archer": 20,
                    "cavalry": 2,
                },
                "army_size": 22,
                "expansions": [
                    {"timestamp_ms": 700000, "x": 300, "y": 300},
                ],
                "apm": 42,
            },
        }
    }

    replay = Replay(
        replay_id=replay_id,
        filename=f"{player1_name}_vs_{player2_name}.aoe2record",
        map_name=map_name,
        duration_ms=match_duration_ms,
        game_version=game_version,
        analysis=analysis,
    )

    # Create player records
    p1 = ReplayPlayer(
        player_number=1,
        name=player1_name,
        civilization=player1_civ,
        winner=True,
        feudal_ms=550,
        castle_ms=1200,
        imperial_ms=2400,
        eapm=45,
        opening="Archer Rush",
    )

    p2 = ReplayPlayer(
        player_number=2,
        name=player2_name,
        civilization=player2_civ,
        winner=False,
        feudal_ms=620,
        castle_ms=1350,
        imperial_ms=2550,
        eapm=42,
        opening="Fast Castle",
    )

    replay.players = [p1, p2]

    return replay
