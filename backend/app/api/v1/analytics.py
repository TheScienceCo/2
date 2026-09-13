"""Advanced analytics endpoints: DVA, playstyle, radar."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.analysis.coachable import load_coachable_match
from app.services.analysis.decision_value import DVAAnalyzer
from app.services.analysis.playstyle import PlaystyleAnalyzer
from app.services.analysis.radar import RadarAnalyzer
from app.schemas.analytics import (
    DVAReportResponse,
    PlaystyleProfileResponse,
    RadarVisualizationResponse,
    MatchInsightsResponse,
)
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/matches/{match_id}/decisions", response_model=DVAReportResponse, tags=["analytics"])
async def analyze_decisions(
    match_id: str,
    db: Session = Depends(get_session),
):
    """Analyze decision value added for a match.
    
    Evaluates the quality of strategic decisions (age advancement, build order,
    unit composition, expansion) relative to peer baselines.
    
    Returns: DVAReport with decision evaluations and quality classification.
    """
    try:
        match = load_coachable_match(db, match_id)
        
        # Run DVA analysis
        # TODO: Wire to actual metrics and cohort comparison
        
        return {
            "decisions": [],
            "total_value_added": 0.0,
            "decision_quality": "neutral",
            "top_decisions": [],
            "bottom_decisions": [],
        }
    except Exception as e:
        log.error(f"Decision analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches/{match_id}/playstyle", response_model=PlaystyleProfileResponse, tags=["analytics"])
async def analyze_playstyle(
    match_id: str,
    db: Session = Depends(get_session),
):
    """Analyze player playstyle and awards.
    
    Classifies the player into one of 9 strategic archetypes (archer rush, castle
    power, etc.) and identifies achievements based on percentile performance.
    
    Returns: PlaystyleProfile with archetype, awards, and strengths/weaknesses.
    """
    try:
        match = load_coachable_match(db, match_id)
        
        # Run playstyle analysis
        analyzer = PlaystyleAnalyzer()
        # TODO: Wire to actual metrics and cohort context
        
        return {
            "primary_archetype": "balanced",
            "secondary_archetype": None,
            "archetype_confidence": 0.0,
            "awards": [],
            "strengths": [],
            "weaknesses": [],
        }
    except Exception as e:
        log.error(f"Playstyle analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches/{match_id}/radar", response_model=RadarVisualizationResponse, tags=["analytics"])
async def get_radar_visualization(
    match_id: str,
    db: Session = Depends(get_session),
):
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
        match = load_coachable_match(db, match_id)
        
        # Run radar analysis
        analyzer = RadarAnalyzer()
        # TODO: Load command stream and generate radar
        
        return {
            "match_duration_ms": match.duration_ms,
            "player_name": match.player_1_name,
            "samples": [],
            "sectors": [],
            "average_apm": 0.0,
            "peak_apm": 0.0,
            "focus_distribution": {"economy": 0.0, "military": 0.0, "scouting": 0.0, "strategy": 0.0},
            "attention_shifts": 0,
            "playstyle_signature": "Minimal activity",
        }
    except Exception as e:
        log.error(f"Radar visualization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches/{match_id}/insights", response_model=MatchInsightsResponse, tags=["analytics"])
async def get_full_analytics(
    match_id: str,
    db: Session = Depends(get_session),
):
    """Get complete analytics package: DVA, playstyle, and radar.
    
    Combines all advanced analytics into a single response for the coaching
    dashboard. This is the primary endpoint for the match analysis view.
    
    Returns: Complete analytics object with decisions, playstyle, and visualization data.
    """
    try:
        match = load_coachable_match(db, match_id)
        
        # Run all three analyses
        p1_decisions = await analyze_decisions(match_id, db)
        p1_playstyle = await analyze_playstyle(match_id, db)
        p1_radar = await get_radar_visualization(match_id, db)
        
        return {
            "match_id": match_id,
            "duration_ms": match.duration_ms,
            "p1_name": match.player_1_name,
            "p2_name": match.player_2_name,
            "p1_civ": match.player_1_civ,
            "p2_civ": match.player_2_civ,
            "winner": match.winner,
            "p1_decisions": p1_decisions,
            "p1_playstyle": p1_playstyle,
            "p1_radar": p1_radar,
            "p2_decisions": None,
            "p2_playstyle": None,
            "p2_radar": None,
        }
    except Exception as e:
        log.error(f"Full analytics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
