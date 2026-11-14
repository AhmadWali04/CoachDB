import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { MatchState } from "../../api/types";
import "./panels.css";

export interface DemoControlsProps {
  matchId: string | null;
  onMatchChange: (match: MatchState) => void;
}

export function DemoControls({ matchId, onMatchChange }: DemoControlsProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(action: string, task: () => Promise<MatchState>) {
    setBusy(action);
    setError(null);
    try {
      onMatchChange(await task());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel" aria-label="Demo controls">
      <h3 className="panel__title">Demo controls</h3>
      <div className="demo-controls__row">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => run("start", () => api.createMatch({ steps_per_half: 20 }))}
        >
          {busy === "start" ? "Starting…" : "Start match"}
        </button>
        <button
          type="button"
          disabled={busy !== null || !matchId}
          onClick={() => matchId && run("reset", () => api.resetMatch(matchId))}
        >
          {busy === "reset" ? "Resetting…" : "Reset match"}
        </button>
        <button
          type="button"
          disabled={busy !== null || !matchId}
          title="Injects a crash between action submit and verify (PRD §9.3)"
          onClick={() =>
            matchId &&
            run("crash", async () => {
              await api.injectCrash({ match_id: matchId, point: "after_submit_before_verify" });
              return api.getMatch(matchId);
            })
          }
        >
          {busy === "crash" ? "Injecting…" : "Inject crash"}
        </button>
        <button type="button" disabled title="Needs Track A's evaluation batch endpoint">
          Run batch
        </button>
      </div>
      {error && <p className="panel__error">{error}</p>}
    </section>
  );
}
