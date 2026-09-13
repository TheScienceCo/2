"""Plain-language observations derived from measured values.

Every line this produces cites a number that was actually measured. There is no
generic advice here ("improve your economy"): if we cannot measure it, we do not
say anything about it.

These are observations, not causal claims. A player who floated resources and
lost did not necessarily lose *because* they floated.
"""

from __future__ import annotations

from app.services.analysis.metrics import MatchAnalysis, Metric, PlayerAnalysis
from app.services.parser.types import Availability


def _clock(ms: float) -> str:
    total = int(ms) // 1000
    return f"{total // 60}:{total % 60:02d}"


def _known(metric: Metric | None) -> float | None:
    """The metric's value, or None when it was not measured.

    Returning the value rather than a boolean keeps the null check and the use
    in one place, so a metric can never be read without having been checked.
    """
    if metric is None or metric.value is None:
        return None
    if metric.availability is Availability.UNAVAILABLE:
        return None
    return float(metric.value)


def for_player(analysis: MatchAnalysis, player: PlayerAnalysis) -> list[str]:
    out: list[str] = []
    m = player.metrics

    # --- Age timings ------------------------------------------------------
    for age in ("feudal", "castle", "imperial"):
        reached = _known(m.get(f"{age}_time"))
        if reached is None:
            continue
        line = f"Reached {age.title()} Age at {_clock(reached)}"
        delta = _known(m.get(f"{age}_delta"))
        if delta is None:
            line += "."
        elif delta < 0:
            line += f", {_clock(-delta)} ahead of your opponent."
        elif delta > 0:
            line += f", {_clock(delta)} behind your opponent."
        else:
            line += ", level with your opponent."
        out.append(line)

    # --- Floating ---------------------------------------------------------
    peak = _known(m.get("float_peak"))
    floating = _known(m.get("time_floating"))
    if peak is not None and floating is not None and floating > 0:
        out.append(
            f"Spent {_clock(floating)} holding more than 1000 banked resources, "
            f"peaking at {int(peak)}. Resources in the bank are not doing "
            f"anything; that peak is roughly a Town Center plus change."
        )
    if player.float_by_age:
        age_name, worst = max(player.float_by_age.items(), key=lambda kv: kv[1])
        if worst > 700:
            out.append(
                f"Banked resources averaged {worst} during {age_name.title()} Age — "
                f"your least efficient phase of the game."
            )

    # --- Production -------------------------------------------------------
    gap_metric = m.get("max_production_gap")
    gap = _known(gap_metric)
    if gap is not None and gap > 60_000:
        out.append(
            f"Longest gap between villager queue commands was {_clock(gap)}. "
            f"At roughly 25s per villager that is about {int(gap) // 25000} "
            f"villagers of lost production, though a full queue can mask a real gap."
        )
    elif gap_metric is not None and gap_metric.availability is Availability.UNAVAILABLE:
        out.append(
            "Production metrics are unavailable for this replay version — the "
            "unit-queue commands could not be decoded."
        )

    # --- Tempo / activity -------------------------------------------------
    eapm = _known(m.get("eapm"))
    if eapm is not None:
        others = [
            other
            for o in analysis.players
            if o.player_number != player.player_number
            and (other := _known(o.metrics.get("eapm"))) is not None
        ]
        if others:
            best_other = max(others)
            if eapm - best_other <= -20:
                out.append(
                    f"Your effective APM was {int(eapm)} against {int(best_other)} — "
                    f"you issued substantially fewer meaningful commands than your opponent."
                )
            elif eapm - best_other >= 20:
                out.append(
                    f"Your effective APM was {int(eapm)} against {int(best_other)}, "
                    f"a clear activity advantage."
                )

    # --- Opening ----------------------------------------------------------
    if player.opening and player.opening != "unclassified":
        evidence = player.opening_evidence_ms
        if player.opening == "fast castle" and evidence is not None:
            out.append(
                f"No military production building before Castle Age at "
                f"{_clock(evidence)} — read as a fast castle."
            )
        elif evidence is not None:
            out.append(
                f"Opening read as {player.opening}: first military production "
                f"building placed at {_clock(evidence)}."
            )

    return out
