import { useBriefingAudio } from "../../audio/useBriefingAudio";
import type { TeamId } from "../../api/types";
import "./CoachPanel.css";

export interface CoachPanelProps {
  matchId: string | null;
  selectedTeam: TeamId | null;
}

export function CoachPanel({ matchId, selectedTeam }: CoachPanelProps) {
  const { status, briefing, play, pause, replay } = useBriefingAudio(matchId, selectedTeam);

  if (!selectedTeam) {
    return (
      <section className="coach-panel coach-panel--empty" aria-label="Coach briefing">
        <p>Select a team to hear its halftime briefing.</p>
      </section>
    );
  }

  return (
    <section className="coach-panel" aria-label="Coach briefing">
      <header className="coach-panel__header">
        <span className="coach-panel__coach">{briefing?.coach_name ?? `${selectedTeam} coach`}</span>
        <span className={`coach-panel__status coach-panel__status--${status}`}>{statusLabel(status)}</span>
      </header>

      {status === "loading" && <p className="coach-panel__transcript">Loading briefing…</p>}
      {status === "error" && <p className="coach-panel__transcript">Couldn't load this briefing. Try again.</p>}

      {briefing && (
        <>
          <p className="coach-panel__transcript">{briefing.transcript}</p>
          <div className="coach-panel__controls">
            {status === "playing" ? (
              <button type="button" onClick={pause}>
                Pause
              </button>
            ) : (
              <button type="button" onClick={play} disabled={status === "unavailable"}>
                Play
              </button>
            )}
            <button type="button" onClick={replay} disabled={status === "unavailable"}>
              Replay
            </button>
          </div>
          {status === "unavailable" && (
            <p className="coach-panel__note">Audio unavailable right now -- transcript above is still accurate.</p>
          )}
        </>
      )}
    </section>
  );
}

function statusLabel(status: string): string {
  switch (status) {
    case "loading":
      return "Loading";
    case "playing":
      return "Playing";
    case "paused":
      return "Paused";
    case "unavailable":
      return "Text only";
    case "error":
      return "Error";
    default:
      return "";
  }
}
