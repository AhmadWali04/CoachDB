// Arrows are derived only from events + positions the simulator already
// emitted in this frame (PRD §13.2). Never invented, never animated beyond
// what the event says happened.
import type { Frame } from "../api/types";

export interface Arrow {
  id: string;
  type: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
}

const ARROW_EVENT_TYPES = new Set([
  "pass_sequence",
  "counterattack",
  "pressing_success",
  "turnover",
]);

export function deriveArrows(frame: Frame | null, cap = 3): Arrow[] {
  if (!frame) return [];
  const byId = new Map(frame.players.map((p) => [p.player_id, p]));
  const arrows: Arrow[] = [];

  for (const event of frame.events ?? []) {
    if (arrows.length >= cap) break;
    if (!ARROW_EVENT_TYPES.has(event.type)) continue;
    const playerIds = event.player_ids ?? [];
    if (playerIds.length < 2) continue;

    const from = byId.get(playerIds[0]);
    const to = byId.get(playerIds[playerIds.length - 1]);
    if (!from || !to) continue;

    arrows.push({
      id: event.event_id,
      type: event.type,
      from: { x: from.x, y: from.y },
      to: { x: to.x, y: to.y },
    });
  }

  return arrows;
}
