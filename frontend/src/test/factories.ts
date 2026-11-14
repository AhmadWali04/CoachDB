import type { Frame, MatchEvent, MatchState, TeamId, TeamStats } from "../api/types";
import type { Action } from "../types/action";
import type { CoachDecision } from "../types/coachAnalysis";

const EMPTY_STATS: TeamStats = {
  possession_pct: 0,
  shots: 0,
  shots_on_target: 0,
  turnovers: 0,
  pressing_successes: 0,
};

const TACTICS = {
  formation: "4-2-3-1" as const,
  mentality: "attacking" as const,
  pressing: "high" as const,
  defensive_line: "medium" as const,
  attack_focus: "left" as const,
  tempo: "fast" as const,
};

export function buildMatchState(overrides: Partial<MatchState> = {}): MatchState {
  return {
    match_id: "match_001",
    seed: 42,
    phase: "first_half",
    half: 1,
    step: 3,
    steps_per_half: 20,
    clock_minute: 12,
    score: { blue: 0, red: 0 },
    stats: { blue: EMPTY_STATS, red: EMPTY_STATS },
    teams: [
      {
        team_id: "blue",
        name: "Blue",
        coach_id: "coach_blue",
        coach_name: "Blue Coach",
        side: "top",
        tactics: TACTICS,
        players: [],
      },
      {
        team_id: "red",
        name: "Red",
        coach_id: "coach_red",
        coach_name: "Red Coach",
        side: "bottom",
        tactics: TACTICS,
        players: [],
      },
    ],
    state_version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

export function buildEvent(overrides: Partial<MatchEvent> = {}): MatchEvent {
  return {
    event_id: "event_1",
    match_id: "match_001",
    schema_version: 1,
    half: 1,
    step: 0,
    clock_minute: 10,
    team_id: "blue",
    type: "pass_sequence",
    player_ids: ["blue_9", "blue_10"],
    details: {},
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

export function buildCoachDecision(
  teamId: TeamId = "blue",
  overrides: Partial<CoachDecision> = {},
): CoachDecision {
  return {
    decision_id: `decision_${teamId}`,
    match_id: "match_001",
    team_id: teamId,
    coach_id: `coach_${teamId}`,
    analysis: {
      match_id: "match_001",
      team_id: teamId,
      state_version: 12,
      summary: "Dominant down the left in the first half.",
      own_strengths: [{ observation: "Left channel overloads", evidence: ["event_1"] }],
      own_weaknesses: [{ observation: "Slow to press centrally", evidence: ["event_2"] }],
      fatigue_concerns: [],
      uncertainties: [],
    },
    scouting: {
      match_id: "match_001",
      team_id: teamId,
      rival_team_id: teamId === "blue" ? "red" : "blue",
      state_version: 12,
      observed_tactics: { formation: "4-4-2", pressing: "low" },
      patterns: [],
      closest_style_profile_ids: [],
      likely_adjustments: [
        { change: "drop defensive line", confidence: 0.72, evidence: ["event_3"] },
      ],
      uncertainties: [],
    },
    plan: {
      match_id: "match_001",
      team_id: teamId,
      based_on_state_version: 12,
      plan: {
        formation: "4-2-3-1",
        mentality: "attacking",
        pressing: "high",
        defensive_line: "medium",
        attack_focus: "left",
        tempo: "fast",
      },
      opponent_prediction: {
        likely_change: "drop defensive line",
        confidence: 0.72,
        evidence: ["event_3"],
      },
      primary_objective: "Create more chances down the left.",
      expected_effects: [],
      risks: ["Higher stamina use"],
      success_indicators: ["Increase in left-channel entries"],
      rationale: "Left channel produced most entries.",
      voice_script: "We have found space down the left.",
    },
    used_fallback: false,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

export function buildAction(overrides: Partial<Action> = {}): Action {
  return {
    action_id: "action_1",
    match_id: "match_001",
    team_id: "blue",
    kind: "apply_tactical_plan",
    requested: TACTICS,
    expected_state_version: 12,
    status: "verified",
    simulator_ref: "sim_ref_1",
    observed_state_version: 13,
    fencing_token: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

export function buildFrame(overrides: Partial<Frame> = {}): Frame {
  return {
    match_id: "match_001",
    seq: 0,
    half: 1,
    step: 0,
    clock_minute: 10,
    phase: "first_half",
    state_version: 1,
    players: [
      { player_id: "blue_9", team_id: "blue", x: 40, y: 30 },
      { player_id: "blue_10", team_id: "blue", x: 60, y: 35 },
      { player_id: "red_9", team_id: "red", x: 45, y: 70 },
    ],
    ball: { x: 50, y: 50, owner_player_id: "blue_9" },
    events: [],
    ...overrides,
  };
}
