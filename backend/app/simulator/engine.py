"""Deterministic, seeded match engine (PRD §5). A simplified tactical
simulator, not a realistic professional football model (CLAUDE.md).

The simulator is the only source of match facts (CLAUDE.md principle 1):
it never calls an LLM and never reads a coach's reasoning. Halftime
tactical changes are passed in by the caller (the orchestration layer,
once it exists) as plain `TacticalSettings`, not inferred here.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.schemas import (
    BallPosition,
    Frame,
    MatchEvent,
    MatchPhase,
    MatchState,
    PitchSide,
    PlayerPosition,
    Score,
    TacticalSettings,
    Team,
    TeamId,
    TeamStats,
)

from .formations import starting_positions
from .roster import build_team

MINUTES_PER_HALF = 45
TURNOVER_BASE = 0.18
SHOT_BASE = 0.20
FOUL_PROB = 0.04
PRESSING_BOOST = {"low": 0.0, "medium": 0.07, "high": 0.16}
LINE_RISK = {"low": 0.0, "medium": 0.05, "high": 0.12}
MENTALITY_ATTACK_BOOST = {"balanced": 0.0, "attacking": 0.12, "defensive": -0.08}
TEMPO_BOOST = {"slow": -0.04, "normal": 0.0, "fast": 0.07}


@dataclass
class SimulationResult:
    match_id: str
    seed: int
    final_state: MatchState
    events: list[MatchEvent]
    frames: list[Frame]


@dataclass
class _TeamRuntime:
    team: Team
    possession_steps: int = 0


@dataclass
class _SimState:
    match_id: str
    rng: random.Random
    teams: dict[TeamId, _TeamRuntime]
    score: Score = field(default_factory=Score)
    stats: dict[TeamId, TeamStats] = field(default_factory=lambda: {t: TeamStats() for t in TeamId})
    events: list[MatchEvent] = field(default_factory=list)
    frames: list[Frame] = field(default_factory=list)
    event_seq: int = 0
    frame_seq: int = 0
    forced_possession: TeamId | None = None
    last_was_turnover: bool = False
    version: int = 0
    started_at: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=UTC))


class MatchSimulator:
    """One seeded match with serializable authoritative runtime and atomic halftime plans."""

    def __init__(
        self,
        match_id,
        seed,
        blue_tactics,
        red_tactics,
        steps_per_half=20,
        *,
        started_at=None,
        sides_swapped=False,
    ):
        if not 2 <= steps_per_half <= 90:
            raise ValueError("steps_per_half must be 2..90")
        self.seed, self.steps_per_half = seed, steps_per_half
        self.phase, self.half, self.step = MatchPhase.FIRST_HALF, 1, 0
        self.applied_actions = {}
        self.state = _SimState(
            match_id=match_id,
            rng=random.Random(seed),
            teams={
                team: _TeamRuntime(
                    build_team(
                        team,
                        PitchSide.BOTTOM
                        if (team == TeamId.BLUE) == sides_swapped
                        else PitchSide.TOP,
                        tactics,
                    )
                )
                for team, tactics in ((TeamId.BLUE, blue_tactics), (TeamId.RED, red_tactics))
            },
        )
        if started_at is not None:
            self.state.started_at = started_at

    def snapshot(self) -> MatchState:
        _finalize_possession_stats(
            self.state, sum(t.possession_steps for t in self.state.teams.values())
        )
        return MatchState(
            match_id=self.state.match_id,
            seed=self.seed,
            phase=self.phase,
            half=self.half,
            step=self.step,
            steps_per_half=self.steps_per_half,
            clock_minute=(self.half - 1) * 45 + round(45 * self.step / self.steps_per_half),
            score=self.state.score.model_copy(deep=True),
            stats={k: v.model_copy(deep=True) for k, v in self.state.stats.items()},
            teams=[t.team.model_copy(deep=True) for t in self.state.teams.values()],
            state_version=self.state.version,
            created_at=self.state.started_at,
            updated_at=self.state.started_at + timedelta(seconds=self.state.version),
        )

    def advance(self) -> Frame:
        if self.phase not in (MatchPhase.FIRST_HALF, MatchPhase.SECOND_HALF):
            raise ValueError("cannot advance until both halftime plans are applied")
        self.step += 1
        self.state.version += 1
        minute = (self.half - 1) * 45 + round(45 * self.step / self.steps_per_half)
        _run_step(self.state, self.half, self.step, minute)
        frame = self.state.frames[-1]
        if self.step == self.steps_per_half:
            self.phase = MatchPhase.HALFTIME if self.half == 1 else MatchPhase.FULL_TIME
            _emit_event(
                self.state,
                self.half,
                self.step,
                minute,
                None,
                "half_time" if self.half == 1 else "full_time",
            )
            frame.phase = self.phase
            frame.events.append(self.state.events[-1])
        return frame.model_copy(deep=True)

    def apply_plans(self, plans: dict[TeamId, TacticalSettings], action_ids: dict[TeamId, str]):
        if set(plans) != set(TeamId) or set(action_ids) != set(TeamId):
            raise ValueError("both plans and stable action IDs are required")
        if len(set(action_ids.values())) != 2:
            raise ValueError("each team requires a distinct action ID")
        requested = {str(action_ids[t]): plans[t].model_dump(mode="json") for t in TeamId}
        if all(key in self.applied_actions for key in requested):
            if any(self.applied_actions[key] != value for key, value in requested.items()):
                raise ValueError("action ID reused with a different plan")
            return
        if self.phase != MatchPhase.HALFTIME or any(
            key in self.applied_actions for key in requested
        ):
            raise ValueError("plans apply exactly once, together at halftime")
        for team in TeamId:
            tactics = TacticalSettings.model_validate(plans[team].model_dump())
            self.state.teams[team].team.tactics = tactics
        self.applied_actions.update(requested)
        self.state.version += 1
        for team in TeamId:
            _emit_event(self.state, 1, self.step, 45, team, "tactical_change")
        self.phase, self.half, self.step = MatchPhase.SECOND_HALF, 2, 0

    def checkpoint(self) -> dict:
        rng = self.state.rng.getstate()
        return {
            "seed": self.seed,
            "steps_per_half": self.steps_per_half,
            "phase": self.phase.value,
            "half": self.half,
            "step": self.step,
            "applied_actions": self.applied_actions,
            "match_id": self.state.match_id,
            "started_at": self.state.started_at,
            "version": self.state.version,
            "rng": [rng[0], list(rng[1]), rng[2]],
            "teams": {
                t.value: {
                    "team": r.team.model_dump(mode="json"),
                    "possession_steps": r.possession_steps,
                }
                for t, r in self.state.teams.items()
            },
            "score": self.state.score.model_dump(),
            "stats": {t.value: v.model_dump() for t, v in self.state.stats.items()},
            "event_seq": self.state.event_seq,
            "frame_seq": self.state.frame_seq,
            "forced_possession": self.state.forced_possession,
            "last_was_turnover": self.state.last_was_turnover,
        }

    @classmethod
    def restore(cls, checkpoint: dict):
        obj = cls.__new__(cls)
        obj.seed, obj.steps_per_half = checkpoint["seed"], checkpoint["steps_per_half"]
        obj.phase, obj.half, obj.step = (
            MatchPhase(checkpoint["phase"]),
            checkpoint["half"],
            checkpoint["step"],
        )
        obj.applied_actions = dict(checkpoint["applied_actions"])
        rng = random.Random()
        version, internal, gaussian = checkpoint["rng"]
        rng.setstate((version, tuple(internal), gaussian))
        obj.state = _SimState(
            match_id=checkpoint["match_id"],
            rng=rng,
            teams={
                TeamId(t): _TeamRuntime(Team.model_validate(r["team"]), r["possession_steps"])
                for t, r in checkpoint["teams"].items()
            },
            score=Score.model_validate(checkpoint["score"]),
            stats={TeamId(t): TeamStats.model_validate(v) for t, v in checkpoint["stats"].items()},
            version=checkpoint["version"],
            started_at=checkpoint["started_at"],
            event_seq=checkpoint["event_seq"],
            frame_seq=checkpoint["frame_seq"],
            forced_possession=(
                TeamId(checkpoint["forced_possession"]) if checkpoint["forced_possession"] else None
            ),
            last_was_turnover=checkpoint["last_was_turnover"],
        )
        return obj


def run_match(
    match_id,
    seed,
    blue_tactics,
    red_tactics,
    steps_per_half=20,
    second_half_tactics=None,
    *,
    sides_swapped=False,
) -> SimulationResult:
    simulator = MatchSimulator(
        match_id, seed, blue_tactics, red_tactics, steps_per_half, sides_swapped=sides_swapped
    )
    for _ in range(steps_per_half):
        simulator.advance()
    plans = {t: simulator.state.teams[t].team.tactics for t in TeamId}
    plans.update(second_half_tactics or {})
    simulator.apply_plans(plans, {t: f"{match_id}:{t}:halftime" for t in TeamId})
    for _ in range(steps_per_half):
        simulator.advance()
    return SimulationResult(
        match_id, seed, simulator.snapshot(), simulator.state.events, simulator.state.frames
    )


def _run_half(state: _SimState, half: int, steps_per_half: int) -> None:
    for step in range(steps_per_half):
        clock_minute = (half - 1) * MINUTES_PER_HALF + round(
            MINUTES_PER_HALF * step / steps_per_half
        )
        _run_step(state, half=half, step=step, clock_minute=clock_minute)


def _run_step(state: _SimState, half: int, step: int, clock_minute: int) -> None:
    rng = state.rng
    possessing_id, defending_id = _pick_possession(state)
    possessing = state.teams[possessing_id].team
    defending = state.teams[defending_id].team
    state.teams[possessing_id].possession_steps += 1

    step_events: list[MatchEvent] = []

    if rng.random() < FOUL_PROB:
        fouler = _pick_player(rng, defending, prefer_roles=("DF", "MF"))
        step_events.append(
            _build_event(state, half, step, clock_minute, defending_id, "foul", [fouler.player_id])
        )

    turnover_prob = _clamp(
        TURNOVER_BASE
        + PRESSING_BOOST[defending.tactics.pressing.value]
        + (0.05 if possessing.tactics.mentality.value == "defensive" else 0.0)
        + TEMPO_BOOST[possessing.tactics.tempo.value] * -0.3,
        0.05,
        0.6,
    )
    shot_prob = _clamp(
        SHOT_BASE
        + (
            0.08
            if defending.tactics.mentality.value == "attacking"
            else -0.08
            if defending.tactics.mentality.value == "defensive"
            else 0.0
        )
        + MENTALITY_ATTACK_BOOST[possessing.tactics.mentality.value]
        + TEMPO_BOOST[possessing.tactics.tempo.value]
        + LINE_RISK[defending.tactics.defensive_line.value],
        0.03,
        0.55,
    )
    if state.last_was_turnover and (
        possessing.tactics.tempo.value == "fast"
        or possessing.tactics.mentality.value == "attacking"
    ):
        if rng.random() < 0.35:
            step_events.append(_counterattack_event(state, possessing, half, step, clock_minute))
            shot_prob += 0.15

    roll = rng.random()
    main_event_type = "pass_sequence"
    shooter = None
    if roll < turnover_prob:
        main_event_type = "turnover"
        state.stats[possessing_id].turnovers += 1
        step_events.append(
            _build_event(
                state,
                half,
                step,
                clock_minute,
                possessing_id,
                "turnover",
                [_pick_player(rng, possessing, prefer_roles=("MF", "FW")).player_id],
            )
        )
        step_events.append(
            _build_event(state, half, step, clock_minute, defending_id, "possession_change", [])
        )
        if defending.tactics.pressing.value == "high" and rng.random() < 0.5:
            state.stats[defending_id].pressing_successes += 1
            step_events.append(
                _build_event(state, half, step, clock_minute, defending_id, "pressing_success", [])
            )
        state.forced_possession = defending_id
        state.last_was_turnover = True
    else:
        state.last_was_turnover = False
        state.forced_possession = None
        if roll < turnover_prob + shot_prob:
            main_event_type = "shot"
            shooter = _pick_player(rng, possessing, prefer_roles=("FW", "MF"))
            step_events.extend(
                _resolve_shot(state, possessing, defending, shooter, half, step, clock_minute)
            )
        else:
            passer, receiver = _pick_pass_pair(rng, possessing)
            step_events.append(
                _build_event(
                    state,
                    half,
                    step,
                    clock_minute,
                    possessing_id,
                    "pass_sequence",
                    [passer.player_id, receiver.player_id],
                    details={"attack_focus": possessing.tactics.attack_focus.value},
                )
            )

    frame = _build_frame(
        state, half, step, clock_minute, possessing_id, main_event_type, shooter, step_events
    )
    state.frames.append(frame)
    state.events.extend(step_events)
    _decay_stamina(state, possessing, defending)


def _pick_possession(state: _SimState) -> tuple[TeamId, TeamId]:
    if state.forced_possession is not None:
        possessing = state.forced_possession
        return possessing, _rival_of(possessing)

    blue = state.teams[TeamId.BLUE].team
    red = state.teams[TeamId.RED].team
    bias = (
        MENTALITY_ATTACK_BOOST[blue.tactics.mentality.value]
        - MENTALITY_ATTACK_BOOST[red.tactics.mentality.value]
        + 0.5 * (TEMPO_BOOST[blue.tactics.tempo.value] - TEMPO_BOOST[red.tactics.tempo.value])
    )
    blue_prob = _clamp(0.5 + bias * 0.3, 0.15, 0.85)
    return (
        (TeamId.BLUE, TeamId.RED) if state.rng.random() < blue_prob else (TeamId.RED, TeamId.BLUE)
    )


def _rival_of(team_id: TeamId) -> TeamId:
    return TeamId.RED if team_id == TeamId.BLUE else TeamId.BLUE


def _pick_player(rng: random.Random, team: Team, prefer_roles: tuple[str, ...]):
    outfield = [p for p in team.players if p.role.value != "GK" and p.available]
    preferred = [p for p in outfield if p.role.value in prefer_roles] or outfield
    weights = [p.skills.passing * p.stamina + 1 for p in preferred]
    return rng.choices(preferred, weights=weights, k=1)[0]


def _pick_pass_pair(rng: random.Random, team: Team):
    passer = _pick_player(rng, team, prefer_roles=("MF",))
    candidates = [
        p
        for p in team.players
        if p.player_id != passer.player_id and p.role.value != "GK" and p.available
    ]
    receiver = _pick_player_from(rng, candidates, prefer_roles=("FW", "MF"))
    return passer, receiver


def _pick_player_from(rng: random.Random, candidates, prefer_roles: tuple[str, ...]):
    preferred = [p for p in candidates if p.role.value in prefer_roles] or candidates
    weights = [p.skills.pace * p.stamina + 1 for p in preferred]
    return rng.choices(preferred, weights=weights, k=1)[0]


def _counterattack_event(
    state: _SimState, possessing: Team, half: int, step: int, clock_minute: int
) -> MatchEvent:
    carrier = _pick_player(state.rng, possessing, prefer_roles=("FW", "MF"))
    return _build_event(
        state, half, step, clock_minute, possessing.team_id, "counterattack", [carrier.player_id]
    )


def _resolve_shot(
    state, possessing, defending, shooter, half, step, clock_minute
) -> list[MatchEvent]:
    rng = state.rng
    state.stats[possessing.team_id].shots += 1
    shot_quality = (shooter.skills.shooting / 100) * shooter.stamina
    defenders = [p for p in defending.players if p.role.value == "DF"]
    defense_quality = sum(p.skills.defending * p.stamina for p in defenders) / (
        100 * max(len(defenders), 1)
    )
    on_target_prob = _clamp(0.35 + shot_quality - 0.5 * defense_quality, 0.1, 0.85)

    events = [
        _build_event(
            state, half, step, clock_minute, possessing.team_id, "shot", [shooter.player_id]
        )
    ]
    if rng.random() >= on_target_prob:
        return events  # off target: shot only

    state.stats[possessing.team_id].shots_on_target += 1
    keeper = next((p for p in defending.players if p.role.value == "GK"), None)
    save_prob = 0.5 if keeper is None else _clamp(keeper.skills.goalkeeping / 100, 0.1, 0.9)
    if rng.random() < save_prob:
        player_ids = [shooter.player_id] + ([keeper.player_id] if keeper else [])
        events.append(
            _build_event(state, half, step, clock_minute, defending.team_id, "save", player_ids)
        )
    else:
        _add_goal(state, possessing.team_id)
        events.append(
            _build_event(
                state, half, step, clock_minute, possessing.team_id, "goal", [shooter.player_id]
            )
        )
    return events


def _add_goal(state: _SimState, scorer: TeamId) -> None:
    current = getattr(state.score, scorer.value)
    state.score = state.score.model_copy(update={scorer.value: current + 1})


def _decay_stamina(state: _SimState, possessing: Team, defending: Team) -> None:
    for runtime, team, intensity in (
        (state.teams[possessing.team_id], possessing, possessing.tactics.tempo.value),
        (state.teams[defending.team_id], defending, defending.tactics.pressing.value),
    ):
        extra = 0.004 if intensity in ("fast", "high") else 0.0
        decayed_players = [
            p.model_copy(update={"stamina": max(0.0, p.stamina - (0.003 + extra))})
            if p.role.value != "GK"
            else p
            for p in team.players
        ]
        runtime.team = team.model_copy(update={"players": decayed_players})


def _build_event(
    state: _SimState,
    half: int,
    step: int,
    clock_minute: int,
    team_id: TeamId | None,
    type_: str,
    player_ids: list[str],
    details: dict | None = None,
) -> MatchEvent:
    state.event_seq += 1
    return MatchEvent(
        event_id=f"{state.match_id}_e{state.event_seq:06d}",
        match_id=state.match_id,
        half=half,
        step=step,
        clock_minute=clock_minute,
        team_id=team_id,
        type=type_,
        player_ids=player_ids,
        details=details or {},
        created_at=state.started_at + timedelta(seconds=state.event_seq),
    )


def _emit_event(
    state: _SimState, half: int, step: int, clock_minute: int, team_id: TeamId | None, type_: str
) -> None:
    state.events.append(_build_event(state, half, step, clock_minute, team_id, type_, []))


def _build_frame(
    state: _SimState,
    half: int,
    step: int,
    clock_minute: int,
    possessing_id: TeamId,
    main_event_type: str,
    shooter,
    step_events: list[MatchEvent],
) -> Frame:
    rng = state.rng
    state.frame_seq += 1
    positions: list[PlayerPosition] = []

    for team_id, runtime in state.teams.items():
        team = runtime.team
        layout = dict(
            zip(
                [p.player_id for p in team.players],
                starting_positions(team.tactics.formation, team.side),
                strict=True,
            )
        )
        is_possessing = team_id == possessing_id
        advance = _advance_for(main_event_type) if is_possessing else 0.0
        line_shift = _line_shift(team.tactics.defensive_line.value) if not is_possessing else 0.0
        direction = 1.0 if team.side == PitchSide.TOP else -1.0

        for player in team.players:
            _role, base_x, base_y = layout[player.player_id]
            if player.role.value == "GK":
                y = base_y + rng.uniform(-1, 1)
                x = base_x + rng.uniform(-2, 2)
            else:
                y = base_y + direction * (advance + line_shift) + rng.uniform(-3, 3)
                x = base_x + rng.uniform(-4, 4)
            positions.append(
                PlayerPosition(
                    player_id=player.player_id,
                    team_id=team_id,
                    x=_clamp(x, 0, 100),
                    y=_clamp(y, 0, 100),
                )
            )

    focus = state.teams[possessing_id].team.tactics.attack_focus.value
    if focus != "middle":
        shift = -12 if focus == "left" else 12
        for position in positions:
            if position.team_id == possessing_id:
                position.x = _clamp(position.x + shift, 0, 100)
    possessing_side = state.teams[possessing_id].team.side
    ball = _ball_position(positions, possessing_id, possessing_side, main_event_type, shooter)

    return Frame(
        match_id=state.match_id,
        seq=state.frame_seq,
        half=half,
        step=step,
        clock_minute=clock_minute,
        phase=MatchPhase.FIRST_HALF if half == 1 else MatchPhase.SECOND_HALF,
        state_version=state.version,
        players=positions,
        ball=ball,
        events=step_events,
    )


def _advance_for(event_type: str) -> float:
    return {"shot": 25.0, "counterattack": 18.0, "pass_sequence": 8.0, "turnover": 2.0}.get(
        event_type, 5.0
    )


def _line_shift(defensive_line: str) -> float:
    return {"low": -8.0, "medium": 0.0, "high": 10.0}[defensive_line]


def _ball_position(
    positions: list[PlayerPosition],
    possessing_id: TeamId,
    possessing_side: PitchSide,
    event_type: str,
    shooter,
) -> BallPosition:
    if event_type == "shot" and shooter is not None:
        carrier_id = shooter.player_id
    else:
        possessing_positions = [p for p in positions if p.team_id == possessing_id]
        sign = 1 if possessing_side == PitchSide.TOP else -1
        carrier = max(possessing_positions, key=lambda p: sign * p.y)
        carrier_id = carrier.player_id

    carrier_pos = next(p for p in positions if p.player_id == carrier_id)
    return BallPosition(x=carrier_pos.x, y=carrier_pos.y, owner_player_id=carrier_id)


def _finalize_possession_stats(state: _SimState, total_steps: int) -> None:
    for team_id, runtime in state.teams.items():
        pct = 100 * runtime.possession_steps / total_steps if total_steps else 0.0
        stats = state.stats[team_id]
        state.stats[team_id] = stats.model_copy(update={"possession_pct": round(pct, 1)})


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
