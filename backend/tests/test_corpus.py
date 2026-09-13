"""The external corpus: schema provenance, cleaning, and ingestion."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.corpus.clean import RejectionReason, clean
from app.services.corpus.ingest import ELO_BAND_EDGES, elo_band, ingest_dump
from app.services.corpus.schema import inspect_columns, provenance_of
from app.services.corpus.synthetic import generate, write
from app.services.parser.types import Availability


class TestProvenance:
    """What we claim per column is the whole point of the corpus layer."""

    def test_publisher_derived_fields_are_not_observed(self):
        for column in (
            "feudal_age_uptime",
            "castle_age_uptime",
            "imperial_age_uptime",
            "replay_summary_raw",
        ):
            assert provenance_of(column) is Availability.EXTERNAL_DERIVED

    def test_opening_is_a_label_not_a_measurement(self):
        assert provenance_of("opening") is Availability.EXTERNAL_LABEL

    def test_patch_is_inferred_not_observed(self):
        """It comes from the start time, not a replay header."""
        assert provenance_of("patch") is Availability.INFERRED

    def test_match_record_fields_are_observed(self):
        for column in ("civ", "winner", "map", "duration", "num_players", "profile_id"):
            assert provenance_of(column) is Availability.OBSERVED

    def test_unknown_columns_are_not_trusted(self):
        assert provenance_of("some_new_field") is Availability.UNAVAILABLE


class TestSchemaInspection:
    def test_reports_unexpected_columns_rather_than_ingesting_them(self):
        report = inspect_columns(["game_id", "civ", "a_column_we_do_not_know"])
        assert "a_column_we_do_not_know" in report.unexpected

    def test_missing_required_makes_a_dump_unusable(self):
        assert not inspect_columns(["civ", "map"]).usable

    def test_full_schema_is_usable(self):
        matches, players = generate(n_matches=5)
        combined = sorted(set(matches.columns) | set(players.columns))
        assert inspect_columns(combined).usable


class TestCleaning:
    def test_odd_player_counts_are_dropped(self):
        matches = pd.DataFrame([{"game_id": "g", "num_players": 3, "duration": 900}])
        players = pd.DataFrame([{"game_id": "g", "profile_id": "a", "old_rating": 1200}])
        kept, _, report = clean(matches, players)
        assert kept.empty
        assert RejectionReason.ODD_PLAYER_COUNT.value in report.by_reason()

    def test_implausible_durations_are_dropped(self):
        matches = pd.DataFrame(
            [
                {"game_id": "short", "num_players": 2, "duration": 3},
                {"game_id": "eternal", "num_players": 2, "duration": 10**6},
            ]
        )
        players = pd.DataFrame(
            [
                {"game_id": "short", "profile_id": "a", "old_rating": 1200},
                {"game_id": "eternal", "profile_id": "b", "old_rating": 1200},
            ]
        )
        kept, _, report = clean(matches, players)
        assert kept.empty
        # Both the match rows and their player rows are recorded as rejected.
        assert report.by_reason()[RejectionReason.IMPLAUSIBLE_DURATION.value] == 4

    def test_implausible_rating_takes_the_whole_match(self):
        """A match missing a player cannot support anything paired."""
        matches = pd.DataFrame([{"game_id": "g", "num_players": 2, "duration": 900}])
        players = pd.DataFrame(
            [
                {"game_id": "g", "profile_id": "a", "old_rating": 99999},
                {"game_id": "g", "profile_id": "b", "old_rating": 1300},
            ]
        )
        _, kept_players, report = clean(matches, players)
        assert kept_players.empty
        assert RejectionReason.INCOMPLETE_MATCH.value in report.by_reason()

    def test_orphan_player_rows_are_dropped(self):
        matches = pd.DataFrame([{"game_id": "g", "num_players": 2, "duration": 900}])
        players = pd.DataFrame(
            [
                {"game_id": "g", "profile_id": "a", "old_rating": 1200},
                {"game_id": "g", "profile_id": "b", "old_rating": 1200},
                {"game_id": "ghost", "profile_id": "c", "old_rating": 1200},
            ]
        )
        _, kept, report = clean(matches, players)
        assert set(kept.profile_id) == {"a", "b"}
        assert RejectionReason.ORPHAN_PLAYER_ROW.value in report.by_reason()

    def test_every_rejection_carries_a_reason(self):
        matches, players = generate(n_matches=120, seed=3)
        _, _, report = clean(matches, players)
        assert report.rejections
        assert all(r.reason and r.detail for r in report.rejections)

    def test_retention_is_reported(self):
        matches, players = generate(n_matches=120, seed=3)
        _, _, report = clean(matches, players)
        assert 0.0 < report.match_retention <= 1.0
        assert "retained" in report.summary()

    def test_clean_data_is_fully_retained(self):
        matches, players = generate(n_matches=60, seed=5, dirty_share=0.0)
        kept_m, kept_p, report = clean(matches, players)
        assert report.match_retention == 1.0
        assert len(kept_m) == len(matches) and len(kept_p) == len(players)


class TestEloBanding:
    @pytest.mark.parametrize(
        ("rating", "expected"),
        [(650, 0), (1000, 1000), (1199, 1000), (1200, 1200), (1999, 1800), (2400, 2000)],
    )
    def test_bands_by_lower_edge(self, rating, expected):
        assert elo_band(rating) == expected

    def test_missing_rating_stays_missing(self):
        assert elo_band(None) is None

    def test_edges_are_ascending(self):
        assert list(ELO_BAND_EDGES) == sorted(ELO_BAND_EDGES)


class TestSynthetic:
    def test_is_deterministic(self):
        a, _ = generate(n_matches=30, seed=42)
        b, _ = generate(n_matches=30, seed=42)
        assert list(a.game_id) == list(b.game_id)

    def test_carries_real_elo_structure(self):
        """Stronger players must actually age up sooner, or models learn noise."""
        _, players = generate(n_matches=900, seed=13, dirty_share=0.0)
        enhanced = players[players.replay_enhanced]
        low = enhanced[enhanced.old_rating < 1200].feudal_age_uptime.median()
        high = enhanced[enhanced.old_rating > 1800].feudal_age_uptime.median()
        assert high < low - 20

    def test_every_row_is_flagged_synthetic(self):
        matches, players = generate(n_matches=20)
        assert matches.synthetic.all() and players.synthetic.all()

    def test_non_enhanced_rows_have_no_derived_fields(self):
        _, players = generate(n_matches=200, seed=2)
        plain = players[~players.replay_enhanced]
        assert plain.feudal_age_uptime.isna().all()
        assert plain.opening.isna().all()


class TestIngestion:
    def test_round_trip_into_the_database(self, session, tmp_path):
        from app.db.models import CorpusMatch, CorpusPlayer, CorpusRejection

        m, p = write(str(tmp_path / "dump"), n_matches=80, seed=9)
        report = ingest_dump(session, m, p, source_range="test-range")

        assert report.matches_written > 0
        assert report.synthetic is True
        assert 0.0 < report.replay_enhanced_share < 1.0

        assert session.query(CorpusMatch).count() == report.matches_written
        assert session.query(CorpusPlayer).count() == report.players_written
        assert session.query(CorpusRejection).count() == report.rejections_written

    def test_elo_bands_are_assigned_on_ingest(self, session, tmp_path):
        from app.db.models import CorpusPlayer

        m, p = write(str(tmp_path / "dump"), n_matches=60, seed=4)
        ingest_dump(session, m, p, source_range="bands")
        rated = session.query(CorpusPlayer).filter(CorpusPlayer.old_rating.isnot(None)).all()
        assert rated
        assert all(row.elo_band in ELO_BAND_EDGES for row in rated)

    def test_reingesting_a_range_replaces_it(self, session, tmp_path):
        from app.db.models import CorpusMatch

        m, p = write(str(tmp_path / "dump"), n_matches=40, seed=6)
        first = ingest_dump(session, m, p, source_range="same")
        ingest_dump(session, m, p, source_range="same")
        assert session.query(CorpusMatch).count() == first.matches_written

    def test_missing_required_columns_are_refused(self, session, tmp_path):
        matches, players = generate(n_matches=10)
        matches = matches.drop(columns=["duration"])
        players = players.drop(columns=["profile_id"])
        d = tmp_path / "bad"
        d.mkdir()
        matches.to_parquet(d / "m.parquet")
        players.to_parquet(d / "p.parquet")
        with pytest.raises(ValueError, match="missing required columns"):
            ingest_dump(session, d / "m.parquet", d / "p.parquet")

    def test_patch_boundary_rows_are_flagged(self, session, tmp_path):
        from datetime import date

        m, p = write(str(tmp_path / "dump"), n_matches=200, seed=8)
        report = ingest_dump(session, m, p, source_range="patched", patch_dates=[date(2024, 6, 11)])
        assert report.patch_low_confidence > 0

    def test_without_a_patch_calendar_nothing_is_flagged_confident(self, session, tmp_path):
        m, p = write(str(tmp_path / "dump"), n_matches=50, seed=8)
        report = ingest_dump(session, m, p, source_range="nocal", patch_dates=None)
        assert report.patch_low_confidence == 0
