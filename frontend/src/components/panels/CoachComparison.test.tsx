import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildCoachDecision } from "../../test/factories";
import { CoachComparison } from "./CoachComparison";

describe("CoachComparison", () => {
  it("shows a pending message for a team with no decision yet", () => {
    render(<CoachComparison decisions={{}} />);
    expect(screen.getAllByText("No halftime decision yet.")).toHaveLength(2);
  });

  it("renders only the structured decision fields, never inventing content", () => {
    const blue = buildCoachDecision("blue");
    render(<CoachComparison decisions={{ blue }} />);

    expect(screen.getByText(blue.analysis.summary)).toBeInTheDocument();
    expect(screen.getByText(blue.analysis.own_strengths[0].observation)).toBeInTheDocument();
    expect(screen.getByText(blue.plan.primary_objective)).toBeInTheDocument();
    expect(screen.getByText("No halftime decision yet.")).toBeInTheDocument();
  });

  it("flags when the balanced fallback plan was used", () => {
    const blue = buildCoachDecision("blue", { used_fallback: true });
    render(<CoachComparison decisions={{ blue }} />);
    expect(screen.getByText("Balanced fallback plan was used.")).toBeInTheDocument();
  });
});
