import type { Action } from "../types/action";
import type { CoachDecision } from "../types/coachAnalysis";
import type { EvaluationBatch } from "../types/evaluation";
import type {
  Briefing,
  CreateMatchRequest,
  FramesPage,
  InjectCrashRequest,
  InjectCrashResponse,
  MatchEvent,
  MatchState,
  TeamId,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, String(body.detail ?? res.statusText));
  }
  return res.json() as Promise<T>;
}

export const api = {
  getDecisions: (matchId: string) => request<CoachDecision[]>(`/matches/${matchId}/decisions`),
  getActions: (matchId: string) => request<Action[]>(`/matches/${matchId}/actions`),
  getRecovery: (matchId: string) => request<{ recoveries: number; crash_fired: boolean }>(`/matches/${matchId}/recovery`),
  runBatch: () => request<EvaluationBatch>("/evaluations", { method: "POST", body: JSON.stringify({ seeds: [42, 43] }) }),
  getEvaluation: (batchId: string) => request<EvaluationBatch>(`/evaluations/${batchId}`),
  createMatch: (body: CreateMatchRequest) =>
    request<MatchState>("/matches", { method: "POST", body: JSON.stringify(body) }),
  getMatch: (matchId: string) => request<MatchState>(`/matches/${matchId}`),
  getFrames: (matchId: string, fromSeq = 0, limit = 50) =>
    request<FramesPage>(`/matches/${matchId}/frames?from_seq=${fromSeq}&limit=${limit}`),
  getEvents: (matchId: string) => request<MatchEvent[]>(`/matches/${matchId}/events`),
  // Read-only: selecting a coach must never trigger a write (PRD §13.3).
  getBriefing: (matchId: string, teamId: TeamId) =>
    request<Briefing>(`/matches/${matchId}/briefings/${teamId}`),
  resetMatch: (matchId: string) =>
    request<MatchState>(`/matches/${matchId}/reset`, { method: "POST" }),
  injectCrash: (body: InjectCrashRequest) =>
    request<InjectCrashResponse>("/demo/inject-crash", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
