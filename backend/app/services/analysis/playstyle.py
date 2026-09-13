"""Playstyle archetype classification and awards.

Identifies unique strengths and categorizes players into strategic archetypes
based on observable patterns: build preferences, military focus, economy efficiency,
expansion aggressiveness, and scouting behavior.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlaystyleArchetype(str, Enum):
    """Strategic archetypes based on decision patterns."""
    
    ARCHER_RUSH = "archer_rush"  # Early military, all-in aggression
    CASTLE_POWER = "castle_power"  # Strong castle age, composition focus
    TROOP_HOARD = "troop_hoard"  # Large army, unit volume
    NINJA_ECONOMY = "ninja_economy"  # Minimal visible army, massive economy
    POCKET_AGGRESSIVE = "pocket_aggressive"  # Team player: aggressive helper
    BOOM_DOMINATION = "boom_domination"  # Explosive growth, many expansions
    TURTLE_DEFENDER = "turtle_defender"  # Defensive, high production, reactive
    MICRO_SPECIALIST = "micro_specialist"  # High APM, precision unit movement
    BALANCED = "balanced"  # No dominant pattern


@dataclass
class PlaystyleAward:
    """Recognition for a unique strength."""
    
    award: str  # e.g., "Fastest Feudal", "Army Hoarding Expert"
    category: str  # "timing" / "economy" / "military" / "strategy"
    percentile: int  # 0-100, where player ranks vs cohort (higher = better)
    explanation: str  # Why they earned this award
    rarity: str  # "common" / "uncommon" / "rare" / "legendary"


@dataclass
class PlaystyleProfile:
    """Complete playstyle analysis."""
    
    primary_archetype: PlaystyleArchetype
    secondary_archetype: Optional[PlaystyleArchetype] = None
    archetype_confidence: float = 0.5  # 0.0-1.0
    
    awards: list[PlaystyleAward] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)  # Top 3 metrics
    weaknesses: list[str] = field(default_factory=list)  # Bottom 3 metrics
    
    def __str__(self) -> str:
        lines = [
            f"Playstyle: {self.primary_archetype.value.replace('_', ' ').title()}",
            f"Confidence: {self.archetype_confidence:.0%}",
        ]
        
        if self.secondary_archetype:
            lines.append(f"Also exhibits: {self.secondary_archetype.value.replace('_', ' ').title()}")
        
        if self.strengths:
            lines.append("\nTop Strengths:")
            for s in self.strengths:
                lines.append(f"  • {s}")
        
        if self.awards:
            lines.append("\nAwards:")
            for award in sorted(self.awards, key=lambda a: a.percentile, reverse=True)[:5]:
                lines.append(f"  🏆 {award.award} ({award.percentile}th percentile)")
        
        if self.weaknesses:
            lines.append("\nAreas to Improve:")
            for w in self.weaknesses:
                lines.append(f"  • {w}")
        
        return "\n".join(lines)


class PlaystyleAnalyzer:
    """Classify player playstyle and award recognition."""
    
    # Thresholds for archetype classification
    ARCHETYPE_THRESHOLDS = {
        PlaystyleArchetype.ARCHER_RUSH: {
            "feudal_ms_percentile": (0, 25),  # Very fast feudal
            "feudal_military_spend_pct": (40, 100),  # 40%+ military in feudal
        },
        PlaystyleArchetype.CASTLE_POWER: {
            "castle_ms_percentile": (0, 40),  # Fast/normal castle
            "military_unit_diversity": (5, 20),  # Multiple unit types
            "army_value_at_castle": (80, 100),  # Percentile
        },
        PlaystyleArchetype.TROOP_HOARD: {
            "military_spend_pct": (60, 100),  # Very high military spend overall
            "army_size_percentile": (75, 100),  # Large armies
        },
        PlaystyleArchetype.NINJA_ECONOMY: {
            "military_spend_pct": (0, 30),  # Low military spend
            "resource_float_percentile": (75, 100),  # Much higher than average
        },
        PlaystyleArchetype.BOOM_DOMINATION: {
            "expansion_count": (4, 20),  # Many expansions
            "expansion_timing_percentile": (75, 100),  # Early/aggressive
        },
        PlaystyleArchetype.TURTLE_DEFENDER: {
            "idle_time_percentile": (75, 100),  # High idle (reactive play)
            "production_pacing": (50, 100),  # Steady, not aggressive
        },
    }
    
    # Award criteria (metric, percentile threshold, rarity)
    AWARDS = [
        ("Fastest Feudal", "feudal_ms_percentile", (0, 10), "legendary"),
        ("Lightning Castle", "castle_ms_percentile", (0, 10), "legendary"),
        ("Army Hoarder", "army_size_percentile", (90, 100), "rare"),
        ("Economic Virtuoso", "resource_efficiency_percentile", (90, 100), "rare"),
        ("Expansion Specialist", "expansion_count_percentile", (85, 100), "uncommon"),
        ("Micro Master", "apm_percentile", (90, 100), "uncommon"),
        ("Defense Maestro", "defense_success_percentile", (90, 100), "uncommon"),
        ("Map Control", "map_coverage_percentile", (85, 100), "uncommon"),
        ("Unit Composition Expert", "unit_diversity_percentile", (80, 100), "common"),
        ("Steady Eddy", "income_consistency_percentile", (85, 100), "common"),
    ]
    
    def analyze(self, metrics: dict, cohort_context: dict) -> PlaystyleProfile:
        """Analyze player playstyle and award achievements.
        
        Args:
            metrics: Player match metrics
            cohort_context: Cohort percentiles and statistics
            
        Returns:
            PlaystyleProfile with archetype and awards
        """
        profile = PlaystyleProfile(
            primary_archetype=PlaystyleArchetype.BALANCED
        )
        
        # Score each archetype
        archetype_scores = {}
        for archetype, thresholds in self.ARCHETYPE_THRESHOLDS.items():
            score = self._score_archetype(metrics, cohort_context, thresholds)
            archetype_scores[archetype] = score
        
        # Find primary and secondary archetypes
        sorted_archetypes = sorted(
            archetype_scores.items(), key=lambda x: x[1], reverse=True
        )
        
        if sorted_archetypes[0][1] > 0.4:  # Minimum threshold
            profile.primary_archetype = sorted_archetypes[0][0]
            profile.archetype_confidence = min(1.0, sorted_archetypes[0][1])
            
            if sorted_archetypes[1][1] > 0.3:
                profile.secondary_archetype = sorted_archetypes[1][0]
        
        # Award achievements
        profile.awards = self._award_achievements(metrics, cohort_context)
        
        # Identify strengths and weaknesses
        profile.strengths = self._get_strengths(metrics, cohort_context)
        profile.weaknesses = self._get_weaknesses(metrics, cohort_context)
        
        return profile
    
    def _score_archetype(
        self,
        metrics: dict,
        cohort_context: dict,
        thresholds: dict,
    ) -> float:
        """Score how well a player matches an archetype (0.0-1.0)."""
        matches = 0
        total = 0
        
        for metric_name, (min_val, max_val) in thresholds.items():
            total += 1
            percentile = cohort_context.get(f"{metric_name}_percentile", 50)
            
            if min_val <= percentile <= max_val:
                matches += 1
        
        return matches / max(1, total) if total > 0 else 0.0
    
    def _award_achievements(
        self,
        metrics: dict,
        cohort_context: dict,
    ) -> list[PlaystyleAward]:
        """Determine which awards the player earned."""
        awards = []
        
        for award_name, metric_key, (min_pct, max_pct), rarity in self.AWARDS:
            percentile = cohort_context.get(f"{metric_key}_percentile", 0)
            
            if min_pct <= percentile <= max_pct:
                awards.append(
                    PlaystyleAward(
                        award=award_name,
                        category=self._categorize_metric(metric_key),
                        percentile=int(percentile),
                        explanation=f"Ranked {percentile:.0f}th percentile in {metric_key}",
                        rarity=rarity,
                    )
                )
        
        return sorted(awards, key=lambda a: a.percentile, reverse=True)
    
    def _categorize_metric(self, metric: str) -> str:
        """Categorize a metric into timing/economy/military/strategy."""
        if "feudal" in metric or "castle" in metric or "imperial" in metric:
            return "timing"
        elif "economy" in metric or "resource" in metric or "income" in metric:
            return "economy"
        elif "army" in metric or "military" in metric or "unit" in metric:
            return "military"
        else:
            return "strategy"
    
    def _get_strengths(self, metrics: dict, cohort_context: dict) -> list[str]:
        """Get top 3 performance areas."""
        strength_metrics = [
            (k.replace("_percentile", ""), v)
            for k, v in cohort_context.items()
            if k.endswith("_percentile") and isinstance(v, (int, float))
        ]
        
        # Sort by percentile descending
        strength_metrics.sort(key=lambda x: x[1], reverse=True)
        
        strengths = []
        for metric_name, percentile in strength_metrics[:3]:
            if percentile >= 70:  # Only include strong areas
                strengths.append(
                    f"{metric_name.replace('_', ' ').title()} "
                    f"({percentile:.0f}th percentile)"
                )
        
        return strengths
    
    def _get_weaknesses(self, metrics: dict, cohort_context: dict) -> list[str]:
        """Get top 3 areas for improvement."""
        weakness_metrics = [
            (k.replace("_percentile", ""), v)
            for k, v in cohort_context.items()
            if k.endswith("_percentile") and isinstance(v, (int, float))
        ]
        
        # Sort by percentile ascending
        weakness_metrics.sort(key=lambda x: x[1])
        
        weaknesses = []
        for metric_name, percentile in weakness_metrics[:3]:
            if percentile <= 30:  # Only include weak areas
                weaknesses.append(
                    f"{metric_name.replace('_', ' ').title()} "
                    f"({percentile:.0f}th percentile)"
                )
        
        return weaknesses
