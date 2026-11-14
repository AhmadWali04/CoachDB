import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EvaluationBatch } from "../../types/evaluation";
import { EvaluationView } from "./EvaluationView";

function buildBatch(overrides: Partial<EvaluationBatch> = {}): EvaluationBatch {
  return {
    batch_id: "batch_1",
    results: [{ seed: 42, sides_swapped: false, score: { blue: 2, red: 1 } }],
    metrics: {
      blue: {
        prediction_accuracy: 0.8,
        decision_validity: 0.9,
        execution_reliability: 1,
        recovery_correctness: 1,
        evidence_grounding: 0.7,
        avg_decision_latency_ms: 1200,
      },
      red: {
        prediction_accuracy: 0.6,
        decision_validity: 0.85,
        execution_reliability: 0.95,
        recovery_correctness: 1,
        evidence_grounding: 0.65,
        avg_decision_latency_ms: 1400,
      },
    },
    ...overrides,
  };
}

describe("EvaluationView", () => {
  it("shows an empty state with no batch", () => {
    render(<EvaluationView batch={null} />);
    expect(screen.getByText("No evaluation batch has run yet.")).toBeInTheDocument();
  });

  it("renders per-coach metrics without ranking by wins", () => {
    render(<EvaluationView batch={buildBatch()} />);
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText("1200 ms")).toBeInTheDocument();
    expect(screen.queryByText(/winner/i)).not.toBeInTheDocument();
  });

  it("shows a dash for a metric missing from a coach", () => {
    const batch = buildBatch({
      metrics: {
        blue: buildBatch().metrics.blue,
        red: undefined as never,
      },
    });
    render(<EvaluationView batch={batch} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
