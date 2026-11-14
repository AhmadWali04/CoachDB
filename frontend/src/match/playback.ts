// Pure interpolation helpers, kept separate from the React hook so they're
// trivial to unit test without a DOM or rAF loop.
import type { BallPosition, Frame, PlayerPosition } from "../api/types";

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function interpolatePlayers(from: Frame, to: Frame, t: number): PlayerPosition[] {
  const toById = new Map(to.players.map((p) => [p.player_id, p]));
  return from.players.map((player) => {
    const target = toById.get(player.player_id);
    if (!target) return player;
    return { ...player, x: lerp(player.x, target.x, t), y: lerp(player.y, target.y, t) };
  });
}

export function interpolateBall(from: Frame, to: Frame, t: number): BallPosition {
  return {
    x: lerp(from.ball.x, to.ball.x, t),
    y: lerp(from.ball.y, to.ball.y, t),
    owner_player_id: t < 0.5 ? from.ball.owner_player_id : to.ball.owner_player_id,
  };
}
