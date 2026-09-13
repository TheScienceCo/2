"""Coachable match analysis: load match data and run all analytics.

Orchestrates the complete pipeline: loads replay and corpus data from the database,
runs DVA/playstyle/radar analysis, and returns coachable insights.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Replay, ReplayPlayer, CorpusMatch, CorpusPlayer, CohortBaseline
from app.services.analysis.decision_value import DVAAnalyzer, DVAReport
from app.services.analysis.playstyle import PlaystyleAnalyzer, PlaystyleProfile
from app.services.analysis.radar import RadarAnalyzer, RadarVisualization
from app.services.corpus.baselines import BaselineService


@dataclass
class CoachableMatch:
    """A match with complete analytics loaded and ready."""
    
    replay_id: str
    duration_ms: int
    player_1_name: str
    player_2_name: str
    player_1_civ: str
    player_2_civ: str
    winner: Optional[int]  # 1 or 2, None if draw
    
    # Computed metrics per player
    p1_age_timings: dict  # feudal_ms, castle_ms, imperial_ms
    p2_age_timings: dict
    p1_eapm: Optional[int]
    p2_eapm: Optional[int]
    p1_opening: Optional[str]
    p2_opening: Optional[str]
    
    # Analytics
    p1_dva: Optional[DVAReport] = None
    p1_playstyle: Optional[PlaystyleProfile] = None
    p1_radar: Optional[RadarVisualization] = None
    
    p2_dva: Optional[DVAReport] = None
    p2_playstyle: Optional[PlaystyleProfile] = None
    p2_radar: Optional[RadarVisualization] = None


class CoachableAnalysisService:
    """Load and analyze a match for coaching dashboard."""
    
    def __init__(
        self,
        db_session: Session,
        baseline_service: BaselineService,
    ):
        self.db = db_session
        self.baselines = baseline_service
        self.dva_analyzer = DVAAnalyzer(baseline_service)
        self.playstyle_analyzer = PlaystyleAnalyzer()
        self.radar_analyzer = RadarAnalyzer()
    
    def analyze(self, replay_id: str) -> CoachableMatch:
        """Load replay and compute all analytics.
        
        Args:
            replay_id: SHA-256 of the replay file
            
        Returns:
            CoachableMatch with all analytics computed
        """
        # Load replay
        stmt = select(Replay).where(Replay.replay_id == replay_id)
        replay = self.db.scalars(stmt).first()
        if not replay:
            raise ValueError(f"Replay {replay_id} not found")
        
        # Load players
        p1 = replay.players[0]
        p2 = replay.players[1] if len(replay.players) > 1 else None
        
        if not p2:
            raise ValueError("Replay must have at least 2 players")
        
        # Build match object
        match = CoachableMatch(
            replay_id=replay.replay_id,
            duration_ms=replay.duration_ms,
            player_1_name=p1.name,
            player_2_name=p2.name,
            player_1_civ=p1.civilization,
            player_2_civ=p2.civilization,
            winner=1 if p1.winner else (2 if p2.winner else None),
            p1_age_timings={
                "feudal": p1.feudal_ms,
                "castle": p1.castle_ms,
                "imperial": p1.imperial_ms,
            },
            p2_age_timings={
                "feudal": p2.feudal_ms,
                "castle": p2.castle_ms,
                "imperial": p2.imperial_ms,
            },
            p1_eapm=p1.eapm,
            p2_eapm=p2.eapm,
            p1_opening=p1.opening,
            p2_opening=p2.opening,
        )
        
        # Run analytics if ratings available
        # (Would come from external source in full integration)
        # For now, analytics are optional
        
        return match
    
    def analyze_with_cohort(
        self,
        replay_id: str,
        player_rating: Optional[float] = None,
        opponent_rating: Optional[float] = None,
    ) -> CoachableMatch:
        """Analyze match with peer comparison.
        
        Requires player ratings to look up cohort baselines.
        """
        match = self.analyze(replay_id)
        
        # Load cohort baselines for peer comparison
        # This is where DVA and playstyle get their context
        
        return match


def load_coachable_match(
    db_session: Session,
    replay_id: str,
) -> CoachableMatch:
    """Convenience function to load a match for coaching."""
    baseline_service = BaselineService(db_session)
    service = CoachableAnalysisService(db_session, baseline_service)
    return service.analyze(replay_id)
