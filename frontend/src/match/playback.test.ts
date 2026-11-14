import { describe, expect, it } from "vitest";
import { buildFrame } from "../test/factories";
import { interpolateBall, interpolatePlayers, lerp } from "./playback";

describe("lerp", () => {
  it("interpolates linearly", () => {
    expect(lerp(0, 10, 0)).toBe(0);
    expect(lerp(0, 10, 1)).toBe(10);
    expect(lerp(0, 10, 0.5)).toBe(5);
  });
});

describe("interpolatePlayers", () => {
  it("moves each player toward its position in the next frame", () => {
    const from = buildFrame({
      players: [{ player_id: "blue_9", team_id: "blue", x: 0, y: 0 }],
    });
    const to = buildFrame({
      players: [{ player_id: "blue_9", team_id: "blue", x: 10, y: 20 }],
    });

    const result = interpolatePlayers(from, to, 0.5);

    expect(result).toEqual([{ player_id: "blue_9", team_id: "blue", x: 5, y: 10 }]);
  });

  it("leaves a player untouched if absent from the next frame", () => {
    const from = buildFrame({
      players: [{ player_id: "blue_9", team_id: "blue", x: 0, y: 0 }],
    });
    const to = buildFrame({ players: [] });

    expect(interpolatePlayers(from, to, 0.9)).toEqual(from.players);
  });
});

describe("interpolateBall", () => {
  it("interpolates position and switches owner at the midpoint", () => {
    const from = buildFrame({ ball: { x: 0, y: 0, owner_player_id: "blue_9" } });
    const to = buildFrame({ ball: { x: 10, y: 10, owner_player_id: "red_9" } });

    expect(interpolateBall(from, to, 0.25)).toEqual({ x: 2.5, y: 2.5, owner_player_id: "blue_9" });
    expect(interpolateBall(from, to, 0.75)).toEqual({ x: 7.5, y: 7.5, owner_player_id: "red_9" });
  });
});
