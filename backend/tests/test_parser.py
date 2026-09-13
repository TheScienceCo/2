"""Parsing real replay files."""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.services.parser import ReplayParseError, get_parser
from app.services.parser.reference import (
    age_from_technology,
    is_military_production_building,
    is_town_center,
    object_name,
    technology_name,
)
from app.services.parser.types import CommandType
from tests.conftest import REC_UNPARSEABLE


@pytest.fixture(scope="module")
def parser():
    return get_parser()


class TestReference:
    """IDs resolve through the shipped dataset, not hard-coded tables."""

    def test_resolves_units_and_buildings(self):
        assert object_name(83) == "Villager"
        assert object_name(87) == "Archery Range"

    def test_town_center_has_many_ids(self):
        # The reason we group by name: one building, many IDs.
        assert is_town_center(109) and is_town_center(71) and is_town_center(621)

    def test_military_production_buildings(self):
        assert is_military_production_building(87)  # Archery Range
        assert not is_military_production_building(70)  # House

    def test_age_technologies(self):
        assert age_from_technology(101) == "feudal"
        assert age_from_technology(102) == "castle"
        assert age_from_technology(103) == "imperial"
        assert age_from_technology(22) is None  # Loom is not an age
        assert technology_name(22) == "Loom"

    def test_unknown_ids_return_none(self):
        assert object_name(999_999) is None
        assert technology_name(999_999) is None


class TestParsing:
    def test_parses_metadata(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        assert r.map_name == "Socotra"
        assert len(r.players) == 2
        assert r.duration_ms > 0
        assert {p.civilization for p in r.players} == {"Goths", "Aztecs"}
        assert sum(1 for p in r.players if p.winner) == 1

    def test_extracts_age_timings(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        ages = [c for c in r.commands if c.type is CommandType.AGE_UP]
        # Both players reached Feudal and Castle in this game.
        assert {(c.player_number, c.payload["age"]) for c in ages} == {
            (1, "feudal"),
            (2, "feudal"),
            (1, "castle"),
            (2, "castle"),
        }

    def test_commands_are_time_ordered(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        stamps = [c.timestamp_ms for c in r.commands]
        assert stamps == sorted(stamps)

    def test_age_ups_not_duplicated_as_research(self, parser, rec_with_queue):
        """Age advances come from `uptimes`; the RESEARCH command is dropped."""
        r = parser.parse(rec_with_queue)
        researched = [
            c.payload.get("technology") for c in r.commands if c.type is CommandType.RESEARCH
        ]
        assert "Feudal Age" not in researched
        assert "Castle Age" not in researched

    def test_resource_samples_present(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        assert r.resource_samples
        for p in r.players:
            assert r.samples_for(p.player_number)

    def test_build_commands_resolve_names(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        builds = [c for c in r.commands if c.type is CommandType.BUILD]
        assert builds
        assert any(c.payload.get("building") == "House" for c in builds)


class TestParseQuality:
    """The parser must say when it could not read something."""

    def test_warns_when_queue_undecodable(self, parser, rec_without_queue):
        r = parser.parse(rec_without_queue)
        assert not [c for c in r.commands if c.type is CommandType.QUEUE_UNIT]
        assert any("queue" in w.lower() for w in r.warnings)

    def test_no_spurious_warning_when_queue_decodable(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        assert [c for c in r.commands if c.type is CommandType.QUEUE_UNIT]
        assert not any("queue" in w.lower() for w in r.warnings)

    def test_unsupported_version_raises(self, parser):
        with pytest.raises(ReplayParseError):
            parser.parse(REC_UNPARSEABLE.read_bytes())

    def test_garbage_raises(self, parser):
        with pytest.raises(ReplayParseError):
            parser.parse(b"this is definitely not a replay")

    def test_empty_raises(self, parser):
        with pytest.raises(ReplayParseError):
            parser.parse(b"")


def test_parsing_is_deterministic(parser, rec_with_queue):
    """Same bytes in, same analysis out — no clocks, no randomness."""
    a, b = parser.parse(rec_with_queue), parser.parse(rec_with_queue)
    assert [(c.timestamp_ms, c.type, c.payload) for c in a.commands] == [
        (c.timestamp_ms, c.type, c.payload) for c in b.commands
    ]
    assert a.resource_samples == b.resource_samples


class TestViewport:
    """Camera positions, which the attention metrics are built on."""

    def test_viewport_extracted_for_recording_player(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        assert r.viewport_player is not None
        assert len(r.viewport) > 100
        assert r.has_viewport_for(r.viewport_player)

    def test_viewport_is_time_ordered(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        stamps = [v.timestamp_ms for v in r.viewport]
        assert stamps == sorted(stamps)

    def test_viewport_only_covers_one_player(self, parser, rec_with_queue):
        """A replay holds one perspective, so nobody else has a camera."""
        r = parser.parse(rec_with_queue)
        others = [p.player_number for p in r.players if p.player_number != r.viewport_player]
        assert others
        assert all(not r.has_viewport_for(n) for n in others)

    def test_consecutive_duplicates_are_dropped(self, parser, rec_with_queue):
        """The camera emits every sync; only real movements are kept."""
        r = parser.parse(rec_with_queue)
        pairs = [(v.x, v.y) for v in r.viewport]
        assert all(a != b for a, b in pairwise(pairs))

    def test_positions_are_within_the_map(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        assert all(0 <= v.x < 500 and 0 <= v.y < 500 for v in r.viewport)


class TestWalls:
    def test_wall_commands_carry_a_tile_count(self, parser, rec_with_queue):
        r = parser.parse(rec_with_queue)
        walls = [c for c in r.commands if c.type is CommandType.WALL]
        assert walls
        # One command lays a run of segments, so tiles exceed command count.
        counted = [c.payload["tiles"] for c in walls if c.payload["tiles"] is not None]
        assert counted and sum(counted) >= len(counted)
        assert all(t >= 1 for t in counted)
