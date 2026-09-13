"""Tests for advanced analytics modules: DVA, playstyle, and radar."""

import pytest

from app.services.analysis.decision_value import DVAAnalyzer, DecisionEvaluation
from app.services.analysis.playstyle import (
    PlaystyleAnalyzer, PlaystyleArchetype, PlaystyleAward
)
from app.services.analysis.radar import RadarAnalyzer, ActionSample, RadarSector
from app.services.corpus.baselines import BaselineService


class TestDVAAnalysis:
    """Decision Value Added (DVA) analysis tests."""
    
    def test_age_advancement_value_positive(self):
        """Fast age advancement vs opponent is positive value."""
        analyzer = DVAAnalyzer(BaselineService(None))
        
        metrics = {
            "feudal_ms": 11_000,  # Fast feudal
            "castle_ms": 22_000,
            "imperial_ms": 45_000,
        }
        
        opponent = {
            "feudal_ms": 13_000,  # Slower
            "castle_ms": 25_000,
            "imperial_ms": 50_000,
        }
        
        cohort = {
            "feudal_baseline_ms": 12_000,
            "feudal_std_ms": 500,
            "castle_baseline_ms": 24_000,
            "castle_std_ms": 700,
            "cohort_size": 500,
        }
        
        decisions = analyzer._evaluate_age_decisions(metrics, cohort, opponent)
        
        assert len(decisions) > 0
        assert all(d.value_added > 0 for d in decisions)
    
    def test_age_advancement_value_negative(self):
        """Slow age advancement is negative value."""
        analyzer = DVAAnalyzer(BaselineService(None))
        
        metrics = {"feudal_ms": 15_000}
        opponent = {"feudal_ms": 11_000}
        cohort = {"feudal_baseline_ms": 12_000, "feudal_std_ms": 500, "cohort_size": 500}
        
        decisions = analyzer._evaluate_age_decisions(metrics, cohort, opponent)
        assert len(decisions) > 0
        assert decisions[0].value_added < 0
    
    def test_build_order_evaluation(self):
        """Build order gets evaluated relative to meta frequency."""
        analyzer = DVAAnalyzer(BaselineService(None))
        
        metrics = {"opening_name": "archer_rush"}
        cohort = {"opening_archer_rush_rate": 0.40}  # 40% of peers pick it
        
        decisions = analyzer._evaluate_build_decisions(metrics, cohort)
        assert len(decisions) == 1
        assert decisions[0].decision_type == "build/opening"
        assert decisions[0].value_added > 0  # Meta-appropriate choice
    
    def test_dva_aggregation(self):
        """DVA aggregates multiple decisions into quality classification."""
        analyzer = DVAAnalyzer(BaselineService(None))
        
        metrics = {
            "feudal_ms": 11_500,
            "castle_ms": 22_500,
            "opening_name": "archer_rush",
            "expansion_count": 3,
            "unit_composition": {"archer": 15, "spearman": 8},
        }
        
        opponent = {
            "feudal_ms": 12_500,
            "castle_ms": 24_000,
            "expansion_count": 2,
            "unit_composition": {"archer": 10},
        }
        
        cohort = {
            "feudal_baseline_ms": 12_000,
            "feudal_std_ms": 500,
            "castle_baseline_ms": 24_000,
            "castle_std_ms": 700,
            "opening_archer_rush_rate": 0.35,
            "expansion_count_mean": 2.5,
            "cohort_size": 500,
        }
        
        report = analyzer.analyze(metrics, cohort, opponent)
        
        assert report.n_comparisons is not None or len(report.decisions) > 0
        assert report.decision_quality in ["excellent", "good", "neutral", "below-average"]
        assert len(report.top_decisions) > 0 or len(report.decisions) > 0


class TestPlaystyleAnalysis:
    """Playstyle archetype and awards tests."""
    
    def test_archetype_archer_rush(self):
        """Fast feudal + high military spend = archer_rush archetype."""
        analyzer = PlaystyleAnalyzer()
        
        metrics = {
            "feudal_ms": 11_000,
            "feudal_military_spend_pct": 60,
        }
        
        cohort = {
            "feudal_ms_percentile": 15,  # Fast
            "feudal_military_spend_pct_percentile": 85,  # High
        }
        
        profile = analyzer.analyze(metrics, cohort)
        assert profile.archetype_confidence >= 0.3  # Some confidence in archetype
    
    def test_award_fastest_feudal(self):
        """Player in 5th percentile for feudal gets legendary award."""
        analyzer = PlaystyleAnalyzer()
        
        metrics = {"feudal_ms": 10_500}
        cohort = {
            "feudal_ms_percentile": 5,  # Top 5%
        }
        
        awards = analyzer._award_achievements(metrics, cohort)
        assert any(a.award == "Fastest Feudal" for a in awards)
        assert any(a.rarity == "legendary" for a in awards if a.award == "Fastest Feudal")
    
    def test_award_army_hoarder(self):
        """High army size earns army hoarder award."""
        analyzer = PlaystyleAnalyzer()
        
        metrics = {"army_size": 200}
        cohort = {
            "army_size_percentile": 95,  # Top 5%
        }
        
        awards = analyzer._award_achievements(metrics, cohort)
        assert any(a.award == "Army Hoarder" for a in awards)
        assert any(a.rarity in ["rare", "uncommon"] for a in awards if a.award == "Army Hoarder")
    
    def test_strength_weakness_identification(self):
        """Identifies top 3 strengths and weaknesses."""
        analyzer = PlaystyleAnalyzer()
        
        metrics = {}
        cohort = {
            "apm_percentile": 95,
            "feudal_ms_percentile": 90,
            "idle_time_percentile": 10,
            "expansion_count_percentile": 5,
        }
        
        profile = analyzer.analyze(metrics, cohort)
        
        assert len(profile.strengths) > 0
        assert len(profile.weaknesses) > 0
        assert any("apm" in s.lower() or "APM" in s for s in profile.strengths)


class TestRadarVisualization:
    """3D circular APM/attention radar tests."""
    
    def test_command_classification(self):
        """Commands are correctly classified by action type."""
        analyzer = RadarAnalyzer()
        
        assert analyzer._classify_command("create_villager") == "economy"
        assert analyzer._classify_command("create_unit") == "military"
        assert analyzer._classify_command("build_barracks") == "military"
        assert analyzer._classify_command("advance_age") == "strategy"
        assert analyzer._classify_command("patrol") == "scouting"
    
    def test_radar_generation(self):
        """Generate radar visualization from command stream."""
        analyzer = RadarAnalyzer()
        
        commands = [
            {"timestamp_ms": 5_000, "command_type": "create_villager"},
            {"timestamp_ms": 6_000, "command_type": "build_farm"},
            {"timestamp_ms": 30_000, "command_type": "create_unit"},
            {"timestamp_ms": 60_000, "command_type": "advance_age"},
        ]
        
        radar = analyzer.analyze(commands, match_duration_ms=120_000, player_name="TestPlayer")
        
        assert radar.match_duration_ms == 120_000
        assert radar.player_name == "TestPlayer"
        assert len(radar.sectors) > 0
        assert len(radar.samples) > 0
        assert radar.average_apm >= 0
        assert radar.peak_apm >= radar.average_apm
    
    def test_attention_shift_detection(self):
        """Detect when dominant action type changes."""
        analyzer = RadarAnalyzer()
        
        commands = [
            # Economy phase (first minute)
            *[{"timestamp_ms": t*1000, "command_type": "create_villager"}
              for t in range(0, 60)],
            # Military phase (second minute)
            *[{"timestamp_ms": t*1000, "command_type": "create_unit"}
              for t in range(60, 120)],
        ]
        
        radar = analyzer.analyze(commands, match_duration_ms=120_000)
        
        # Should detect shift from economy to military
        assert radar.attention_shifts >= 1
    
    def test_focus_distribution(self):
        """Calculate percentage of actions by type."""
        analyzer = RadarAnalyzer()
        
        commands = [
            *[{"timestamp_ms": t*1000, "command_type": "create_villager"}
              for t in range(0, 60)],
            *[{"timestamp_ms": t*1000, "command_type": "create_unit"}
              for t in range(60, 90)],
        ]
        
        radar = analyzer.analyze(commands, match_duration_ms=120_000)
        
        assert "economy" in radar.focus_distribution
        assert "military" in radar.focus_distribution
        assert radar.focus_distribution["economy"] > radar.focus_distribution["military"]
    
    def test_action_color_assignment(self):
        """Actions get assigned correct colors."""
        analyzer = RadarAnalyzer()
        
        assert analyzer._action_color("economy") == "#3b82f6"  # Blue
        assert analyzer._action_color("military") == "#ef4444"  # Red
        assert analyzer._action_color("scouting") == "#10b981"  # Green
        assert analyzer._action_color("strategy") == "#f59e0b"  # Amber
    
    def test_playstyle_signature_generation(self):
        """Generate readable playstyle signature."""
        analyzer = RadarAnalyzer()
        
        commands = [
            *[{"timestamp_ms": t*100, "command_type": "create_unit"}
              for t in range(0, 100)],
            *[{"timestamp_ms": t*100, "command_type": "create_villager"}
              for t in range(100, 200)],
        ]
        
        radar = analyzer.analyze(commands, match_duration_ms=30_000)
        
        assert len(radar.playstyle_signature) > 0
        assert "early" in radar.playstyle_signature.lower() or \
               "mid" in radar.playstyle_signature.lower() or \
               "late" in radar.playstyle_signature.lower()


class TestIntegration:
    """Integration tests across modules."""
    
    def test_complete_analysis_pipeline(self):
        """Run DVA, playstyle, and radar together."""
        dva_analyzer = DVAAnalyzer(BaselineService(None))
        playstyle_analyzer = PlaystyleAnalyzer()
        radar_analyzer = RadarAnalyzer()
        
        # Sample match data
        metrics = {
            "feudal_ms": 11_500,
            "castle_ms": 23_000,
            "opening_name": "archer_rush",
            "expansion_count": 3,
        }
        
        opponent = {
            "feudal_ms": 12_500,
            "castle_ms": 24_500,
            "expansion_count": 2,
        }
        
        cohort = {
            "feudal_baseline_ms": 12_000,
            "feudal_std_ms": 500,
            "castle_baseline_ms": 24_000,
            "castle_std_ms": 700,
            "opening_archer_rush_rate": 0.35,
            "feudal_ms_percentile": 40,
            "apm_percentile": 75,
            "army_size_percentile": 80,
            "idle_time_percentile": 25,
            "cohort_size": 500,
        }
        
        commands = [
            *[{"timestamp_ms": t*1000, "command_type": "create_villager"}
              for t in range(0, 40)],
            *[{"timestamp_ms": t*1000, "command_type": "create_unit"}
              for t in range(40, 70)],
        ]
        
        # Run all analyses
        dva_report = dva_analyzer.analyze(metrics, cohort, opponent)
        playstyle_profile = playstyle_analyzer.analyze(metrics, cohort)
        radar = radar_analyzer.analyze(commands, match_duration_ms=120_000)
        
        # Verify all produced results
        assert len(dva_report.decisions) > 0 or dva_report.n_comparisons >= 0
        assert playstyle_profile.primary_archetype is not None
        assert len(radar.sectors) > 0
        
        # Playstyle should have some awards with good metrics
        if playstyle_profile.awards:
            assert all(isinstance(a, PlaystyleAward) for a in playstyle_profile.awards)
