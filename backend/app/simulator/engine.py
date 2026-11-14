"""Seeded, simplified tactical match simulator (PRD §5). Not a realistic model.

The simulator owns match truth: clock, score, events, frames, stamina and
tactics. Each step's randomness comes from `Random(f"{seed}:{half}:{step}")`,
so the same seed and the same halftime plans always replay identically, and a
step never depends on how many random numbers earlier steps drew.

Tactical effects (all from the possessing team A's view, defending team B):
- B pressing high: more A turnovers in A's own half, faster B stamina loss.
- A defensive line high: A's turnovers turn into B counterattacks more often.
- A mentality attacking / tempo fast: more chances, but more turnovers.
- B mentality defensive: fewer A chances, and B creates less itself.
- A attack focus: the lane A attacks through and the players involved.
- Fatigue: lower stamina scales every skill down.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.schemas import (
    BallPosition,
    EventType,
    Frame,
    Level,
    MatchEvent,
    MatchPhase,
    MatchState,
    Mentality,
    PlayerPosition,
    Score,
    TacticalSettings,
    Team,
    TeamId,
    TeamStats,
    Tempo,
)

from .roster import default_teams
from .shape import FOCUS_LANE, line_of, team_positions, to_pitch

FRAMES_PER_STEP = 3
MINUTES_PER_HALF = 45

PRESS_TURNOVER = {Level.LOW: -0.07, Level.MEDIUM: 0.0, Level.HIGH: 0.10}
TEMPO_TURNOVER = {Tempo.SLOW: -0.04, Tempo.NORMAL: 0.0, Tempo.FAST: 0.05}
TEMPO_ADVANCE = {Tempo.SLOW: 9.0, Tempo.NORMAL: 14.0, Tempo.FAST: 19.0}
MENTALITY_CHANCE = {Mentality.DEFENSIVE: -0.07, Mentality.BALANCED: 0.0, Mentality.ATTACKING: 0.08}
DEFENDING_MENTALITY_CHANCE = {
    Mentality.DEFENSIVE: -0.06,
    Mentality.BALANCED: 0.0,
    Mentality.ATTACKING: 0.04,
}
COUNTER_CHANCE = {Level.LOW: 0.10, Level.MEDIUM: 0.20, Level.HIGH: 0.38}
STAMINA_PRESS = {Level.LOW: 0.0, Level.MEDIUM: 0.002, Level.HIGH: 0.005}
STAMINA_TEMPO = {Tempo.SLOW: 0.0, Tempo.NORMAL: 0.001, Tempo.FAST: 0.003}


class SimulatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class StepOutput:
    events: list[MatchEvent]
    frames: list[Frame]
    state: MatchState


@dataclass(frozen=True)
class ApplyResult:
    action_id: str
    team_id: TeamId
    applied: bool
    state_version: int
    tactics: TacticalSettings
    reason: str | None = None


@dataclass
class _Runtime:
    possession: TeamId = TeamId.BLUE
    ball_depth: float = 35.0  # in the possessing team's frame
    ball_lateral: float = 50.0
    possession_steps: dict[TeamId, int] = field(
        default_factory=lambda: {TeamId.BLUE: 0, TeamId.RED: 0}
    )
    seq: int = 0
    event_count: int = 0


def rival(team_id: TeamId) -> TeamId:
    return TeamId.RED if team_id == TeamId.BLUE else TeamId.BLUE


def new_match_state(match_id: str, seed: int, steps_per_half: int = 20) -> MatchState:
    now = datetime.now(UTC)
    return MatchState(
        match_id=match_id,
        seed=seed,
        phase=MatchPhase.NOT_STARTED,
        steps_per_half=steps_per_half,
        score=Score(),
        stats={TeamId.BLUE: TeamStats(), TeamId.RED: TeamStats()},
        teams=default_teams(),
        state_version=0,
        created_at=now,
        updated_at=now,
    )


class MatchSimulator:
    """One match. Not thread-safe; the match runner serializes calls."""

    def __init__(self, state: MatchState) -> None:
        self._state = state.model_copy(deep=True)
        self._rt = _Runtime()
        self._applied: dict[str, ApplyResult] = {}
        self._pending_events: list[MatchEvent] = []

    # --- read ------------------------------------------------------------------

    @property
    def state(self) -> MatchState:
        return self._state.model_copy(deep=True)

    def team(self, team_id: TeamId) -> Team:
        return next(t for t in self._state.teams if t.team_id == team_id)

    def action_result(self, action_id: str) -> ApplyResult | None:
        """Authoritative answer to "did this action happen?" for reconciliation."""
        return self._applied.get(action_id)

    # --- transitions -----------------------------------------------------------------

    def step(self) -> StepOutput:
        s = self._state
        if s.phase is MatchPhase.NOT_STARTED:
            s.phase, s.half, s.step = MatchPhase.FIRST_HALF, 1, 0
        elif s.phase in (MatchPhase.HALFTIME, MatchPhase.FULL_TIME):
            raise SimulatorError(f"cannot step during {s.phase.value}")

        rng = random.Random(f"{s.seed}:{s.half}:{s.step}")
        events, owners = self._play_step(rng)
        s.step += 1
        s.clock_minute = (s.half - 1) * MINUTES_PER_HALF + round(
            s.step * MINUTES_PER_HALF / s.steps_per_half
        )
        self._drain_stamina()
        self._update_possession_pct()

        if s.step >= s.steps_per_half:
            if s.half == 1:
                s.phase = MatchPhase.HALFTIME
                events.append(self._event(EventType.HALF_TIME, None, [], {}))
            else:
                s.phase = MatchPhase.FULL_TIME
                events.append(self._event(EventType.FULL_TIME, None, [], {}))

        s.state_version += 1
        s.updated_at = datetime.now(UTC)
        frames = self._frames(rng, owners, events)
        return StepOutput(events=events, frames=frames, state=self.state)

    def start_second_half(self) -> MatchState:
        s = self._state
        if s.phase is not MatchPhase.HALFTIME:
            raise SimulatorError("second half starts only from halftime")
        s.phase, s.half, s.step = MatchPhase.SECOND_HALF, 2, 0
        self._rt.possession, self._rt.ball_depth, self._rt.ball_lateral = TeamId.RED, 35.0, 50.0
        s.state_version += 1
        s.updated_at = datetime.now(UTC)
        return self.state

    def apply_tactics(
        self,
        action_id: str,
        team_id: TeamId,
        tactics: TacticalSettings,
        expected_state_version: int,
    ) -> ApplyResult:
        """Idempotent: a repeated action_id returns the original result unchanged."""
        if action_id in self._applied:
            return self._applied[action_id]
        s = self._state
        team = self.team(TeamId(team_id))
        if s.phase is not MatchPhase.HALFTIME:
            return self._record(action_id, team, False, "tactics change only at halftime")
        if expected_state_version > s.state_version:
            return self._record(action_id, team, False, "expected state version is in the future")
        previous = team.tactics
        team.tactics = tactics.model_copy()
        s.state_version += 1
        s.updated_at = datetime.now(UTC)
        self._pending_events.append(
            self._event(
                EventType.TACTICAL_CHANGE,
                team.team_id,
                [],
                {
                    "action_id": action_id,
                    "from": previous.model_dump(mode="json"),
                    "to": tactics.model_dump(mode="json"),
                },
                half=2,
                step=0,
            )
        )
        return self._record(action_id, team, True, None)

    def drain_pending_events(self) -> list[MatchEvent]:
        """Events produced outside a step (tactical changes at halftime)."""
        events, self._pending_events = self._pending_events, []
        return events

    def _record(self, action_id: str, team: Team, applied: bool, reason: str | None) -> ApplyResult:
        result = ApplyResult(
            action_id=action_id,
            team_id=team.team_id,
            applied=applied,
            state_version=self._state.state_version,
            tactics=team.tactics.model_copy(),
            reason=reason,
        )
        self._applied[action_id] = result
        return result

    # --- one step of play ---------------------------------------------------------------

    def _skill(self, team: Team, index: int, name: str) -> float:
        player = team.players[index]
        return getattr(player.skills, name) * (0.75 + 0.25 * player.stamina)

    def _indices(self, team: Team, line: int) -> list[int]:
        return [
            i
            for i in range(len(team.players))
            if line_of(team.tactics.formation, i) == line and team.players[i].available
        ]

    def _pick(self, rng: random.Random, team: Team, lines: tuple[int, ...]) -> int:
        pool = [i for line in lines for i in self._indices(team, line)]
        return rng.choice(pool or [1])

    def _play_step(self, rng: random.Random) -> tuple[list[MatchEvent], list[tuple[TeamId, int]]]:
        rt, s = self._rt, self._state
        a, b = self.team(rt.possession), self.team(rival(rt.possession))
        ta, tb = a.tactics, b.tactics
        rt.possession_steps[a.team_id] += 1
        events: list[MatchEvent] = []

        zone = rt.ball_depth
        lines = (1, 2) if zone < 40 else (2, 3) if zone < 70 else (2, 3)
        passer = self._pick(rng, a, lines)
        rt.ball_lateral = FOCUS_LANE[ta.attack_focus] + rng.uniform(-12, 12)
        owners = [(a.team_id, passer)]

        press = PRESS_TURNOVER[tb.pressing] * (1.0 if zone < 60 else 0.5)
        press *= sum(p.stamina for p in b.players) / len(b.players)
        skill_gap = (self._skill(b, 3, "defending") - self._skill(a, passer, "passing")) / 400
        turnover_p = 0.20 + press + TEMPO_TURNOVER[ta.tempo] + skill_gap

        if rng.random() < turnover_p:
            winner = self._pick(rng, b, (2, 3) if zone < 50 else (1, 2))
            kind = (
                EventType.PRESSING_SUCCESS
                if tb.pressing is Level.HIGH and zone < 55
                else EventType.TURNOVER
            )
            events.append(
                self._event(
                    kind, b.team_id, [a.players[passer].player_id, b.players[winner].player_id], {}
                )
            )
            s.stats[a.team_id].turnovers += 1
            if kind is EventType.PRESSING_SUCCESS:
                s.stats[b.team_id].pressing_successes += 1
            owners.append((b.team_id, winner))
            rt.possession, rt.ball_depth = b.team_id, 100 - zone
            if rng.random() < COUNTER_CHANCE[ta.defensive_line]:
                runner = self._pick(rng, b, (3,))
                events.append(
                    self._event(
                        EventType.COUNTERATTACK,
                        b.team_id,
                        [b.players[winner].player_id, b.players[runner].player_id],
                        {"against_line": ta.defensive_line.value},
                    )
                )
                owners.append((b.team_id, runner))
                rt.ball_depth = 78.0
                events += self._shot(rng, b, a, runner, bonus=0.08, owners=owners)
            return events, owners

        receiver = self._pick(rng, a, (2, 3))
        finisher = self._pick(rng, a, (3,))
        zone = min(92.0, zone + TEMPO_ADVANCE[ta.tempo] + rng.uniform(-4, 6))
        events.append(
            self._event(
                EventType.PASS_SEQUENCE,
                a.team_id,
                [
                    a.players[passer].player_id,
                    a.players[receiver].player_id,
                    a.players[finisher].player_id,
                ],
                {"lane": ta.attack_focus.value, "tempo": ta.tempo.value},
            )
        )
        owners += [(a.team_id, receiver), (a.team_id, finisher)]
        rt.ball_depth = zone

        if rng.random() < 0.05:
            fouler = self._pick(rng, b, (1, 2))
            events.append(self._event(EventType.FOUL, b.team_id, [b.players[fouler].player_id], {}))

        if zone >= 58:
            chance_p = (
                0.50
                + MENTALITY_CHANCE[ta.mentality]
                + DEFENDING_MENTALITY_CHANCE[tb.mentality]
                + (0.04 if tb.defensive_line is Level.HIGH else 0.0)
                + (self._skill(a, finisher, "shooting") - self._skill(b, 2, "defending")) / 400
            )
            if rng.random() < chance_p:
                events += self._shot(rng, a, b, finisher, bonus=0.0, owners=owners)
                return events, owners

        if rng.random() < 0.45:
            events.append(self._event(EventType.POSSESSION_CHANGE, b.team_id, [], {}))
            rt.possession, rt.ball_depth = b.team_id, 100 - zone
        else:
            rt.ball_depth = max(45.0, zone - 15)
        return events, owners

    def _shot(
        self,
        rng: random.Random,
        a: Team,
        b: Team,
        shooter: int,
        *,
        bonus: float,
        owners: list[tuple[TeamId, int]],
    ) -> list[MatchEvent]:
        s, rt = self._state, self._rt
        depth = rt.ball_depth
        xg = 0.12 + 0.14 * max(0.0, depth - 58) / 34 + bonus
        xg += (self._skill(a, shooter, "shooting") - b.players[0].skills.goalkeeping) / 500
        xg = round(min(0.55, max(0.03, xg)), 3)
        shooter_id = a.players[shooter].player_id
        on_target = rng.random() < 0.40 + xg
        events = [
            self._event(EventType.SHOT, a.team_id, [shooter_id], {"xg": xg, "on_target": on_target})
        ]
        s.stats[a.team_id].shots += 1
        if on_target:
            s.stats[a.team_id].shots_on_target += 1
        if on_target and rng.random() < xg / (0.40 + xg):
            if a.team_id is TeamId.BLUE:
                s.score.blue += 1
            else:
                s.score.red += 1
            events.append(self._event(EventType.GOAL, a.team_id, [shooter_id], {"xg": xg}))
            rt.possession, rt.ball_depth = b.team_id, 50.0
        else:
            if on_target:
                events.append(self._event(EventType.SAVE, b.team_id, [b.players[0].player_id], {}))
            owners.append((b.team_id, 0))
            rt.possession, rt.ball_depth = b.team_id, 8.0
        return events

    def _drain_stamina(self) -> None:
        for team in self._state.teams:
            t = team.tactics
            drain = 0.004 + STAMINA_PRESS[t.pressing] + STAMINA_TEMPO[t.tempo]
            drain += 0.002 if t.mentality is Mentality.ATTACKING else 0.0
            for i, player in enumerate(team.players):
                rate = drain * (0.3 if i == 0 else 1.0)
                player.stamina = round(max(0.3, player.stamina - rate), 4)

    def _update_possession_pct(self) -> None:
        steps = self._rt.possession_steps
        total = sum(steps.values()) or 1
        for team_id, n in steps.items():
            self._state.stats[team_id].possession_pct = round(100 * n / total, 1)

    # --- output ---------------------------------------------------------------------------

    def _event(
        self,
        kind: EventType,
        team_id: TeamId | None,
        player_ids: list[str],
        details: dict,
        *,
        half: int | None = None,
        step: int | None = None,
    ) -> MatchEvent:
        s = self._state
        self._rt.event_count += 1
        return MatchEvent(
            event_id=f"{s.match_id}:e{self._rt.event_count:04d}",
            match_id=s.match_id,
            half=half if half is not None else s.half or 1,
            step=step if step is not None else s.step,
            clock_minute=s.clock_minute,
            team_id=team_id,
            type=kind,
            player_ids=player_ids,
            details=details,
            created_at=datetime.now(UTC),
        )

    def _frames(
        self, rng: random.Random, owners: list[tuple[TeamId, int]], events: list[MatchEvent]
    ) -> list[Frame]:
        s, rt = self._state, self._rt
        # Spread the step's ball owners over the frames; events land on the last.
        picks = [
            owners[min(len(owners) - 1, round(i * (len(owners) - 1) / 2))]
            for i in range(FRAMES_PER_STEP)
        ]
        frames = []
        for i, (owner_team, owner_index) in enumerate(picks):
            positions: list[PlayerPosition] = []
            screen: dict[str, tuple[float, float]] = {}
            for team in s.teams:
                in_possession = team.team_id == owner_team
                depth = rt.ball_depth if in_possession else 100 - rt.ball_depth
                lateral = rt.ball_lateral if in_possession else 100 - rt.ball_lateral
                own = team_positions(
                    team.tactics,
                    [p.player_id for p in team.players],
                    in_possession=in_possession,
                    ball_depth=depth,
                    ball_lateral=lateral,
                    rng=rng,
                )
                for pid, (d, w) in own.items():
                    x, y = to_pitch(team.side, d, w)
                    screen[pid] = (x, y)
                    positions.append(PlayerPosition(player_id=pid, team_id=team.team_id, x=x, y=y))
            owner_id = self.team(owner_team).players[owner_index].player_id
            bx, by = screen[owner_id]
            if i == FRAMES_PER_STEP - 1 and any(e.type is EventType.GOAL for e in events):
                scorer_team = next(e.team_id for e in events if e.type is EventType.GOAL)
                by = 99.0 if self.team(scorer_team).side.value == "top" else 1.0
                bx, owner_id = 50.0, None
            frames.append(
                Frame(
                    match_id=s.match_id,
                    seq=rt.seq,
                    half=s.half or 1,
                    step=max(0, s.step - 1),
                    clock_minute=s.clock_minute,
                    phase=s.phase,
                    state_version=s.state_version,
                    players=positions,
                    ball=BallPosition(x=bx, y=by, owner_player_id=owner_id),
                    events=events if i == FRAMES_PER_STEP - 1 else [],
                )
            )
            rt.seq += 1
        return frames


def simulate_match(
    match_id: str,
    seed: int,
    steps_per_half: int = 20,
    plans: dict[TeamId, TacticalSettings] | None = None,
) -> tuple[MatchState, list[MatchEvent], list[Frame]]:
    """Run a whole match without coaches; optional halftime plans per team."""
    sim = MatchSimulator(new_match_state(match_id, seed, steps_per_half))
    events: list[MatchEvent] = []
    frames: list[Frame] = []
    while sim.state.phase is not MatchPhase.FULL_TIME:
        if sim.state.phase is MatchPhase.HALFTIME:
            for team_id, tactics in (plans or {}).items():
                sim.apply_tactics(
                    f"{match_id}:{team_id.value}:halftime",
                    team_id,
                    tactics,
                    sim.state.state_version,
                )
            events += sim.drain_pending_events()
            sim.start_second_half()
            continue
        out = sim.step()
        events += out.events
        frames += out.frames
    return sim.state, events, frames
