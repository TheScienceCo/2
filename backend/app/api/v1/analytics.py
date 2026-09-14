"""Advanced analytics endpoints: DVA, playstyle, radar."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Replay, CohortBaseline
from app.db.session import get_db
from app.services.analysis.coachable import load_coachable_match
from app.services.analysis.compute import MetricsComputeService, PlayerMetrics
from app.services.analysis.decision_value import DVAAnalyzer, DecisionEvaluation
from app.services.analysis.playstyle import PlaystyleAnalyzer
from app.services.analysis.radar import RadarAnalyzer
from app.services.corpus.baselines import BaselineService, cohort_key
from app.schemas.analytics import (
    DVAReportResponse,
    PlaystyleProfileResponse,
    RadarVisualizationResponse,
    MatchInsightsResponse,
    DecisionEvaluationResponse,
    PlaystyleAwardResponse,
    ActionSampleResponse,
    RadarSectorResponse,
)
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


def _load_replay(db: Session, match_id: str) -> "Replay":
    """Load a replay by ID, raising HTTPException if not found."""
    stmt = select(Replay).where(Replay.replay_id == match_id)
    replay = db.scalars(stmt).first()
    if not replay:
        raise HTTPException(status_code=404, detail=f"Replay {match_id} not found")
    return replay


def _rank_decisions(
    decisions: list[DecisionEvaluationResponse],
) -> tuple[list[DecisionEvaluationResponse], list[DecisionEvaluationResponse]]:
    """Split decisions into what helped and what hurt, best and worst first.

    Partitioning on the sign rather than taking head and tail of one list keeps
    the two disjoint: a decision must never be reported as both a strength and
    something to work on. Ties are broken by confidence, so a well-evidenced
    decision outranks a marginal one of the same value.
    """
    helped = sorted(
        (d for d in decisions if d.value_added > 0),
        key=lambda d: (d.value_added * d.confidence),
        reverse=True,
    )
    hurt = sorted(
        (d for d in decisions if d.value_added < 0),
        key=lambda d: (d.value_added * d.confidence),
    )
    return helped[:3], hurt[:3]


def _metrics_to_dict(metrics: "PlayerMetrics") -> dict:
    """Convert PlayerMetrics dataclass to dict for analyzer methods."""
    return {
        "feudal_ms": metrics.feudal_ms,
        "castle_ms": metrics.castle_ms,
        "imperial_ms": metrics.imperial_ms,
        "eapm": metrics.eapm,
        "apm": metrics.apm,
        "opening": metrics.opening,
        "military_spend_pct": metrics.military_spend_pct,
        "military_unit_diversity": metrics.military_unit_diversity,
        "army_size": metrics.army_size,
        "resource_float_avg": metrics.resource_float_avg,
        "resource_float_peak": metrics.resource_float_peak,
        "villager_uptime": metrics.villager_uptime,
        "tc_idle_percentage": metrics.tc_idle_percentage,
        "expansion_count": metrics.expansion_count,
        "expansion_timing_ms": metrics.expansion_timing_ms,
        "winner": metrics.winner,
    }


def _build_cohort_context(
    db: Session,
    player_metrics: "PlayerMetrics",
    elo_band: int | None = None,
    civ: str | None = None,
    map_name: str | None = None,
) -> dict:
    """Load cohort baselines for a player."""
    # Try to find baselines in order of specificity
    baselines = {}

    # All standard metrics we care about
    metric_names = [
        "feudal_ms",
        "castle_ms",
        "imperial_ms",
        "eapm",
        "apm",
        "resource_float_avg",
        "tc_idle_percentage",
        "military_spend_pct",
        "expansion_count",
    ]

    # Build a fallback search pattern: try with map, then without
    for metric in metric_names:
        # Try: (elo_band, civ, map)
        if elo_band and civ and map_name:
            dims_key = cohort_key({"elo_band": elo_band, "civ": civ, "map_name": map_name})
            stmt = select(CohortBaseline).where(
                CohortBaseline.metric == metric,
                CohortBaseline.cohort_key == dims_key,
            )
            baseline = db.scalars(stmt).first()
            if baseline and baseline.n >= 30:
                baselines[metric] = {
                    "mean": baseline.mean,
                    "std": baseline.std,
                    "p10": baseline.p10,
                    "p25": baseline.p25,
                    "p50": baseline.p50,
                    "p75": baseline.p75,
                    "p90": baseline.p90,
                    "n": baseline.n,
                    "source": baseline.source,
                }
                continue

        # Try: (elo_band, civ)
        if elo_band and civ:
            dims_key = cohort_key({"elo_band": elo_band, "civ": civ})
            stmt = select(CohortBaseline).where(
                CohortBaseline.metric == metric,
                CohortBaseline.cohort_key == dims_key,
            )
            baseline = db.scalars(stmt).first()
            if baseline and baseline.n >= 30:
                baselines[metric] = {
                    "mean": baseline.mean,
                    "std": baseline.std,
                    "p10": baseline.p10,
                    "p25": baseline.p25,
                    "p50": baseline.p50,
                    "p75": baseline.p75,
                    "p90": baseline.p90,
                    "n": baseline.n,
                    "source": baseline.source,
                }
                continue

        # Try: (elo_band)
        if elo_band:
            dims_key = cohort_key({"elo_band": elo_band})
            stmt = select(CohortBaseline).where(
                CohortBaseline.metric == metric,
                CohortBaseline.cohort_key == dims_key,
            )
            baseline = db.scalars(stmt).first()
            if baseline and baseline.n >= 30:
                baselines[metric] = {
                    "mean": baseline.mean,
                    "std": baseline.std,
                    "p10": baseline.p10,
                    "p25": baseline.p25,
                    "p50": baseline.p50,
                    "p75": baseline.p75,
                    "p90": baseline.p90,
                    "n": baseline.n,
                    "source": baseline.source,
                }

    return {
        "baselines": baselines,
        "elo_band": elo_band,
        "civ": civ,
        "map_name": map_name,
    }


@router.post("/matches/{match_id}/decisions", response_model=DVAReportResponse, tags=["analytics"])
async def analyze_decisions(
    match_id: str,
    db: Session = Depends(get_db),
) -> DVAReportResponse:
    """Analyze decision value added for a match.

    Evaluates the quality of strategic decisions (age advancement, build order,
    unit composition, expansion) relative to peer baselines.

    Returns: DVAReport with decision evaluations and quality classification.
    """
    try:
        replay = _load_replay(db, match_id)
        if not replay.players or len(replay.players) < 2:
            raise ValueError("Replay must have at least 2 players")

        # Compute metrics for both players
        metrics_service = MetricsComputeService()
        all_metrics = metrics_service.compute_from_replay(replay)

        p1_metrics = all_metrics[1]
        p2_metrics = all_metrics[2] if 2 in all_metrics else all_metrics.get(1)

        # Load cohort context for player 1
        # For now, use generic elo_band 1400 as placeholder
        cohort = _build_cohort_context(
            db,
            p1_metrics,
            elo_band=1400,
            civ=p1_metrics.civilization,
            map_name=replay.map_name,
        )

        # Run DVA analysis
        baseline_service = BaselineService(db)
        analyzer = DVAAnalyzer(baseline_service)

        # Build cohort context dict with baseline info
        cohort_context = cohort.copy()
        for metric_name, baseline_data in cohort["baselines"].items():
            if baseline_data:
                cohort_context[f"{metric_name}_baseline"] = baseline_data.get("mean")
                cohort_context[f"{metric_name}_std"] = baseline_data.get("std")
        cohort_context["cohort_size"] = sum(
            b.get("n", 0) for b in cohort["baselines"].values() if b
        )

        report = analyzer.analyze(
            metrics=_metrics_to_dict(p1_metrics),
            cohort_context=cohort_context,
            opponent_metrics=_metrics_to_dict(p2_metrics),
        )

        # Convert to response format
        decisions_response = [
            DecisionEvaluationResponse(
                timestamp_ms=d.timestamp_ms,
                decision_type=d.decision_type,
                value_added=d.value_added,
                confidence=d.confidence,
                explanation=d.explanation,
            )
            for d in report.decisions
        ]

        top, bottom = _rank_decisions(decisions_response)

        return DVAReportResponse(
            decisions=decisions_response,
            total_value_added=report.total_value_added,
            decision_quality=report.decision_quality,
            top_decisions=top,
            bottom_decisions=bottom,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Decision analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches/{match_id}/playstyle", response_model=PlaystyleProfileResponse, tags=["analytics"])
async def analyze_playstyle(
    match_id: str,
    db: Session = Depends(get_db),
) -> PlaystyleProfileResponse:
    """Analyze player playstyle and awards.

    Classifies the player into one of 9 strategic archetypes (archer rush, castle
    power, etc.) and identifies achievements based on percentile performance.

    Returns: PlaystyleProfile with archetype, awards, and strengths/weaknesses.
    """
    try:
        replay = _load_replay(db, match_id)
        if not replay.players:
            raise ValueError("Replay must have at least 1 player")

        p1 = replay.players[0]

        # Compute metrics for player 1
        metrics_service = MetricsComputeService()
        all_metrics = metrics_service.compute_from_replay(replay)
        p1_metrics = all_metrics[1]

        # Load cohort context for player 1
        cohort = _build_cohort_context(
            db,
            p1_metrics,
            elo_band=1400,
            civ=p1_metrics.civilization,
            map_name=replay.map_name,
        )

        # Run playstyle analysis
        analyzer = PlaystyleAnalyzer()

        # Build cohort context dict with baseline info
        cohort_context = cohort.copy()
        for metric_name, baseline_data in cohort["baselines"].items():
            if baseline_data:
                cohort_context[f"{metric_name}_baseline"] = baseline_data.get("mean")
                cohort_context[f"{metric_name}_std"] = baseline_data.get("std")
                # Add percentile key for each metric
                cohort_context[f"{metric_name}_percentile"] = 50  # Default

        profile = analyzer.analyze(
            metrics=_metrics_to_dict(p1_metrics),
            cohort_context=cohort_context,
        )

        # Convert awards to response format
        awards_response = [
            PlaystyleAwardResponse(
                award=award.award,
                category=award.category,
                percentile=award.percentile,
                explanation=award.explanation,
                rarity=award.rarity,
            )
            for award in profile.awards
        ]

        return PlaystyleProfileResponse(
            primary_archetype=profile.primary_archetype.value,
            secondary_archetype=profile.secondary_archetype.value if profile.secondary_archetype else None,
            archetype_confidence=profile.archetype_confidence,
            awards=awards_response,
            strengths=profile.strengths,
            weaknesses=profile.weaknesses,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Playstyle analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches/{match_id}/radar", response_model=RadarVisualizationResponse, tags=["analytics"])
async def get_radar_visualization(
    match_id: str,
    db: Session = Depends(get_db),
) -> RadarVisualizationResponse:
    """Get 3D circular APM/attention radar visualization data.

    Returns detailed sector and sample data for rendering a 3D polar plot
    showing action distribution across the match.

    Visualization structure:
    - Circumference: time (match duration)
    - Radial distance: action intensity (APM-equivalent)
    - Color: action type (economy/military/scouting/strategy)
    - 3D rotation: temporal flow patterns

    Returns: RadarVisualization with sectors, samples, and focus distribution.
    """
    try:
        replay = _load_replay(db, match_id)
        if not replay.players:
            raise ValueError("Replay must have at least 1 player")

        p1 = replay.players[0]

        # Compute metrics
        metrics_service = MetricsComputeService()
        all_metrics = metrics_service.compute_from_replay(replay)
        p1_metrics = all_metrics[1]

        # Generate radar visualization
        analyzer = RadarAnalyzer()

        # If we have command data in analysis, use it; otherwise generate from metrics
        commands = []
        if replay.analysis and "commands" in replay.analysis.get("players", {}).get("player_1", {}):
            commands = replay.analysis["players"]["player_1"]["commands"]

        viz = analyzer.analyze(
            commands=commands,
            match_duration_ms=replay.duration_ms,
            player_name=p1.name,
        )

        # Convert to response format
        samples_response = [
            ActionSampleResponse(
                timestamp_ms=sample.timestamp_ms,
                intensity=sample.intensity,
                action_type=sample.action_type,
                action_count=sample.action_count,
                color_code=sample.color_code,
            )
            for sample in viz.samples
        ]

        sectors_response = [
            RadarSectorResponse(
                time_start_ms=sector.time_start_ms,
                time_end_ms=sector.time_end_ms,
                economy_intensity=sector.economy_intensity,
                military_intensity=sector.military_intensity,
                scouting_intensity=sector.scouting_intensity,
                strategy_intensity=sector.strategy_intensity,
                dominant_action_type=sector.dominant_action_type,
                total_action_count=sector.total_action_count,
            )
            for sector in viz.sectors
        ]

        return RadarVisualizationResponse(
            match_duration_ms=viz.match_duration_ms,
            player_name=viz.player_name,
            samples=samples_response,
            sectors=sectors_response,
            average_apm=viz.average_apm,
            peak_apm=viz.peak_apm,
            focus_distribution=viz.focus_distribution,
            attention_shifts=viz.attention_shifts,
            playstyle_signature=viz.playstyle_signature,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Radar visualization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _analyze_player(
    replay: "Replay",
    player_num: int,
    db: Session,
) -> tuple[DVAReportResponse | None, PlaystyleProfileResponse | None, RadarVisualizationResponse | None]:
    """Analyze one player from a loaded replay."""
    try:
        if player_num < 1 or player_num > len(replay.players):
            return None, None, None

        player = replay.players[player_num - 1]

        # Compute metrics
        metrics_service = MetricsComputeService()
        all_metrics = metrics_service.compute_from_replay(replay)
        player_metrics = all_metrics.get(player_num)

        if not player_metrics:
            return None, None, None

        # Get opponent metrics
        opponent_num = 3 - player_num  # 1->2, 2->1
        opponent_metrics = all_metrics.get(opponent_num)

        # Load cohort context
        cohort = _build_cohort_context(
            db,
            player_metrics,
            elo_band=1400,
            civ=player_metrics.civilization,
            map_name=replay.map_name,
        )

        # DVA Analysis
        baseline_service = BaselineService(db)
        analyzer = DVAAnalyzer(baseline_service)

        cohort_context = cohort.copy()
        for metric_name, baseline_data in cohort["baselines"].items():
            if baseline_data:
                cohort_context[f"{metric_name}_baseline"] = baseline_data.get("mean")
                cohort_context[f"{metric_name}_std"] = baseline_data.get("std")
        cohort_context["cohort_size"] = sum(
            b.get("n", 0) for b in cohort["baselines"].values() if b
        )

        report = analyzer.analyze(
            metrics=_metrics_to_dict(player_metrics),
            cohort_context=cohort_context,
            opponent_metrics=_metrics_to_dict(opponent_metrics) if opponent_metrics else {},
        )

        decisions_response = [
            DecisionEvaluationResponse(
                timestamp_ms=d.timestamp_ms,
                decision_type=d.decision_type,
                value_added=d.value_added,
                confidence=d.confidence,
                explanation=d.explanation,
            )
            for d in report.decisions
        ]

        top, bottom = _rank_decisions(decisions_response)

        dva_response = DVAReportResponse(
            decisions=decisions_response,
            total_value_added=report.total_value_added,
            decision_quality=report.decision_quality,
            top_decisions=top,
            bottom_decisions=bottom,
        )

        # Playstyle Analysis
        playstyle_analyzer = PlaystyleAnalyzer()

        cohort_context_style = cohort.copy()
        for metric_name, baseline_data in cohort["baselines"].items():
            if baseline_data:
                cohort_context_style[f"{metric_name}_baseline"] = baseline_data.get("mean")
                cohort_context_style[f"{metric_name}_std"] = baseline_data.get("std")
                cohort_context_style[f"{metric_name}_percentile"] = 50

        profile = playstyle_analyzer.analyze(
            metrics=_metrics_to_dict(player_metrics),
            cohort_context=cohort_context_style,
        )

        awards_response = [
            PlaystyleAwardResponse(
                award=award.award,
                category=award.category,
                percentile=award.percentile,
                explanation=award.explanation,
                rarity=award.rarity,
            )
            for award in profile.awards
        ]

        playstyle_response = PlaystyleProfileResponse(
            primary_archetype=profile.primary_archetype.value,
            secondary_archetype=profile.secondary_archetype.value if profile.secondary_archetype else None,
            archetype_confidence=profile.archetype_confidence,
            awards=awards_response,
            strengths=profile.strengths,
            weaknesses=profile.weaknesses,
        )

        # Radar Analysis
        radar_analyzer = RadarAnalyzer()
        commands = []
        if replay.analysis and "commands" in replay.analysis.get("players", {}).get(f"player_{player_num}", {}):
            commands = replay.analysis["players"][f"player_{player_num}"]["commands"]

        viz = radar_analyzer.analyze(
            commands=commands,
            match_duration_ms=replay.duration_ms,
            player_name=player.name,
        )

        samples_response = [
            ActionSampleResponse(
                timestamp_ms=sample.timestamp_ms,
                intensity=sample.intensity,
                action_type=sample.action_type,
                action_count=sample.action_count,
                color_code=sample.color_code,
            )
            for sample in viz.samples
        ]

        sectors_response = [
            RadarSectorResponse(
                time_start_ms=sector.time_start_ms,
                time_end_ms=sector.time_end_ms,
                economy_intensity=sector.economy_intensity,
                military_intensity=sector.military_intensity,
                scouting_intensity=sector.scouting_intensity,
                strategy_intensity=sector.strategy_intensity,
                dominant_action_type=sector.dominant_action_type,
                total_action_count=sector.total_action_count,
            )
            for sector in viz.sectors
        ]

        radar_response = RadarVisualizationResponse(
            match_duration_ms=viz.match_duration_ms,
            player_name=viz.player_name,
            samples=samples_response,
            sectors=sectors_response,
            average_apm=viz.average_apm,
            peak_apm=viz.peak_apm,
            focus_distribution=viz.focus_distribution,
            attention_shifts=viz.attention_shifts,
            playstyle_signature=viz.playstyle_signature,
        )

        return dva_response, playstyle_response, radar_response

    except Exception as e:
        log.warning(f"Analysis for player {player_num} failed: {e}")
        return None, None, None


@router.get("/matches/{match_id}/insights", response_model=MatchInsightsResponse, tags=["analytics"])
async def get_full_analytics(
    match_id: str,
    db: Session = Depends(get_db),
) -> MatchInsightsResponse:
    """Get complete analytics package: DVA, playstyle, and radar.

    Combines all advanced analytics into a single response for the coaching
    dashboard. This is the primary endpoint for the match analysis view.

    Returns: Complete analytics object with decisions, playstyle, and visualization data.
    """
    try:
        replay = _load_replay(db, match_id)
        if not replay.players or len(replay.players) < 2:
            raise ValueError("Replay must have at least 2 players")

        # Analyze both players
        p1_decisions, p1_playstyle, p1_radar = await _analyze_player(replay, 1, db)
        p2_decisions, p2_playstyle, p2_radar = await _analyze_player(replay, 2, db)

        # Determine winner
        p1, p2 = replay.players[0], replay.players[1]
        winner = None
        if p1.winner:
            winner = 1
        elif p2.winner:
            winner = 2

        return MatchInsightsResponse(
            match_id=match_id,
            duration_ms=replay.duration_ms,
            p1_name=p1.name,
            p2_name=p2.name,
            p1_civ=p1.civilization,
            p2_civ=p2.civilization,
            winner=winner,
            p1_decisions=p1_decisions,
            p1_playstyle=p1_playstyle,
            p1_radar=p1_radar,
            p2_decisions=p2_decisions,
            p2_playstyle=p2_playstyle,
            p2_radar=p2_radar,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Full analytics failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
