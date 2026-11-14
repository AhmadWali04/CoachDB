import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildAction } from "../../test/factories";
import { ActionTimeline } from "./ActionTimeline";

describe("ActionTimeline", () => {
  it("shows an empty state with no actions", () => {
    render(<ActionTimeline actions={[]} />);
    expect(screen.getByText("No actions recorded yet.")).toBeInTheDocument();
  });

  it("orders actions newest first", () => {
    const older = buildAction({
      action_id: "a1",
      updated_at: "2026-01-01T00:00:00Z",
      requested: {
        formation: "4-4-2",
        mentality: "defensive",
        pressing: "low",
        defensive_line: "low",
        attack_focus: "middle",
        tempo: "slow",
      },
    });
    const newer = buildAction({
      action_id: "a2",
      updated_at: "2026-01-02T00:00:00Z",
      requested: {
        formation: "4-3-3",
        mentality: "attacking",
        pressing: "high",
        defensive_line: "high",
        attack_focus: "right",
        tempo: "fast",
      },
    });
    render(<ActionTimeline actions={[older, newer]} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("4-3-3");
    expect(items[1]).toHaveTextContent("4-4-2");
  });

  it("shows the verified state version transition only once verified", () => {
    const verified = buildAction({
      status: "verified",
      expected_state_version: 5,
      observed_state_version: 6,
    });
    render(<ActionTimeline actions={[verified]} />);
    expect(screen.getByText("v5 → v6")).toBeInTheDocument();
  });

  it("does not show a version transition for a submitted (unverified) action", () => {
    const submitted = buildAction({ status: "submitted", observed_state_version: null });
    render(<ActionTimeline actions={[submitted]} />);
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
  });
});
