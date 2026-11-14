import type { KeyboardEvent } from "react";
import type { BallPosition, MatchState, PlayerPosition, TeamId } from "../../api/types";
import type { Arrow } from "../../match/arrows";
import {
  CENTER_CIRCLE_RADIUS,
  GOAL_AREA_LENGTH,
  GOAL_WIDTH,
  PENALTY_AREA_LENGTH,
  PITCH_LENGTH,
  PITCH_WIDTH,
  goalArea,
  goalMouth,
  penaltyArea,
  toViewBoxX,
  toViewBoxY,
} from "./pitchMarkings";
import "./TacticalPitch.css";

const TEAM_COLOR: Record<string, string> = { blue: "#3b82f6", red: "#ef4444" };

export interface TacticalPitchProps {
  match: MatchState | null;
  players: PlayerPosition[];
  ball: BallPosition | null;
  arrows: Arrow[];
  isFixture: boolean;
  reducedMotion?: boolean;
  selectedTeam?: TeamId | null;
  activeSpeaker?: TeamId | null;
  onSelectTeam?: (teamId: TeamId) => void;
}

export function TacticalPitch({
  match,
  players,
  ball,
  arrows,
  isFixture,
  reducedMotion = false,
  selectedTeam = null,
  activeSpeaker = null,
  onSelectTeam,
}: TacticalPitchProps) {
  const blue = match?.teams.find((team) => team.team_id === "blue") ?? null;
  const red = match?.teams.find((team) => team.team_id === "red") ?? null;

  const select = (teamId: TeamId) => onSelectTeam?.(teamId);
  const onHalfKeyDown = (teamId: TeamId) => (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(teamId);
    }
  };

  return (
    <section className="tactical-pitch" aria-label="Tactical pitch">
      {isFixture && <span className="fixture-badge">Fixture data</span>}

      <header className="pitch-hud">
        <TeamHud
          team={blue}
          side="blue"
          selected={selectedTeam === "blue"}
          speaking={activeSpeaker === "blue"}
          onSelect={() => select("blue")}
        />
        <div className="pitch-hud__center">
          <span className="pitch-hud__score">
            {match?.score.blue ?? 0}&ndash;{match?.score.red ?? 0}
          </span>
          <span className="pitch-hud__clock">{match?.clock_minute ?? 0}&apos;</span>
          <span className="pitch-hud__phase">{formatPhase(match?.phase)}</span>
        </div>
        <TeamHud
          team={red}
          side="red"
          selected={selectedTeam === "red"}
          speaking={activeSpeaker === "red"}
          onSelect={() => select("red")}
        />
      </header>

      <svg
        className={`pitch-svg${reducedMotion ? " pitch-svg--reduced-motion" : ""}`}
        viewBox={`0 0 ${PITCH_WIDTH} ${PITCH_LENGTH}`}
        role="img"
        aria-label="Top-down pitch with player and ball positions"
      >
        <defs>
          <marker id="pitch-arrowhead" markerWidth="4" markerHeight="4" refX="2" refY="2" orient="auto">
            <path d="M0,0 L4,2 L0,4 Z" className="pitch-arrow-head" />
          </marker>
        </defs>

        <rect x={0} y={0} width={PITCH_WIDTH} height={PITCH_LENGTH} className="pitch-turf" />

        {/* Team A (blue) upper half / Team B (red) lower half selection targets */}
        <rect
          x={0}
          y={0}
          width={PITCH_WIDTH}
          height={PITCH_LENGTH / 2}
          role="button"
          tabIndex={0}
          aria-label={`Select ${blue?.name ?? "Blue"}`}
          aria-pressed={selectedTeam === "blue"}
          className={`pitch-half pitch-half--blue${selectedTeam === "blue" ? " pitch-half--selected" : ""}`}
          onClick={() => select("blue")}
          onKeyDown={onHalfKeyDown("blue")}
        />
        <rect
          x={0}
          y={PITCH_LENGTH / 2}
          width={PITCH_WIDTH}
          height={PITCH_LENGTH / 2}
          role="button"
          tabIndex={0}
          aria-label={`Select ${red?.name ?? "Red"}`}
          aria-pressed={selectedTeam === "red"}
          className={`pitch-half pitch-half--red${selectedTeam === "red" ? " pitch-half--selected" : ""}`}
          onClick={() => select("red")}
          onKeyDown={onHalfKeyDown("red")}
        />

        <line x1={0} y1={PITCH_LENGTH / 2} x2={PITCH_WIDTH} y2={PITCH_LENGTH / 2} className="pitch-line" />
        <circle cx={PITCH_WIDTH / 2} cy={PITCH_LENGTH / 2} r={CENTER_CIRCLE_RADIUS} className="pitch-line-shape" />
        <circle cx={PITCH_WIDTH / 2} cy={PITCH_LENGTH / 2} r={0.4} className="pitch-spot" />

        <rect x={penaltyArea.x} y={0} width={penaltyArea.width} height={PENALTY_AREA_LENGTH} className="pitch-line-shape" />
        <rect
          x={penaltyArea.x}
          y={PITCH_LENGTH - PENALTY_AREA_LENGTH}
          width={penaltyArea.width}
          height={PENALTY_AREA_LENGTH}
          className="pitch-line-shape"
        />
        <rect x={goalArea.x} y={0} width={goalArea.width} height={GOAL_AREA_LENGTH} className="pitch-line-shape" />
        <rect
          x={goalArea.x}
          y={PITCH_LENGTH - GOAL_AREA_LENGTH}
          width={goalArea.width}
          height={GOAL_AREA_LENGTH}
          className="pitch-line-shape"
        />
        <rect x={goalMouth.x} y={-1.2} width={GOAL_WIDTH} height={1.2} className="pitch-goal" />
        <rect x={goalMouth.x} y={PITCH_LENGTH} width={GOAL_WIDTH} height={1.2} className="pitch-goal" />
        <rect x={0} y={0} width={PITCH_WIDTH} height={PITCH_LENGTH} className="pitch-boundary" />

        {arrows.map((arrow) => (
          <PitchArrow key={arrow.id} arrow={arrow} />
        ))}

        {ball && <circle cx={toViewBoxX(ball.x)} cy={toViewBoxY(ball.y)} r={0.9} className="pitch-ball" />}

        {players.map((player) => (
          <PlayerMarker key={player.player_id} player={player} />
        ))}
      </svg>
    </section>
  );
}

function TeamHud({
  team,
  side,
  selected,
  speaking,
  onSelect,
}: {
  team: MatchState["teams"][number] | null;
  side: TeamId;
  selected: boolean;
  speaking: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`pitch-hud__team pitch-hud__team--${side}${selected ? " pitch-hud__team--selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${team?.name ?? (side === "blue" ? "Blue" : "Red")} coach card`}
    >
      {speaking && <span className="pitch-hud__speaking" aria-label="Speaking now" />}
      <span className="pitch-hud__name">{team?.name ?? (side === "blue" ? "Blue" : "Red")}</span>
      <span className="pitch-hud__formation">{team?.tactics.formation}</span>
    </button>
  );
}

function formatPhase(phase?: string): string {
  if (!phase) return "";
  return phase.replace(/_/g, " ");
}

function PlayerMarker({ player }: { player: PlayerPosition }) {
  const color = TEAM_COLOR[player.team_id] ?? "#999";
  const cx = toViewBoxX(player.x);
  const cy = toViewBoxY(player.y);

  if (player.team_id === "red") {
    return (
      <g className="player-marker" data-testid={`player-${player.player_id}`} transform={`translate(${cx} ${cy})`}>
        <line x1={-1.3} y1={-1.3} x2={1.3} y2={1.3} stroke={color} strokeWidth={0.6} />
        <line x1={-1.3} y1={1.3} x2={1.3} y2={-1.3} stroke={color} strokeWidth={0.6} />
      </g>
    );
  }

  return (
    <circle
      cx={cx}
      cy={cy}
      r={1.3}
      className="player-marker"
      data-testid={`player-${player.player_id}`}
      fill={color}
    />
  );
}

function PitchArrow({ arrow }: { arrow: Arrow }) {
  return (
    <line
      x1={toViewBoxX(arrow.from.x)}
      y1={toViewBoxY(arrow.from.y)}
      x2={toViewBoxX(arrow.to.x)}
      y2={toViewBoxY(arrow.to.y)}
      className={`pitch-arrow pitch-arrow--${arrow.type}`}
      markerEnd="url(#pitch-arrowhead)"
    />
  );
}
