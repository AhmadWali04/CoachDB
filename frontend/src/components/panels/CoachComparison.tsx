import type { TeamId } from "../../api/types";
import type { CoachDecision } from "../../types/coachAnalysis";
import "./panels.css";
import "./CoachComparison.css";

export interface CoachComparisonProps {
  decisions: Partial<Record<TeamId, CoachDecision>>;
}

const TEAMS: TeamId[] = ["blue", "red"];

export function CoachComparison({ decisions }: CoachComparisonProps) {
  return (
    <section className="panel" aria-label="Coach comparison">
      <h3 className="panel__title">Coach comparison</h3>
      <div className="coach-comparison">
        {TEAMS.map((teamId) => (
          <CoachColumn key={teamId} teamId={teamId} decision={decisions[teamId]} />
        ))}
      </div>
    </section>
  );
}

function CoachColumn({ teamId, decision }: { teamId: TeamId; decision?: CoachDecision }) {
  if (!decision) {
    return (
      <div className={`coach-comparison__column coach-comparison__column--${teamId}`}>
        <h4 className="coach-comparison__team">{teamId}</h4>
        <p className="panel__empty">No halftime decision yet.</p>
      </div>
    );
  }

  const { analysis, scouting, plan } = decision;

  return (
    <div className={`coach-comparison__column coach-comparison__column--${teamId}`}>
      <h4 className="coach-comparison__team">{teamId}</h4>

      <section>
        <h5>Analysis</h5>
        <p>{analysis.summary}</p>
        <ObservationList label="Strengths" items={analysis.own_strengths} />
        <ObservationList label="Weaknesses" items={analysis.own_weaknesses} />
      </section>

      <section>
        <h5>Scouting the rival</h5>
        <dl className="coach-comparison__tactics">
          {Object.entries(scouting.observed_tactics)
            .filter(([, value]) => value)
            .map(([key, value]) => (
              <div key={key}>
                <dt>{key.replace(/_/g, " ")}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
        {scouting.likely_adjustments.map((adjustment, i) => (
          <p key={i} className="coach-comparison__prediction">
            Likely: {adjustment.change} ({Math.round(adjustment.confidence * 100)}% confidence)
          </p>
        ))}
      </section>

      <section>
        <h5>Halftime plan</h5>
        <p className="coach-comparison__plan-summary">
          {plan.plan.formation} · {plan.plan.mentality} · {plan.plan.pressing} press ·{" "}
          {plan.plan.tempo} tempo
        </p>
        <p>{plan.primary_objective}</p>
        <p className="coach-comparison__rationale">{plan.rationale}</p>
        {plan.risks.length > 0 && (
          <p className="coach-comparison__risks">Risks: {plan.risks.join("; ")}</p>
        )}
        {decision.used_fallback && (
          <p className="coach-comparison__fallback">Balanced fallback plan was used.</p>
        )}
      </section>
    </div>
  );
}

function ObservationList({ label, items }: { label: string; items: { observation: string }[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <strong>{label}:</strong>
      <ul>
        {items.map((item, i) => (
          <li key={i}>{item.observation}</li>
        ))}
      </ul>
    </div>
  );
}
