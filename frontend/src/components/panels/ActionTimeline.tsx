import type { Action, ActionStatus } from "../../types/action";
import "./panels.css";
import "./ActionTimeline.css";

export interface ActionTimelineProps {
  actions: Action[];
}

export function ActionTimeline({ actions }: ActionTimelineProps) {
  const ordered = [...actions].sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  return (
    <section className="panel" aria-label="Action timeline">
      <h3 className="panel__title">Action timeline</h3>
      {ordered.length === 0 ? (
        <p className="panel__empty">No actions recorded yet.</p>
      ) : (
        <ul className="action-timeline">
          {ordered.map((action) => (
            <li key={action.action_id} className="action-timeline__item">
              <StatusBadge status={action.status} />
              <span className="action-timeline__team">{action.team_id}</span>
              <span className="action-timeline__detail">
                {action.requested.formation} / {action.requested.mentality}
              </span>
              {action.status === "verified" && (
                <span className="action-timeline__version">
                  v{action.expected_state_version} → v{action.observed_state_version}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const STATUS_LABEL: Record<ActionStatus, string> = {
  proposed: "Proposed",
  submitted: "Submitted",
  applied: "Applied",
  verified: "Verified",
  rejected: "Rejected",
  failed: "Failed",
  unknown: "Unknown",
};

function StatusBadge({ status }: { status: ActionStatus }) {
  return <span className={`action-status action-status--${status}`}>{STATUS_LABEL[status]}</span>;
}
