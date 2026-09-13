"""Skill Ladder: what separates players *within* a rating band.

The method is a within-match paired conditional logit. For each match both
players' features are differenced and the model predicts which of the two won
from that difference alone.

Differencing is the point. Both players shared a map, a patch, a game length and
an opponent, so every match-level confounder cancels exactly rather than being
adjusted for. What survives is the part of the behaviour that differed between
two people playing the same game - which is the question a player is actually
asking when they say "what should I work on".

Fitting per Elo band answers the follow-up: the behaviours that separate players
at 1000 are not the ones that separate players at 2000, and comparing
coefficients across bands shows where the lever moves.

Coefficients are associations within a historical corpus. A feature that
separates winners from losers is not thereby a cause of winning, and nothing
here establishes that changing it would change an outcome.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

from app.core.logging import get_logger
from app.services.corpus.spend import age_durations, compute_spend

log = get_logger(__name__)

#: Below this a band cannot support a fit worth reporting.
MIN_PAIRS_PER_BAND = 40

#: A fit at or below chance has found nothing. Its coefficients are noise, and
#: reporting them ranked by magnitude would read exactly like insight.
MIN_ACCURACY = 0.55

FEATURE_LABELS = {
    "feudal_time": "Feudal Age time",
    "castle_time": "Castle Age time",
    "imperial_time": "Imperial Age time",
    "spend_total": "Total resources spent",
    "military_share_feudal": "Military share of spend (Feudal)",
    "military_share_castle": "Military share of spend (Castle)",
    "tech_share_castle": "Technology share of spend (Castle)",
    "income_proxy_feudal": "Spend rate, Feudal (income proxy)",
    "income_proxy_castle": "Spend rate, Castle (income proxy)",
}

#: Features where a lower value is the better outcome, so the reported direction
#: reads consistently as "the winner did more of this".
LOWER_IS_BETTER = frozenset({"feudal_time", "castle_time", "imperial_time"})


def player_features(row: pd.Series) -> dict[str, float] | None:
    """Feature vector for one corpus player row, or None if unusable."""
    if not row.get("replay_enhanced"):
        return None

    duration = float(row.get("duration_seconds") or 0)
    if duration <= 0:
        return None

    feudal = row.get("feudal_age_uptime")
    castle = row.get("castle_age_uptime")
    imperial = row.get("imperial_age_uptime")

    breakdown = compute_spend(row.get("replay_summary_raw"))
    if not breakdown.ages:
        return None
    durations = age_durations(duration, feudal, castle, imperial)

    features: dict[str, float] = {}
    if feudal is not None and not pd.isna(feudal):
        features["feudal_time"] = float(feudal)
    if castle is not None and not pd.isna(castle):
        features["castle_time"] = float(castle)
    if imperial is not None and not pd.isna(imperial):
        features["imperial_time"] = float(imperial)

    features["spend_total"] = float(breakdown.total.total)

    for age in ("feudal", "castle"):
        entry = breakdown.ages.get(age)
        if entry is None:
            continue
        share = entry.military_share
        if share is not None:
            features[f"military_share_{age}"] = float(share)
        income = entry.income_proxy(durations.get(age))
        if income is not None:
            features[f"income_proxy_{age}"] = float(income)
        if age == "castle":
            tech = entry.tech_share
            if tech is not None:
                features["tech_share_castle"] = float(tech)

    return features


@dataclass
class BandResult:
    """One Elo band's fit."""

    elo_band: int
    pairs: int
    accuracy: float | None
    features: dict[str, float] = field(default_factory=dict)

    def ranked(self) -> list[tuple[str, float]]:
        """Features by absolute influence, strongest first."""
        return sorted(self.features.items(), key=lambda kv: -abs(kv[1]))

    def describe(self, top: int = 5) -> list[str]:
        out = []
        for name, coefficient in self.ranked()[:top]:
            label = FEATURE_LABELS.get(name, name)
            # After differencing, a positive coefficient means the winner had
            # the larger value. For timings, larger means slower, so the
            # readable direction flips.
            winner_had_more = coefficient > 0
            if name in LOWER_IS_BETTER:
                direction = "slower" if winner_had_more else "faster"
            else:
                direction = "more" if winner_had_more else "less"
            out.append(f"{label}: winners had {direction} ({coefficient:+.2f})")
        return out


@dataclass
class LadderReport:
    bands: list[BandResult] = field(default_factory=list)
    synthetic: bool = False
    skipped_bands: dict[int, str] = field(default_factory=dict)

    def shift_table(self) -> pd.DataFrame:
        """Coefficient per feature per band - how the lever moves up the ladder."""
        if not self.bands:
            return pd.DataFrame()
        frame = pd.DataFrame({b.elo_band: b.features for b in self.bands}).T.sort_index()
        frame.index.name = "elo_band"
        return frame

    def to_json(self) -> str:
        return json.dumps(
            {
                "synthetic": self.synthetic,
                "skipped_bands": self.skipped_bands,
                "bands": [
                    {
                        "elo_band": b.elo_band,
                        "pairs": b.pairs,
                        "accuracy": b.accuracy,
                        "features": b.features,
                        "top": b.describe(),
                    }
                    for b in self.bands
                ],
            },
            indent=1,
        )


def build_pairs(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Difference each match's two players into one row.

    Returns (differenced features, label, elo band). The label is 1 when the
    first-listed player won; which player is listed first is arbitrary, so the
    sign is symmetrised by emitting both orderings.
    """
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    bands: list[int] = []

    for _, group in frame.groupby("game_id"):
        if len(group) != 2:
            continue
        a, b = group.iloc[0], group.iloc[1]
        if a.get("elo_band") != b.get("elo_band") or a.get("elo_band") is None:
            # Cross-band matches would smuggle a rating difference into the
            # comparison, which is exactly what stratifying is meant to remove.
            continue
        if a.get("winner") == b.get("winner"):
            continue

        fa, fb = player_features(a), player_features(b)
        if not fa or not fb:
            continue
        shared = set(fa) & set(fb)
        if not shared:
            continue

        diff = {k: fa[k] - fb[k] for k in shared}
        # Emit both orderings so the fit cannot learn a row-order artefact.
        rows.append(diff)
        labels.append(1 if bool(a["winner"]) else 0)
        bands.append(int(a["elo_band"]))
        rows.append({k: -v for k, v in diff.items()})
        labels.append(0 if bool(a["winner"]) else 1)
        bands.append(int(a["elo_band"]))

    return (
        pd.DataFrame(rows),
        pd.Series(labels, name="winner"),
        pd.Series(bands, name="elo_band"),
    )


def fit_ladder(frame: pd.DataFrame) -> LadderReport:
    """Fit one paired conditional logit per Elo band."""
    report = LadderReport(synthetic=bool(frame.get("synthetic", pd.Series([False])).any()))
    features, labels, bands = build_pairs(frame)
    if features.empty:
        log.warning("ladder.no_pairs")
        return report

    for band in sorted(bands.unique()):
        mask = bands == band
        X = features[mask.to_numpy()]
        y = labels[mask.to_numpy()]

        # Only keep features present for most of this band's pairs; a column
        # that is mostly missing would be imputed into noise.
        keep = [c for c in X.columns if X[c].notna().mean() > 0.8]
        X = X[keep].dropna()
        y = y.loc[X.index]

        if len(X) < MIN_PAIRS_PER_BAND or y.nunique() < 2:
            report.skipped_bands[int(band)] = f"only {len(X)} usable pairs"
            continue

        scaler = StandardScaler(with_mean=False)  # differences are already centred
        X_scaled = scaler.fit_transform(X)

        # No intercept: differencing removed it, and fitting one would let the
        # model express a preference for a row ordering that carries no meaning.
        model = LogisticRegression(fit_intercept=False, max_iter=2000, C=1.0)
        try:
            scores = cross_val_score(model, X_scaled, y, cv=min(5, len(X) // 20 or 2))
            accuracy = float(np.mean(scores))
        except ValueError:
            accuracy = None
        model.fit(X_scaled, y)

        if accuracy is not None and accuracy < MIN_ACCURACY:
            report.skipped_bands[int(band)] = (
                f"cross-validated accuracy {accuracy:.3f} is not above chance; "
                f"no behaviour separated winners in this band"
            )
            continue

        report.bands.append(
            BandResult(
                elo_band=int(band),
                pairs=len(X),
                accuracy=accuracy,
                features={
                    name: float(coefficient)
                    for name, coefficient in zip(keep, model.coef_[0], strict=True)
                },
            )
        )

    log.info("ladder.fitted", bands=len(report.bands), skipped=len(report.skipped_bands))
    return report
