"""Parser validation against external corpus baseline.

Compares computed metrics (age timings, build order patterns) against aoestats.io
corpus to verify parser accuracy and identify systematic biases.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.services.analysis.metrics import analyze


@dataclass
class TimingValidation:
    """Results for a single age timing comparison."""

    age: str
    ours_ms: Optional[int]
    theirs_ms: Optional[int]
    error_ms: Optional[int] = None
    error_pct: Optional[float] = None

    def __post_init__(self):
        if self.ours_ms is not None and self.theirs_ms is not None:
            self.error_ms = self.ours_ms - self.theirs_ms
            self.error_pct = 100.0 * self.error_ms / self.theirs_ms


@dataclass
class ValidationReport:
    """Summary of parser validation against corpus baseline."""

    n_comparisons: int
    ages: dict[str, list[TimingValidation]]
    mae_ms: dict[str, float]  # Mean absolute error per age
    bias_ms: dict[str, float]  # Mean signed error (systematic bias)
    coverage: dict[str, float]  # % of replays with both measurements

    def __str__(self) -> str:
        lines = [
            f"Parser Validation Report ({self.n_comparisons} replays)",
            "",
        ]
        for age in ["feudal", "castle", "imperial"]:
            if age in self.mae_ms:
                mae = self.mae_ms[age]
                bias = self.bias_ms.get(age, 0)
                cov = self.coverage.get(age, 0)
                lines.append(
                    f"{age:8s} | MAE {mae:6.0f}ms | "
                    f"bias {bias:+7.0f}ms | coverage {cov:5.1f}%"
                )
        return "\n".join(lines)


def validate_parser(
    replays: list[tuple],  # (ParsedReplay, CorpusMatch) pairs
) -> ValidationReport:
    """Validate parser against corpus baseline.

    Args:
        replays: List of (ParsedReplay, CorpusMatch) tuples from the corpus.
                 ParsedReplay from our parser, CorpusMatch from aoestats.io.

    Returns:
        ValidationReport with MAE per age and systematic bias detection.
    """
    validations: dict[str, list[TimingValidation]] = {
        "feudal": [],
        "castle": [],
        "imperial": [],
    }

    for parsed_replay, corpus_match in replays:
        # Analyze our parser result
        metrics_p1 = analyze(parsed_replay, player=1)
        metrics_p2 = analyze(parsed_replay, player=2)

        # Get timings from corpus (assume stored as milliseconds)
        corpus_p1_timings = corpus_match.timings.get("player_1", {})
        corpus_p2_timings = corpus_match.timings.get("player_2", {})

        # Compare P1
        for age in ["feudal", "castle", "imperial"]:
            ours = metrics_p1.age_timings_ms.get(age)
            theirs = corpus_p1_timings.get(age)
            validations[age].append(TimingValidation(age, ours, theirs))

        # Compare P2
        for age in ["feudal", "castle", "imperial"]:
            ours = metrics_p2.age_timings_ms.get(age)
            theirs = corpus_p2_timings.get(age)
            validations[age].append(TimingValidation(age, ours, theirs))

    # Compute statistics
    mae_ms = {}
    bias_ms = {}
    coverage = {}

    for age in ["feudal", "castle", "imperial"]:
        errors = [
            v.error_ms
            for v in validations[age]
            if v.error_ms is not None
        ]

        if errors:
            mae_ms[age] = float(np.mean(np.abs(errors)))
            bias_ms[age] = float(np.mean(errors))
            coverage[age] = 100.0 * len(errors) / len(validations[age])
        else:
            mae_ms[age] = np.nan
            bias_ms[age] = np.nan
            coverage[age] = 0.0

    return ValidationReport(
        n_comparisons=len(replays),
        ages=validations,
        mae_ms=mae_ms,
        bias_ms=bias_ms,
        coverage=coverage,
    )
