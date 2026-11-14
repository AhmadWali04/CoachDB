import { api } from "./api/client";
import type { Action } from "./types/action";
import type { CoachDecision } from "./types/coachAnalysis";
import type { EvaluationBatch } from "./types/evaluation";
import { useEffect, useMemo, useState } from "react";
import "./App.css";
import type { Frame, MatchState, TeamId } from "./api/types";
import { CoachPanel } from "./components/coach/CoachPanel";
import { ActionTimeline } from "./components/panels/ActionTimeline";
import { CoachComparison } from "./components/panels/CoachComparison";
import { DatasetAttribution } from "./components/panels/DatasetAttribution";
import { DemoControls } from "./components/panels/DemoControls";
import { EvaluationView } from "./components/panels/EvaluationView";
import { EventFeed } from "./components/panels/EventFeed";
import { TacticalPitch } from "./components/pitch/TacticalPitch";
import { deriveArrows } from "./match/arrows";
import { listFixtureNames, loadFixture } from "./match/fixtures";
import { prefersReducedMotion, useFramePlayback } from "./match/useFramePlayback";
import { useLiveEvents } from "./match/useLiveEvents";
import { useLiveFrames } from "./match/useLiveFrames";

function App() {
  const [match, setMatch] = useState<MatchState | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<TeamId | null>(null);
  const [fixtureFrames, setFixtureFrames] = useState<Frame[] | null>(null);

  const [decisions, setDecisions] = useState<Partial<Record<TeamId, CoachDecision>>>({});
  const [actions, setActions] = useState<Action[]>([]);
  const [batch, setBatch] = useState<EvaluationBatch | null>(null);
  const [recoveries, setRecoveries] = useState(0);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const matchId = match?.match_id ?? null;

  useEffect(() => {
    if (!matchId) return;
    let cancelled = false;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const [state, coachRows, ledger, recovery] = await Promise.all([
          api.getMatch(matchId), api.getDecisions(matchId), api.getActions(matchId), api.getRecovery(matchId),
        ]);
        if (!cancelled) {
          setMatch(state);
          setDecisions(Object.fromEntries(coachRows.map((decision) => [decision.team_id, decision])));
          setActions(ledger); setRecoveries(recovery.recoveries); setConnectionError(null);
        }
      } catch { if (!cancelled) setConnectionError("Connection interrupted; retrying…"); }
      finally { inFlight = false; }
    };
    void poll();
    const timer = setInterval(poll, 700);
    return () => { cancelled = true; clearInterval(timer); };
  }, [matchId]);

  const batchId = batch?.batch_id ?? null;
  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    const poll = async () => {
      try { const updated = await api.getEvaluation(batchId); if (!cancelled) setBatch(updated); }
      catch { /* next poll retries */ }
    };
    const timer = setInterval(poll, 1000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [batchId]);

  const isLive = match !== null;
  const liveFrames = useLiveFrames(match?.match_id ?? null, isLive);
  const events = useLiveEvents(match?.match_id ?? null, isLive);

  useEffect(() => {
    if (isLive || !import.meta.env.DEV) return;
    const [first] = listFixtureNames();
    if (!first) return;
    loadFixture(first).then((page) => {
      if (page) setFixtureFrames(page.frames);
    });
  }, [isLive]);

  const frames = isLive ? liveFrames : fixtureFrames ?? [];
  const playback = useFramePlayback(frames);
  const arrows = useMemo(() => deriveArrows(playback.currentFrame), [playback.currentFrame]);
  const reducedMotion = useMemo(() => prefersReducedMotion(), []);

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>Rival Coaches</h1>
      </header>

      <main className="dashboard__grid">
        <div className="dashboard__pitch">
          <TacticalPitch
            match={match}
            players={playback.players}
            ball={playback.ball}
            arrows={arrows}
            isFixture={!isLive && fixtureFrames !== null}
            reducedMotion={reducedMotion}
            selectedTeam={selectedTeam}
            activeSpeaker={selectedTeam}
            onSelectTeam={(teamId) => setSelectedTeam((current) => (current === teamId ? null : teamId))}
          />
        </div>

        <aside className="dashboard__side">
          <CoachPanel matchId={match?.match_id ?? null} selectedTeam={selectedTeam} />
          <DemoControls matchId={match?.match_id ?? null} onMatchChange={setMatch} onBatchChange={setBatch} />
          {connectionError && <p role="status">{connectionError}</p>}
          {recoveries > 0 && <p role="status">Recovered {recoveries} worker interruption(s); tactical effects reconciled.</p>}
          <EventFeed events={events} />
          <CoachComparison decisions={decisions} />
          <ActionTimeline actions={actions} />
          <EvaluationView batch={batch} />
          <DatasetAttribution />
        </aside>
      </main>
    </div>
  );
}

export default App;
