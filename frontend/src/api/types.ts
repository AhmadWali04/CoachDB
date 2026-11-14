// Friendly aliases over the generated contract. Never hand-edit schema.d.ts;
// regenerate it with `npm run gen:api` after the backend contract changes.
import type { components } from "./schema";

type S = components["schemas"];

export type TeamId = S["TeamId"];
export type PitchSide = S["PitchSide"];
export type MatchPhase = S["MatchPhase"];
export type EventType = S["EventType"];
export type AudioStatus = S["AudioStatus"];

export type MatchState = S["MatchState"];
export type Team = S["Team"];
export type Player = S["Player"];
export type TacticalSettings = S["TacticalSettings"];
export type MatchEvent = S["MatchEvent"];

export type Frame = S["Frame"];
export type FramesPage = S["FramesPage"];
export type PlayerPosition = S["PlayerPosition"];
export type BallPosition = S["BallPosition"];

export type Briefing = S["Briefing"];
export type CreateMatchRequest = S["CreateMatchRequest"];
export type InjectCrashRequest = S["InjectCrashRequest"];
export type InjectCrashResponse = S["InjectCrashResponse"];
