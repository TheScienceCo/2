"""Compute metrics from replay for analytics.

Extracts relevant data from a loaded replay and computes metrics needed
for DVA, playstyle, and radar analysis.
"""

from dataclasses import dataclass
from typing import Optional

from app.db.models import Replay, ReplayPlayer


@dataclass
class PlayerMetrics:
    """Computed metrics for one player in a match."""
    
    player_number: int
    name: str
    civilization: str
    
    # Age timings (ms)
    feudal_ms: Optional[int] = None
    castle_ms: Optional[int] = None
    imperial_ms: Optional[int] = None
    
    # APM metrics
    eapm: Optional[int] = None  # Effective APM
    apm: Optional[int] = None  # Raw APM
    
    # Build order
    opening: Optional[str] = None
    
    # Military metrics
    military_spend_pct: Optional[float] = None
    military_unit_diversity: int = 0
    army_size: Optional[int] = None
    
    # Economy metrics
    resource_float_avg: Optional[float] = None
    resource_float_peak: Optional[float] = None
    villager_uptime: Optional[float] = None
    tc_idle_percentage: Optional[float] = None
    
    # Expansion metrics
    expansion_count: int = 0
    expansion_timing_ms: Optional[int] = None
    
    # Results
    winner: Optional[bool] = None


class MetricsComputeService:
    """Compute metrics from replay data."""
    
    def compute_from_replay(self, replay: Replay) -> dict[int, PlayerMetrics]:
        """Compute metrics for both players from a replay.
        
        Args:
            replay: Loaded Replay object with players
            
        Returns:
            Dictionary mapping player_number to PlayerMetrics
        """
        metrics = {}
        
        for player in replay.players:
            m = PlayerMetrics(
                player_number=player.player_number,
                name=player.name,
                civilization=player.civilization,
                feudal_ms=player.feudal_ms,
                castle_ms=player.castle_ms,
                imperial_ms=player.imperial_ms,
                eapm=player.eapm,
                opening=player.opening,
                winner=player.winner,
            )
            
            # Extract from analysis document if available
            if replay.analysis:
                self._extract_from_analysis(replay.analysis, player.player_number, m)
            
            metrics[player.player_number] = m
        
        return metrics
    
    def _extract_from_analysis(
        self,
        analysis: dict,
        player_number: int,
        metrics: PlayerMetrics,
    ) -> None:
        """Extract computed metrics from analysis document."""
        
        # Navigate to player-specific data
        players = analysis.get("players", {})
        player_key = f"player_{player_number}"
        player_analysis = players.get(player_key, {})
        
        if not player_analysis:
            return
        
        # Economy
        metrics.resource_float_avg = player_analysis.get("resource_float_avg")
        metrics.resource_float_peak = player_analysis.get("resource_float_peak")
        metrics.villager_uptime = player_analysis.get("villager_uptime")
        metrics.tc_idle_percentage = player_analysis.get("tc_idle_percentage")
        
        # Military
        metrics.military_spend_pct = player_analysis.get("military_spend_pct")
        unit_composition = player_analysis.get("unit_composition", {})
        metrics.military_unit_diversity = len([u for u, c in unit_composition.items() if c > 0])
        metrics.army_size = player_analysis.get("army_size")
        
        # Expansion
        expansions = player_analysis.get("expansions", [])
        metrics.expansion_count = len(expansions)
        if expansions:
            metrics.expansion_timing_ms = expansions[0].get("timestamp_ms")
        
        # APM
        metrics.apm = player_analysis.get("apm")
    
    def get_cohort_context(
        self,
        player_metrics: PlayerMetrics,
        cohort_baselines: dict,
    ) -> dict:
        """Build cohort context for a player.
        
        Context includes:
        - Percentiles for each metric relative to cohort
        - Mean and std for comparison
        - Specificity level that was used
        
        Args:
            player_metrics: Computed metrics for the player
            cohort_baselines: Baselines from database (from BaselineService)
            
        Returns:
            Dictionary with percentile and baseline data
        """
        context = {
            "cohort_size": cohort_baselines.get("cohort_size", 0),
            "specificity": cohort_baselines.get("specificity", 0),
            "source": cohort_baselines.get("source", "unknown"),
        }
        
        # Add percentiles and baselines for key metrics
        metric_keys = [
            ("feudal_ms", "Feudal age timing"),
            ("castle_ms", "Castle age timing"),
            ("imperial_ms", "Imperial age timing"),
            ("eapm", "EAPM"),
            ("apm", "APM"),
            ("resource_float_avg", "Resource float average"),
            ("tc_idle_percentage", "TC idle percentage"),
            ("military_spend_pct", "Military spend %"),
            ("expansion_count", "Expansion count"),
        ]
        
        for metric_key, display_name in metric_keys:
            value = getattr(player_metrics, metric_key)
            
            if value is None:
                context[f"{metric_key}_percentile"] = 50
                context[f"{metric_key}_baseline"] = None
                context[f"{metric_key}_std"] = None
                continue
            
            # Look up baseline for this metric
            baseline_data = cohort_baselines.get(metric_key, {})
            baseline_mean = baseline_data.get("mean")
            baseline_std = baseline_data.get("std")
            baseline_p50 = baseline_data.get("p50")
            
            if baseline_mean is not None and baseline_std is not None:
                # Compute percentile (assuming normal distribution)
                z_score = (value - baseline_mean) / baseline_std if baseline_std > 0 else 0
                # Rough percentile from z-score
                percentile = self._z_to_percentile(z_score)
            else:
                percentile = 50
            
            context[f"{metric_key}_percentile"] = percentile
            context[f"{metric_key}_baseline"] = baseline_mean
            context[f"{metric_key}_std"] = baseline_std
            context[f"{metric_key}_p50"] = baseline_p50
        
        return context
    
    @staticmethod
    def _z_to_percentile(z_score: float) -> int:
        """Convert z-score to percentile (rough approximation)."""
        import math
        
        # Using approximation of cumulative normal distribution
        if z_score >= 3:
            return 99
        elif z_score >= 2:
            return 97
        elif z_score >= 1:
            return 84
        elif z_score >= 0:
            return 50
        elif z_score >= -1:
            return 16
        elif z_score >= -2:
            return 3
        else:
            return 1
