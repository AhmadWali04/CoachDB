import { describe, expect, it } from "vitest";
import { buildEvent, buildFrame } from "../test/factories";
import { deriveArrows } from "./arrows";

describe("deriveArrows", () => {
  it("returns no arrows for a null frame", () => {
    expect(deriveArrows(null)).toEqual([]);
  });

  it("draws an arrow between the first and last player in a multi-player event", () => {
    const frame = buildFrame({
      events: [buildEvent({ event_id: "e1", type: "pass_sequence", player_ids: ["blue_9", "blue_10"] })],
    });

    const arrows = deriveArrows(frame);

    expect(arrows).toEqual([
      {
        id: "e1",
        type: "pass_sequence",
        from: { x: 40, y: 30 },
        to: { x: 60, y: 35 },
      },
    ]);
  });

  it("ignores events without a drawable pair of players", () => {
    const frame = buildFrame({
      events: [
        buildEvent({ event_id: "e1", type: "shot", player_ids: ["blue_9"] }),
        buildEvent({ event_id: "e2", type: "foul", player_ids: [] }),
      ],
    });

    expect(deriveArrows(frame)).toEqual([]);
  });

  it("ignores event types that aren't meant to draw arrows", () => {
    const frame = buildFrame({
      events: [buildEvent({ event_id: "e1", type: "goal", player_ids: ["blue_9", "blue_10"] })],
    });

    expect(deriveArrows(frame)).toEqual([]);
  });

  it("never exceeds the cap even with many qualifying events", () => {
    const frame = buildFrame({
      events: Array.from({ length: 6 }, (_, i) =>
        buildEvent({ event_id: `e${i}`, type: "pass_sequence", player_ids: ["blue_9", "blue_10"] }),
      ),
    });

    expect(deriveArrows(frame, 3)).toHaveLength(3);
  });

  it("skips events referencing players absent from this frame", () => {
    const frame = buildFrame({
      events: [buildEvent({ event_id: "e1", type: "pass_sequence", player_ids: ["blue_9", "unknown_player"] })],
    });

    expect(deriveArrows(frame)).toEqual([]);
  });
});
