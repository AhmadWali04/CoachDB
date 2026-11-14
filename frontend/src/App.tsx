import { useEffect, useMemo, useState } from "react";
import "./App.css";
import type { Frame, MatchState, TeamId } from "./api/types";
import { CoachPanel } from "./components/coach/CoachPanel";
import { DatasetAttribution } from "./components/panels/DatasetAttribution";
import { DemoControls } from "./components/panels/DemoControls";
import { EventFeed } from "./components/panels/EventFeed";
import { PendingPanel } from "./components/panels/PendingPanel";
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

  const isLive = match !== null;
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
            match={match}
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
          <DemoControls matchId={match?.match_id ?? null} onMatchChange={setMatch} />
          <EventFeed events={events} />
          <PendingPanel
            title="Coach comparison"
            reason="Needs Track A's coach_decisions (analysis, scouting, prediction, tactics) -- see CHECKLIST.md Requests."
          />
          <PendingPanel
            title="Action timeline"
            reason="Needs a read endpoint over the action ledger (proposed → submitted → applied → verified) from Track A."
          />
          <PendingPanel
            title="Evaluation"
            reason="Needs Track A's GET /evaluations/{batch_id}."
          />
          <DatasetAttribution />
        </aside>
      </main>
    </div>
  );
}

export default App;
