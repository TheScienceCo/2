/** Mirrors `app/schemas/aoe2.py`. */

/** How a number was arrived at. `unavailable` always carries a null value. */
export type Availability = "observed" | "reconstructed" | "inferred" | "unavailable";

export interface Metric {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  availability: Availability;
  note: string | null;
}

export interface BuildOrderEntry {
  timestamp_ms: number;
  building: string;
  x: number | null;
  y: number | null;
}

export interface ResourcePoint {
  timestamp_ms: number;
  /** Food + wood + gold + stone combined; the per-type split is not in a replay. */
  banked: number;
  objects: number;
}

export interface PlayerAnalysis {
  player_number: number;
  name: string;
  civilization: string;
  winner: boolean | null;
  opening: string | null;
  age_timings_ms: Record<string, number>;
  float_by_age: Record<string, number>;
  metrics: Record<string, Metric>;
  build_order: BuildOrderEntry[];
  resource_curve: ResourcePoint[];
  insights: string[];
}

export interface MatchAnalysis {
  replay_id: string;
  filename: string;
  map_name: string | null;
  duration_ms: number;
  version: string | null;
  players: PlayerAnalysis[];
  warnings: string[];
}

/* -------------------------------------------------------------------------
   Advanced analytics. Mirrors `app/schemas/analytics.py`.
   ------------------------------------------------------------------------- */

export interface DecisionEvaluationResponse {
  timestamp_ms: number;
  decision_type: string;
  value_added: number;
  confidence: number;
  explanation: string;
}

export interface DVAReportResponse {
  decisions: DecisionEvaluationResponse[];
  total_value_added: number;
  decision_quality: "excellent" | "good" | "neutral" | "below-average";
  top_decisions: DecisionEvaluationResponse[];
  bottom_decisions: DecisionEvaluationResponse[];
}

export interface PlaystyleAwardResponse {
  award: string;
  category: "timing" | "economy" | "military" | "strategy";
  percentile: number;
  explanation: string;
  rarity: "legendary" | "rare" | "uncommon" | "common";
}

export interface PlaystyleProfileResponse {
  primary_archetype: string;
  secondary_archetype: string | null;
  archetype_confidence: number;
  awards: PlaystyleAwardResponse[];
  strengths: string[];
  weaknesses: string[];
}

export interface ActionSampleResponse {
  timestamp_ms: number;
  intensity: number;
  action_type: string;
  action_count: number;
  color_code: string;
}

export interface RadarSectorResponse {
  time_start_ms: number;
  time_end_ms: number;
  economy_intensity: number;
  military_intensity: number;
  scouting_intensity: number;
  strategy_intensity: number;
  dominant_action_type: string;
  total_action_count: number;
}

export interface RadarVisualizationResponse {
  match_duration_ms: number;
  player_name: string;
  samples: ActionSampleResponse[];
  sectors: RadarSectorResponse[];
  average_apm: number;
  peak_apm: number;
  focus_distribution: Record<string, number>;
  attention_shifts: number;
  playstyle_signature: string;
}

export interface MatchInsightsResponse {
  match_id: string;
  duration_ms: number;
  p1_name: string;
  p2_name: string;
  p1_civ: string;
  p2_civ: string;
  winner: number | null;
  p1_decisions: DVAReportResponse | null;
  p1_playstyle: PlaystyleProfileResponse | null;
  p1_radar: RadarVisualizationResponse | null;
  p2_decisions: DVAReportResponse | null;
  p2_playstyle: PlaystyleProfileResponse | null;
  p2_radar: RadarVisualizationResponse | null;
}
