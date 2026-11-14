// Mirrors the evaluation harness's core metrics (PRD §12). No
// `GET /evaluations/{batch_id}` exists yet (Track A -- see CHECKLIST.md
// Requests); delete this and import from `../api/types` once one does.
import type { TeamId } from "../api/types";

export interface MatchResult {
  seed: number;
  sides_swapped: boolean;
  score: Record<TeamId, number>;
}

export interface CoachMetrics {
  prediction_accuracy: number;
  decision_validity: number;
  execution_reliability: number;
  recovery_correctness: number;
  evidence_grounding: number;
  avg_decision_latency_ms: number;
}

export interface EvaluationBatch {
  batch_id: string;
  status?: "running" | "done" | "failed";
  results: MatchResult[];
  metrics: Record<TeamId, CoachMetrics>;
}
