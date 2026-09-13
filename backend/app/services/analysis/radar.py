"""3D circular APM/attention radar visualization data.

Generates data for a 3D circular (polar) visualization of player attention
distribution: where actions were taken, their intensity, and temporal flow.

The radar shows:
- Circumference: time (match duration)
- Radial distance: action intensity (APM equivalent)
- Color: action type (military/economy/strategy/scouting)
- 3D rotation: reveals temporal patterns and attention shifts
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ActionSample:
    """A single action at a point in time."""
    
    timestamp_ms: int  # Position on circumference (angle = timestamp / duration * 360)
    intensity: float  # Radial distance (0.0-1.0, normalized APM or action density)
    action_type: str  # "economy" / "military" / "scouting" / "strategy"
    action_count: int  # How many commands in this time window
    color_code: str  # Hex color for visualization


@dataclass
class RadarSector:
    """Aggregated data for a wedge of the radar (e.g., 1-minute segment)."""
    
    time_start_ms: int
    time_end_ms: int
    economy_intensity: float  # 0.0-1.0
    military_intensity: float
    scouting_intensity: float
    strategy_intensity: float
    dominant_action_type: str
    total_action_count: int
    
    @property
    def total_intensity(self) -> float:
        """Sum of all action intensities."""
        return self.economy_intensity + self.military_intensity + \
               self.scouting_intensity + self.strategy_intensity


@dataclass
class RadarVisualization:
    """Complete 3D radar visualization data."""
    
    match_duration_ms: int
    player_name: str
    samples: list[ActionSample] = field(default_factory=list)
    sectors: list[RadarSector] = field(default_factory=list)
    
    # Summary statistics
    average_apm: float = 0.0
    peak_apm: float = 0.0
    focus_distribution: dict[str, float] = field(default_factory=dict)  # % by action type
    attention_shifts: int = 0  # How many times dominant action changed
    
    # Thematic interpretation
    playstyle_signature: str = ""  # e.g., "Early aggression, mid-game economy, late defense"


class RadarAnalyzer:
    """Generate 3D radar visualization from match commands."""
    
    # Action type classification
    ECONOMY_COMMANDS = {
        "create_villager", "build_farm", "build_mill", "build_lumber_camp",
        "build_mining_camp", "build_market", "build_tc", "build_dock",
        "research_wheelbarrow", "research_horse_collar",
    }
    
    MILITARY_COMMANDS = {
        "build_barracks", "build_archery_range", "build_stable", "build_siege_workshop",
        "create_unit", "move_unit", "attack", "garrison", "ungarrison",
    }
    
    SCOUTING_COMMANDS = {
        "scout_move", "explore", "patrol", "scout_order",
    }
    
    STRATEGY_COMMANDS = {
        "research_tech", "advance_age", "build_keep", "build_wall", "build_tower",
        "delete_building", "resign",
    }
    
    def analyze(
        self,
        commands: list[dict],
        match_duration_ms: int,
        player_name: str = "Player",
    ) -> RadarVisualization:
        """Generate radar visualization from command stream.
        
        Args:
            commands: List of commands with timestamp_ms and command_type
            match_duration_ms: Total match duration
            player_name: Player identifier
            
        Returns:
            RadarVisualization with samples and sectors
        """
        radar = RadarVisualization(
            match_duration_ms=match_duration_ms,
            player_name=player_name,
        )
        
        # Classify each command by action type
        classified = []
        for cmd in commands:
            action_type = self._classify_command(cmd.get("command_type", ""))
            classified.append({
                "timestamp_ms": cmd.get("timestamp_ms", 0),
                "action_type": action_type,
            })
        
        # Generate sectors (1-minute windows)
        sector_duration_ms = 60_000  # 1 minute
        n_sectors = (match_duration_ms + sector_duration_ms - 1) // sector_duration_ms
        
        for i in range(n_sectors):
            sector_start = i * sector_duration_ms
            sector_end = min((i + 1) * sector_duration_ms, match_duration_ms)
            
            # Count actions in this sector by type
            sector_commands = [
                c for c in classified
                if sector_start <= c["timestamp_ms"] < sector_end
            ]
            
            action_counts = {
                "economy": sum(1 for c in sector_commands if c["action_type"] == "economy"),
                "military": sum(1 for c in sector_commands if c["action_type"] == "military"),
                "scouting": sum(1 for c in sector_commands if c["action_type"] == "scouting"),
                "strategy": sum(1 for c in sector_commands if c["action_type"] == "strategy"),
            }
            
            total_actions = sum(action_counts.values())
            
            # Normalize to 0.0-1.0 (assume max 100 actions per minute = APM equivalent)
            max_actions_per_minute = 100
            economy_intensity = min(1.0, action_counts["economy"] / max_actions_per_minute)
            military_intensity = min(1.0, action_counts["military"] / max_actions_per_minute)
            scouting_intensity = min(1.0, action_counts["scouting"] / max_actions_per_minute)
            strategy_intensity = min(1.0, action_counts["strategy"] / max_actions_per_minute)
            
            dominant_action = max(
                action_counts.items(), key=lambda x: x[1]
            )[0] if total_actions > 0 else "strategy"
            
            sector = RadarSector(
                time_start_ms=sector_start,
                time_end_ms=sector_end,
                economy_intensity=float(economy_intensity),
                military_intensity=float(military_intensity),
                scouting_intensity=float(scouting_intensity),
                strategy_intensity=float(strategy_intensity),
                dominant_action_type=dominant_action,
                total_action_count=total_actions,
            )
            
            radar.sectors.append(sector)
        
        # Generate high-resolution samples for smooth visualization
        sample_interval_ms = 5_000  # Sample every 5 seconds
        for t in range(0, match_duration_ms, sample_interval_ms):
            window_start = max(0, t - sample_interval_ms // 2)
            window_end = min(match_duration_ms, t + sample_interval_ms // 2)
            
            window_commands = [
                c for c in classified
                if window_start <= c["timestamp_ms"] < window_end
            ]
            
            if not window_commands:
                intensity = 0.0
                action_type = "strategy"
                action_count = 0
            else:
                action_type = max(
                    set(c["action_type"] for c in window_commands),
                    key=lambda a: sum(1 for c in window_commands if c["action_type"] == a)
                )
                action_count = len(window_commands)
                intensity = min(1.0, action_count / 20.0)  # Normalize
            
            sample = ActionSample(
                timestamp_ms=t,
                intensity=intensity,
                action_type=action_type,
                action_count=action_count,
                color_code=self._action_color(action_type),
            )
            radar.samples.append(sample)
        
        # Calculate summary statistics
        radar.average_apm = (
            sum(s.total_action_count for s in radar.sectors) / max(1, n_sectors)
        )
        radar.peak_apm = max((s.total_action_count for s in radar.sectors), default=0.0)
        
        # Attention shift detection
        prev_dominant = None
        attention_shifts = 0
        for sector in radar.sectors:
            if prev_dominant and sector.dominant_action_type != prev_dominant:
                attention_shifts += 1
            prev_dominant = sector.dominant_action_type
        radar.attention_shifts = attention_shifts
        
        # Focus distribution
        total_actions = sum(s.total_action_count for s in radar.sectors)
        if total_actions > 0:
            radar.focus_distribution = {
                "economy": sum(s.economy_intensity for s in radar.sectors) / len(radar.sectors),
                "military": sum(s.military_intensity for s in radar.sectors) / len(radar.sectors),
                "scouting": sum(s.scouting_intensity for s in radar.sectors) / len(radar.sectors),
                "strategy": sum(s.strategy_intensity for s in radar.sectors) / len(radar.sectors),
            }
        
        # Playstyle signature
        radar.playstyle_signature = self._generate_signature(radar.sectors)
        
        return radar
    
    def _classify_command(self, command_type: str) -> str:
        """Classify a command by action type."""
        cmd_lower = command_type.lower()
        
        if any(eco in cmd_lower for eco in self.ECONOMY_COMMANDS):
            return "economy"
        elif any(mil in cmd_lower for mil in self.MILITARY_COMMANDS):
            return "military"
        elif any(sco in cmd_lower for sco in self.SCOUTING_COMMANDS):
            return "scouting"
        else:
            return "strategy"
    
    def _action_color(self, action_type: str) -> str:
        """Return hex color for action type."""
        colors = {
            "economy": "#3b82f6",  # Blue
            "military": "#ef4444",  # Red
            "scouting": "#10b981",  # Green
            "strategy": "#f59e0b",  # Amber
        }
        return colors.get(action_type, "#6b7280")  # Default gray
    
    def _generate_signature(self, sectors: list[RadarSector]) -> str:
        """Generate human-readable playstyle signature from sector patterns."""
        if not sectors:
            return "Minimal activity"
        
        early = sectors[:len(sectors)//3]
        mid = sectors[len(sectors)//3:2*len(sectors)//3]
        late = sectors[2*len(sectors)//3:]
        
        def get_dominant(phase_sectors: list[RadarSector]) -> str:
            if not phase_sectors:
                return "idle"
            action_types = [s.dominant_action_type for s in phase_sectors]
            return max(set(action_types), key=action_types.count)
        
        early_style = get_dominant(early)
        mid_style = get_dominant(mid)
        late_style = get_dominant(late)
        
        return f"Early {early_style}, mid-game {mid_style}, late {late_style}"
