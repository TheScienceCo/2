"""Response schemas for analytics endpoints."""

from typing import Optional
from pydantic import BaseModel, Field


class DecisionEvaluationResponse(BaseModel):
    """Single decision evaluation."""
    
    timestamp_ms: int
    decision_type: str
    value_added: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str


class DVAReportResponse(BaseModel):
    """Decision Value Added analysis."""
    
    decisions: list[DecisionEvaluationResponse]
    total_value_added: float = Field(..., ge=-1.0, le=1.0)
    decision_quality: str = Field(..., pattern="^(excellent|good|neutral|below-average)$")
    top_decisions: list[DecisionEvaluationResponse]
    bottom_decisions: list[DecisionEvaluationResponse]


class PlaystyleAwardResponse(BaseModel):
    """Achievement award."""
    
    award: str
    category: str = Field(..., pattern="^(timing|economy|military|strategy)$")
    percentile: int = Field(..., ge=0, le=100)
    explanation: str
    rarity: str = Field(..., pattern="^(legendary|rare|uncommon|common)$")


class PlaystyleProfileResponse(BaseModel):
    """Player playstyle classification."""
    
    primary_archetype: str
    secondary_archetype: Optional[str] = None
    archetype_confidence: float = Field(..., ge=0.0, le=1.0)
    awards: list[PlaystyleAwardResponse] = []
    strengths: list[str] = []
    weaknesses: list[str] = []


class ActionSampleResponse(BaseModel):
    """Single action sample for radar."""
    
    timestamp_ms: int
    intensity: float = Field(..., ge=0.0, le=1.0)
    action_type: str
    action_count: int
    color_code: str


class RadarSectorResponse(BaseModel):
    """Aggregated 1-minute sector."""
    
    time_start_ms: int
    time_end_ms: int
    economy_intensity: float = Field(..., ge=0.0, le=1.0)
    military_intensity: float = Field(..., ge=0.0, le=1.0)
    scouting_intensity: float = Field(..., ge=0.0, le=1.0)
    strategy_intensity: float = Field(..., ge=0.0, le=1.0)
    dominant_action_type: str
    total_action_count: int


class RadarVisualizationResponse(BaseModel):
    """3D circular APM/attention radar."""
    
    match_duration_ms: int
    player_name: str
    samples: list[ActionSampleResponse]
    sectors: list[RadarSectorResponse]
    average_apm: float
    peak_apm: float
    focus_distribution: dict[str, float]
    attention_shifts: int
    playstyle_signature: str


class MatchInsightsResponse(BaseModel):
    """Complete analytics package for a match."""
    
    match_id: str
    duration_ms: int
    p1_name: str
    p2_name: str
    p1_civ: str
    p2_civ: str
    winner: Optional[int]
    
    # Player 1 analytics
    p1_decisions: Optional[DVAReportResponse] = None
    p1_playstyle: Optional[PlaystyleProfileResponse] = None
    p1_radar: Optional[RadarVisualizationResponse] = None
    
    # Player 2 analytics
    p2_decisions: Optional[DVAReportResponse] = None
    p2_playstyle: Optional[PlaystyleProfileResponse] = None
    p2_radar: Optional[RadarVisualizationResponse] = None
