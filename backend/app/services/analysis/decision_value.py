"""Decision Value Added (DVA) analysis.

Evaluates decisions' contribution to match outcome relative to peer baselines.
Since replays lack combat outcomes, DVA is based on observable choices:
- Build order and timing vs opponents
- Age advancement decisions
- Unit composition and production pacing
- Expansion patterns
- Scouting and map control
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.services.corpus.baselines import BaselineService


@dataclass
class DecisionEvaluation:
    """Evaluation of a single decision point."""

    timestamp_ms: int
    decision_type: str  # "age_advance", "build", "unit_composition", "expansion"
    value_added: float  # Relative to peer baseline (-1.0 to +1.0)
    confidence: float  # 0.0-1.0, based on cohort size and peer variance
    explanation: str  # Human-readable rationale


@dataclass
class DVAReport:
    """Summary of decision value added across the match."""

    decisions: list[DecisionEvaluation] = field(default_factory=list)
    total_value_added: float = 0.0  # Sum of value-weighted decisions
    decision_quality: str = "neutral"  # "excellent" / "good" / "neutral" / "below-average"
    top_decisions: list[DecisionEvaluation] = field(default_factory=list)
    bottom_decisions: list[DecisionEvaluation] = field(default_factory=list)
    
    def __str__(self) -> str:
        lines = [
            f"Decision Value Added Report",
            f"  Total DVA:         {self.total_value_added:+.2f}",
            f"  Quality:           {self.decision_quality}",
            f"  Decisions analyzed: {len(self.decisions)}",
            "",
            "Top 3 decisions:",
        ]
        for dec in self.top_decisions[:3]:
            lines.append(f"  @{dec.timestamp_ms//1000:>5}s | {dec.decision_type:15s} | "
                        f"+{dec.value_added:.2f} | {dec.explanation[:40]}")
        lines.append("")
        lines.append("Areas for improvement:")
        for dec in self.bottom_decisions[:3]:
            lines.append(f"  @{dec.timestamp_ms//1000:>5}s | {dec.decision_type:15s} | "
                        f"{dec.value_added:.2f} | {dec.explanation[:40]}")
        return "\n".join(lines)


class DVAAnalyzer:
    """Analyze decision value added from a replay.
    
    Since replays don't contain combat or outcome data, DVA focuses on 
    timing and strategic decisions observable from the command stream.
    """

    def __init__(self, baseline_service: BaselineService):
        self.baselines = baseline_service

    def analyze(
        self,
        metrics: dict,
        cohort_context: dict,
        opponent_metrics: dict,
    ) -> DVAReport:
        """Analyze decisions relative to peer baselines.
        
        Args:
            metrics: Player metrics from match
            cohort_context: The cohort used for comparison (role, rating, etc.)
            opponent_metrics: Opponent's metrics for relative comparison
            
        Returns:
            DVAReport with decision evaluations and explanations
        """
        report = DVAReport()
        
        # 1. Age advancement decisions
        age_decisions = self._evaluate_age_decisions(
            metrics, cohort_context, opponent_metrics
        )
        report.decisions.extend(age_decisions)
        
        # 2. Build order quality
        build_decisions = self._evaluate_build_decisions(
            metrics, cohort_context
        )
        report.decisions.extend(build_decisions)
        
        # 3. Unit composition pacing
        comp_decisions = self._evaluate_unit_composition(
            metrics, cohort_context, opponent_metrics
        )
        report.decisions.extend(comp_decisions)
        
        # 4. Expansion decisions
        exp_decisions = self._evaluate_expansion(
            metrics, cohort_context, opponent_metrics
        )
        report.decisions.extend(exp_decisions)
        
        # Aggregate
        report.total_value_added = sum(
            d.value_added * (d.confidence ** 2)  # Weight by confidence squared
            for d in report.decisions
        ) / max(1, len(report.decisions))
        
        # Classify quality
        if report.total_value_added > 0.3:
            report.decision_quality = "excellent"
        elif report.total_value_added > 0.1:
            report.decision_quality = "good"
        elif report.total_value_added < -0.2:
            report.decision_quality = "below-average"
        else:
            report.decision_quality = "neutral"
        
        # Find top and bottom
        sorted_decisions = sorted(
            report.decisions,
            key=lambda d: d.value_added * d.confidence,
            reverse=True
        )
        report.top_decisions = sorted_decisions[:5]
        report.bottom_decisions = sorted(
            report.decisions,
            key=lambda d: d.value_added * d.confidence
        )[:5]
        
        return report
    
    def _evaluate_age_decisions(
        self,
        metrics: dict,
        cohort: dict,
        opponent: dict,
    ) -> list[DecisionEvaluation]:
        """Evaluate age advancement timing decisions."""
        decisions = []
        ages = ["feudal", "castle", "imperial"]
        
        for age in ages:
            ours = metrics.get(f"{age}_ms")
            theirs = opponent.get(f"{age}_ms")
            baseline = cohort.get(f"{age}_baseline_ms")

            if not all([ours, theirs, baseline]):
                continue

            # Type guards
            assert isinstance(ours, (int, float)) and ours is not None
            assert isinstance(theirs, (int, float)) and theirs is not None
            assert isinstance(baseline, (int, float)) and baseline is not None

            # Value added: how much faster than opponent relative to peer baseline
            peer_gap = baseline - ours  # Positive = faster than peers
            our_gap = theirs - ours  # Positive = we're faster
            
            # Normalize: value_added in [-1, 1]
            peer_std = cohort.get(f"{age}_std_ms", 30)
            value = float(np.clip(our_gap / peer_std, -1.0, 1.0))
            
            # Confidence: higher when cohort is large
            cohort_size = cohort.get("cohort_size", 100)
            confidence = float(np.clip(cohort_size / 500.0, 0.0, 1.0))
            
            decisions.append(
                DecisionEvaluation(
                    timestamp_ms=int(ours),
                    decision_type=f"age_advance/{age}",
                    value_added=value,
                    confidence=confidence,
                    explanation=f"Reached {age} {our_gap:+.0f}ms vs opponent, "
                               f"{peer_gap:+.0f}ms vs peer baseline",
                )
            )
        
        return decisions
    
    def _evaluate_build_decisions(
        self,
        metrics: dict,
        cohort: dict,
    ) -> list[DecisionEvaluation]:
        """Evaluate build order quality against peers."""
        decisions = []
        
        # Compare opening chosen vs peer distribution for that rating/civ
        opening = metrics.get("opening_name")
        opening_rate = cohort.get(f"opening_{opening}_rate", 0.0)
        
        if opening and opening_rate:
            # Value: picking a high-frequency, meta-appropriate opening
            meta_fit = opening_rate - 0.1  # Above 10% = meta-relevant
            value = float(np.clip(meta_fit / 0.3, -0.5, 0.5))
            
            decisions.append(
                DecisionEvaluation(
                    timestamp_ms=0,
                    decision_type="build/opening",
                    value_added=value,
                    confidence=0.6,
                    explanation=f"Opening {opening} chosen by {opening_rate:.0%} of peers",
                )
            )
        
        return decisions
    
    def _evaluate_unit_composition(
        self,
        metrics: dict,
        cohort: dict,
        opponent: dict,
    ) -> list[DecisionEvaluation]:
        """Evaluate unit composition decisions."""
        decisions = []
        
        # Military composition relative to opponent
        our_comp = metrics.get("unit_composition", {})
        their_comp = opponent.get("unit_composition", {})
        
        # Simple heuristic: composition diversity and production pacing
        our_unit_types = len([u for u, c in our_comp.items() if c > 0])
        their_unit_types = len([u for u, c in their_comp.items() if c > 0])
        
        if our_unit_types and their_unit_types:
            # Diversity relative to opponent
            diversity_advantage = (our_unit_types - their_unit_types) / max(1, their_unit_types)
            value = float(np.clip(diversity_advantage, -0.5, 0.5))
            
            decisions.append(
                DecisionEvaluation(
                    timestamp_ms=metrics.get("castle_ms", 0),
                    decision_type="military/composition",
                    value_added=value,
                    confidence=0.5,
                    explanation=f"Unit diversity: {our_unit_types} types vs opponent's {their_unit_types}",
                )
            )
        
        return decisions
    
    def _evaluate_expansion(
        self,
        metrics: dict,
        cohort: dict,
        opponent: dict,
    ) -> list[DecisionEvaluation]:
        """Evaluate expansion timing and density."""
        decisions = []
        
        our_expansions = metrics.get("expansion_count", 0)
        their_expansions = opponent.get("expansion_count", 0)
        baseline_expansions = cohort.get("expansion_count_mean", 2)
        
        if our_expansions or their_expansions:
            # Value: expanding more than opponent relative to peer baseline
            expansion_advantage = (our_expansions - their_expansions) / max(1, baseline_expansions)
            value = float(np.clip(expansion_advantage * 0.2, -0.5, 0.5))
            
            decisions.append(
                DecisionEvaluation(
                    timestamp_ms=metrics.get("castle_ms", 0),
                    decision_type="strategic/expansion",
                    value_added=value,
                    confidence=0.6,
                    explanation=f"Expansions: {our_expansions} vs opponent {their_expansions}, "
                               f"peer average {baseline_expansions}",
                )
            )
        
        return decisions
