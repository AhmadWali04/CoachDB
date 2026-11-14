// Mirrors backend/app/schemas/coach.py. Not generated: no endpoint returns
// these yet (Track A -- see CHECKLIST.md Requests), so there's nothing for
// openapi-typescript to pick up. Delete this file and import from
// `../api/types` once one does; keep the field names in sync until then.
import type { TacticalSettings, TeamId } from "../api/types";

export interface Observation {
  observation: string;
  evidence: string[];
}

export interface AnalystReport {
  match_id: string;
  team_id: TeamId;
  state_version: number;
  summary: string;
  own_strengths: Observation[];
  own_weaknesses: Observation[];
  fatigue_concerns: Observation[];
  uncertainties: string[];
}

export interface ObservedTactics {
  formation?: string | null;
  mentality?: string | null;
  pressing?: string | null;
  defensive_line?: string | null;
  attack_focus?: string | null;
  tempo?: string | null;
}

export interface LikelyAdjustment {
  change: string;
  confidence: number;
  evidence: string[];
}

export interface ScoutReport {
  match_id: string;
  team_id: TeamId;
  rival_team_id: TeamId;
  state_version: number;
  observed_tactics: ObservedTactics;
  patterns: Observation[];
  closest_style_profile_ids: string[];
  likely_adjustments: LikelyAdjustment[];
  uncertainties: string[];
}

export interface OpponentPrediction {
  likely_change: string;
  confidence: number;
  evidence: string[];
}

export interface TacticalPlan {
  match_id: string;
  team_id: TeamId;
  based_on_state_version: number;
  plan: TacticalSettings;
  opponent_prediction: OpponentPrediction;
  primary_objective: string;
  expected_effects: string[];
  risks: string[];
  success_indicators: string[];
  rationale: string;
  voice_script: string;
}

export interface CoachDecision {
  decision_id: string;
  match_id: string;
  team_id: TeamId;
  coach_id: string;
  analysis: AnalystReport;
  scouting: ScoutReport;
  plan: TacticalPlan;
  used_fallback: boolean;
  created_at: string;
}
