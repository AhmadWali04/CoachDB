import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { buildFrame, buildMatchState } from "../../test/factories";
import { TacticalPitch } from "./TacticalPitch";

describe("TacticalPitch", () => {
  it("renders from the given frame without fabricating any positions", () => {
    const frame = buildFrame();
    render(
      <TacticalPitch
        match={buildMatchState()}
        players={frame.players}
        ball={frame.ball}
        arrows={[]}
        isFixture={false}
      />,
    );

    for (const player of frame.players) {
      expect(screen.getByTestId(`player-${player.player_id}`)).toBeInTheDocument();
    }
  });

  it("shows the fixture badge only when rendering fixture data", () => {
    const { rerender } = render(
      <TacticalPitch match={null} players={[]} ball={null} arrows={[]} isFixture={true} />,
    );
    expect(screen.getByText("Fixture data")).toBeInTheDocument();

    rerender(<TacticalPitch match={null} players={[]} ball={null} arrows={[]} isFixture={false} />);
    expect(screen.queryByText("Fixture data")).not.toBeInTheDocument();
  });

  it("shows score, clock, and phase from match state, not invented values", () => {
    render(
      <TacticalPitch
        match={buildMatchState({ score: { blue: 2, red: 1 }, clock_minute: 37, phase: "second_half" })}
        players={[]}
        ball={null}
        arrows={[]}
        isFixture={false}
      />,
    );
    expect(screen.getByText("2–1")).toBeInTheDocument();
    expect(screen.getByText("37'")).toBeInTheDocument();
    expect(screen.getByText("second half")).toBeInTheDocument();
  });

  it("selecting a team via its half calls onSelectTeam exactly once, with no side effects beyond the callback", async () => {
    const onSelectTeam = vi.fn();
    render(
      <TacticalPitch
        match={buildMatchState()}
        players={[]}
        ball={null}
        arrows={[]}
        isFixture={false}
        onSelectTeam={onSelectTeam}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /select blue/i }));

    expect(onSelectTeam).toHaveBeenCalledOnce();
    expect(onSelectTeam).toHaveBeenCalledWith("blue");
  });

  it("selecting a team via its HUD card also works and reflects the selected state", async () => {
    const onSelectTeam = vi.fn();
    render(
      <TacticalPitch
        match={buildMatchState()}
        players={[]}
        ball={null}
        arrows={[]}
        isFixture={false}
        selectedTeam="red"
        onSelectTeam={onSelectTeam}
      />,
    );

    const redCard = screen.getByRole("button", { name: /red coach card/i, pressed: true });
    expect(redCard).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /blue coach card/i }));
    expect(onSelectTeam).toHaveBeenCalledWith("blue");
  });
});
