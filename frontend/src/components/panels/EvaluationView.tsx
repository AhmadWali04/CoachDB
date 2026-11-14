import type { TeamId } from "../../api/types";
import type { EvaluationBatch } from "../../types/evaluation";
import "./panels.css";
import "./EvaluationView.css";

export interface EvaluationViewProps {
  batch: EvaluationBatch | null;
}

const TEAMS: TeamId[] = ["blue", "red"];

const METRIC_LABELS: Record<string, string> = {
  prediction_accuracy: "Prediction accuracy",
  decision_validity: "Decision validity",
  execution_reliability: "Execution reliability",
  recovery_correctness: "Recovery correctness",
  evidence_grounding: "Evidence grounding",
  avg_decision_latency_ms: "Avg. decision latency",
};

export function EvaluationView({ batch }: EvaluationViewProps) {
  return (
    <section className="panel" aria-label="Evaluation">
      <h3 className="panel__title">Evaluation</h3>
      {!batch ? (
        <p className="panel__empty">No evaluation batch has run yet.</p>
      ) : (
        <>
          <p className="evaluation__summary">
            {batch.results.length} seeded match{batch.results.length === 1 ? "" : "es"}, sides
            swapped across paired runs. Metrics are reported separately per coach, never ranked
            by wins alone (PRD §12).
          </p>
          <table className="evaluation__table">
            <thead>
              <tr>
                <th>Metric</th>
                {TEAMS.map((team) => (
                  <th key={team}>{team}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.keys(METRIC_LABELS).map((metric) => (
                <tr key={metric}>
                  <td>{METRIC_LABELS[metric]}</td>
                  {TEAMS.map((team) => (
                    <td key={team}>{formatMetric(metric, batch.metrics[team]?.[metric as keyof typeof batch.metrics.blue])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function formatMetric(metric: string, value: number | undefined): string {
  if (value === undefined) return "—";
  if (metric === "avg_decision_latency_ms") return `${Math.round(value)} ms`;
  return `${Math.round(value * 100)}%`;
}
