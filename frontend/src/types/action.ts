// Mirrors backend/app/schemas/action.py. No endpoint returns the action
// ledger yet (Track A -- see CHECKLIST.md Requests); delete this and import
// from `../api/types` once one does.
import type { TacticalSettings, TeamId } from "../api/types";

export type ActionStatus =
  | "proposed"
  | "submitted"
  | "applied"
  | "verified"
  | "rejected"
  | "failed"
  | "unknown";

export interface Action {
  action_id: string;
  match_id: string;
  team_id: TeamId;
  kind: "apply_tactical_plan";
  requested: TacticalSettings;
  expected_state_version: number;
  status: ActionStatus;
  simulator_ref: string | null;
  observed_state_version: number | null;
  fencing_token: number;
  created_at: string;
  updated_at: string;
}
