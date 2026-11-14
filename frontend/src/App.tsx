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
import { usePolling } from "./match/usePolling";
import { api } from "./api/client";
import type { EvaluationBatch } from "./types/evaluation";

const isFinished = (m: MatchState) => m.phase === "full_time";
const batchDone = (b: EvaluationBatch) => b.status !== undefined && b.status !== "running";

function App() {
  const [match, setMatch] = useState<MatchState | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<TeamId | null>(null);
  const [fixtureFrames, setFixtureFrames] = useState<Frame[] | null>(null);

  const [batchId, setBatchId] = useState<string | null>(null);
  const isLive = match !== null;
  const matchId = match?.match_id ?? null;
  // Live score, clock, phase and tactics; falls back to the last action's response.
  const liveMatch = usePolling(matchId, api.getMatch, 1000, isFinished) ?? match;
  const decisions = usePolling(matchId, api.getDecisions, 2000) ?? {};
  const actions = usePolling(matchId, api.getActions, 1500) ?? [];
  const batch = usePolling(batchId, api.getEvaluation, 2000, batchDone);
  const liveFrames = useLiveFrames(match?.match_id ?? null, isLive);
  const events = useLiveEvents(match?.match_id ?? null, isLive);

  useEffect(() => {
    if (isLive) return;
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
            match={liveMatch}
            players={playback.players}
            ball={playback.ball}
            arrows={arrows}
            isFixture={!isLive}
            reducedMotion={reducedMotion}
            selectedTeam={selectedTeam}
            activeSpeaker={selectedTeam}
            onSelectTeam={(teamId) => setSelectedTeam((current) => (current === teamId ? null : teamId))}
          />
        </div>

        <aside className="dashboard__side">
          <CoachPanel matchId={match?.match_id ?? null} selectedTeam={selectedTeam} />
          <DemoControls
            matchId={match?.match_id ?? null}
            onMatchChange={setMatch}
            onBatchStarted={setBatchId}
          />
          <EventFeed events={events} />
          {/* No coach_decisions/action-ledger/evaluation endpoint exists yet
              (Track A -- see CHECKLIST.md Requests), so these render their
              own empty state until real data is wired in. */}
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
