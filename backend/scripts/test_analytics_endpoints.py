#!/usr/bin/env python3
"""Test analytics endpoints with sample data."""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import session_scope
from app.utils.test_data import create_sample_replay
from app.services.analysis.compute import MetricsComputeService
from app.services.analysis.decision_value import DVAAnalyzer
from app.services.analysis.playstyle import PlaystyleAnalyzer
from app.services.corpus.baselines import BaselineService, cohort_key


def test_metrics_extraction():
    """Test extracting metrics from a replay."""
    print("\n=== Testing Metrics Extraction ===")

    replay = create_sample_replay()
    service = MetricsComputeService()
    metrics = service.compute_from_replay(replay)

    for player_num, player_metrics in metrics.items():
        print(f"\nPlayer {player_num}:")
        print(f"  Name: {player_metrics.name}")
        print(f"  Civilization: {player_metrics.civilization}")
        print(f"  Feudal: {player_metrics.feudal_ms}ms")
        print(f"  Castle: {player_metrics.castle_ms}ms")
        print(f"  Imperial: {player_metrics.imperial_ms}ms")
        print(f"  EAPM: {player_metrics.eapm}")
        print(f"  Opening: {player_metrics.opening}")
        print(f"  Expansion count: {player_metrics.expansion_count}")


def test_cohort_lookup():
    """Test looking up cohort baselines."""
    print("\n=== Testing Cohort Lookup ===")

    with session_scope() as db:
        service = BaselineService(db)

        # Try to look up a baseline
        baseline = service.lookup(
            metric="feudal_age_uptime",
            dimensions={"elo_band": 1400, "civ": "Franks"},
        )

        if baseline:
            print(f"Found baseline: {baseline.metric}")
            print(f"  Cohort size: {baseline.n}")
            print(f"  Mean: {baseline.mean:.2f}")
            print(f"  Std: {baseline.std:.2f}")
        else:
            print("No baseline found (may need to populate database)")


def test_dva_analysis():
    """Test DVA analysis with sample data."""
    print("\n=== Testing DVA Analysis ===")

    with session_scope() as db:
        replay = create_sample_replay()

        # Extract metrics
        service = MetricsComputeService()
        metrics = service.compute_from_replay(replay)

        p1_metrics = metrics[1]
        p2_metrics = metrics[2]

        # Create mock cohort context
        cohort_context = {
            "feudal_baseline_ms": 550,
            "feudal_std_ms": 50,
            "castle_baseline_ms": 1200,
            "castle_std_ms": 100,
            "imperial_baseline_ms": 2400,
            "imperial_std_ms": 150,
            "cohort_size": 100,
        }

        # Run DVA analysis
        baseline_service = BaselineService(db)
        analyzer = DVAAnalyzer(baseline_service)

        # Convert metrics to dicts
        p1_dict = {
            "feudal_ms": p1_metrics.feudal_ms,
            "castle_ms": p1_metrics.castle_ms,
            "imperial_ms": p1_metrics.imperial_ms,
            "opening": p1_metrics.opening,
            "expansion_count": p1_metrics.expansion_count,
        }

        p2_dict = {
            "feudal_ms": p2_metrics.feudal_ms,
            "castle_ms": p2_metrics.castle_ms,
            "imperial_ms": p2_metrics.imperial_ms,
            "opening": p2_metrics.opening,
            "expansion_count": p2_metrics.expansion_count,
        }

        report = analyzer.analyze(
            metrics=p1_dict,
            cohort_context=cohort_context,
            opponent_metrics=p2_dict,
        )

        print(f"Decision Value Added: {report.total_value_added:+.2f}")
        print(f"Decision Quality: {report.decision_quality}")
        print(f"Total Decisions: {len(report.decisions)}")

        for decision in report.decisions[:3]:
            print(f"  - {decision.decision_type}: {decision.value_added:+.2f}")


def test_playstyle_analysis():
    """Test playstyle analysis with sample data."""
    print("\n=== Testing Playstyle Analysis ===")

    replay = create_sample_replay()

    # Extract metrics
    service = MetricsComputeService()
    metrics = service.compute_from_replay(replay)
    p1_metrics = metrics[1]

    # Create mock cohort context
    cohort_context = {
        "feudal_ms_percentile": 60,
        "castle_ms_percentile": 50,
        "military_spend_pct_percentile": 45,
        "resource_float_percentile": 55,
        "expansion_count_percentile": 70,
    }

    # Run playstyle analysis
    analyzer = PlaystyleAnalyzer()

    p1_dict = {
        "feudal_ms": p1_metrics.feudal_ms,
        "castle_ms": p1_metrics.castle_ms,
        "military_spend_pct": p1_metrics.military_spend_pct,
        "expansion_count": p1_metrics.expansion_count,
    }

    profile = analyzer.analyze(
        metrics=p1_dict,
        cohort_context=cohort_context,
    )

    print(f"Primary Archetype: {profile.primary_archetype.value}")
    print(f"Confidence: {profile.archetype_confidence:.0%}")
    print(f"Awards: {len(profile.awards)}")
    print(f"Strengths: {len(profile.strengths)}")
    print(f"Weaknesses: {len(profile.weaknesses)}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Analytics Endpoints Test Suite")
    print("=" * 60)

    try:
        test_metrics_extraction()
        test_cohort_lookup()
        test_dva_analysis()
        test_playstyle_analysis()

        print("\n" + "=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
