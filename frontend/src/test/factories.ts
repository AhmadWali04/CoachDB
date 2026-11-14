import type { Frame, MatchEvent, MatchState, TeamStats } from "../api/types";

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
