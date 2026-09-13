"""Spend derivation and the Skill Ladder fit."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app.services.analysis.ladder import MIN_ACCURACY, build_pairs, fit_ladder, player_features
from app.services.corpus.ingest import elo_band
from app.services.corpus.spend import age_durations, compute_spend, parse_summary
from app.services.corpus.synthetic import generate
from app.services.costs import cost_of_unit, snapshot_provenance
from app.services.parser.types import Availability


def ladder_frame(n: int = 400, seed: int = 17) -> pd.DataFrame:
    """A frame shaped like `corpus_frame()`, without needing a database.

    Elo bands are assigned during ingestion in production, so a test frame that
    skips ingestion has to apply the same banding or nothing pairs up.
    """
    matches, players = generate(n_matches=n, seed=seed, dirty_share=0.0)
    frame = players.merge(
        matches[["game_id", "duration", "map_name" if "map_name" in matches else "map"]].rename(
            columns={"duration": "duration_seconds", "map": "map_name"}
        ),
        on="game_id",
    )
    frame["elo_band"] = frame["old_rating"].map(elo_band)
    return frame


class TestCostTables:
    def test_costs_match_the_game(self):
        """Spot-check against known values; a wrong table silently skews everything."""
        assert cost_of_unit(83).as_dict() == {"food": 50, "wood": 0, "gold": 0, "stone": 0}
        assert cost_of_unit(7).as_dict() == {"food": 25, "wood": 35, "gold": 0, "stone": 0}

    def test_snapshot_records_its_upstream(self):
        p = snapshot_provenance()
        assert p["source"].startswith("https://github.com/SiegeEngineers")
        assert len(p["upstream_sha256"]) == 64


class TestSummaryParsing:
    def test_tolerates_junk_without_raising(self):
        for junk in (None, "", "not json", "[1,2,3]", '{"bogus_age": {}}'):
            assert parse_summary(junk) == {}

    def test_extracts_known_ages_only(self):
        raw = json.dumps({"feudal": {"units": {"83": 4}}, "nonsense": {"units": {"1": 1}}})
        assert set(parse_summary(raw)) == {"feudal"}

    def test_rejects_negative_counts(self):
        raw = json.dumps({"feudal": {"units": {"83": -5, "7": 3}}})
        assert parse_summary(raw)["feudal"]["units"] == {"7": 3}


class TestSpend:
    def test_spend_is_exact_arithmetic(self):
        raw = json.dumps({"feudal": {"units": {"83": 10}}})  # 10 villagers
        breakdown = compute_spend(raw)
        assert breakdown.ages["feudal"].units.food == 500
        assert breakdown.total.total == 500

    def test_military_is_separated_from_economy(self):
        raw = json.dumps({"castle": {"units": {"83": 4, "7": 4}}})
        entry = compute_spend(raw).ages["castle"]
        assert entry.military.total == 4 * 60  # crossbows only
        assert 0 < entry.military_share < 1

    def test_unknown_ids_are_reported_not_absorbed(self):
        raw = json.dumps({"feudal": {"units": {"99999": 3}}})
        breakdown = compute_spend(raw)
        assert breakdown.unresolved_ids == ["unit:99999"]
        assert breakdown.total.total == 0

    def test_civ_adjustment_is_declared_absent(self):
        """Civ cost bonuses are not applied; the result must say so."""
        assert compute_spend(json.dumps({"feudal": {"units": {"83": 1}}})).civ_adjusted is False

    def test_provenance_is_external(self):
        assert compute_spend(None).provenance is Availability.EXTERNAL_DERIVED

    def test_shares_are_none_when_nothing_was_spent(self):
        breakdown = compute_spend(json.dumps({"feudal": {"units": {}}}))
        assert breakdown.ages["feudal"].military_share is None


class TestAgeDurations:
    def test_ages_never_reached_are_absent_not_zero(self):
        durations = age_durations(1200, feudal_uptime=600, castle_uptime=None, imperial_uptime=None)
        assert set(durations) == {"dark", "feudal"}
        assert "castle" not in durations

    def test_durations_sum_to_the_match(self):
        durations = age_durations(3000, 700, 1500, 2200)
        assert sum(durations.values()) == pytest.approx(3000)

    def test_income_proxy_needs_a_duration(self):
        entry = compute_spend(json.dumps({"feudal": {"units": {"83": 10}}})).ages["feudal"]
        assert entry.income_proxy(None) is None
        assert entry.income_proxy(0) is None
        assert entry.income_proxy(600) == pytest.approx(50.0)


class TestPairing:
    def test_pairs_are_emitted_in_both_orderings(self):
        """Otherwise the fit can learn which row came first, which means nothing."""
        frame = ladder_frame(n=120)
        features, labels, _ = build_pairs(frame)
        assert len(features) % 2 == 0
        assert labels.sum() == len(labels) / 2

    def test_differencing_is_antisymmetric(self):
        frame = ladder_frame(n=60)
        features, _, _ = build_pairs(frame)
        first, second = features.iloc[0], features.iloc[1]
        shared = [c for c in features.columns if pd.notna(first[c]) and pd.notna(second[c])]
        assert all(first[c] == pytest.approx(-second[c]) for c in shared)

    def test_cross_band_matches_are_excluded(self):
        frame = ladder_frame(n=200)
        _, _, bands = build_pairs(frame)
        assert bands.notna().all()

    def test_non_enhanced_rows_yield_no_features(self):
        _, players = generate(n_matches=60, seed=3)
        plain = players[~players.replay_enhanced]
        if not plain.empty:
            row = plain.iloc[0].copy()
            row["duration_seconds"] = 1800
            assert player_features(row) is None


class TestLadder:
    def test_finds_signal_when_signal_exists(self):
        frame = ladder_frame(n=2000, seed=23)
        report = fit_ladder(frame)
        assert report.bands, "no band cleared the accuracy floor"
        assert all(b.accuracy >= MIN_ACCURACY for b in report.bands)

    def test_bands_at_chance_are_skipped_with_a_reason(self):
        """A fit that found nothing must say so, not rank its noise."""
        frame = ladder_frame(n=600, seed=29)
        # Sever the behaviour-outcome link: reassign winners at random, keeping
        # exactly one per match so pairs still form and only the signal is gone.
        frame = frame.sort_values("game_id", kind="stable").reset_index(drop=True)
        rng = np.random.default_rng(0)
        winners: list[bool] = []
        for _, group in frame.groupby("game_id", sort=False):
            flip = bool(rng.integers(0, 2))
            winners.extend([flip, not flip][: len(group)])
        frame["winner"] = winners

        report = fit_ladder(frame)
        assert report.skipped_bands
        # A band skips either for sitting at chance or for being too small.
        # Both are legitimate; every skip must carry its reason.
        assert all(report.skipped_bands.values())
        assert any("chance" in reason for reason in report.skipped_bands.values())
        # With the link severed, almost nothing should survive as a finding.
        assert len(report.bands) <= 1

    def test_synthetic_flag_propagates(self):
        frame = ladder_frame(n=200, seed=5)
        assert fit_ladder(frame).synthetic is True

    def test_shift_table_spans_bands(self):
        frame = ladder_frame(n=1500, seed=23)
        table = fit_ladder(frame).shift_table()
        if not table.empty:
            assert table.index.name == "elo_band"
            assert len(table) >= 1
