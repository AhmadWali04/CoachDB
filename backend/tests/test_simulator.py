from statistics import mean

import pytest

from app.schemas import EventType, Frame, Level, MatchPhase, Mentality, PitchSide, TeamId, Tempo
from app.simulator import (
    FRAMES_PER_STEP,
    MatchSimulator,
    SimulatorError,
    new_match_state,
    simulate_match,
)
from app.simulator.roster import DEFAULT_TACTICS
from app.simulator.shape import to_pitch


def fingerprint(result):
    state, events, frames = result
    return (
        state.score,
        [(e.event_id, e.type, tuple(e.player_ids)) for e in events],
        [(f.seq, f.ball.x, f.ball.y, tuple((p.x, p.y) for p in f.players)) for f in frames],
    )


def test_same_seed_and_plans_replay_identically():
    assert fingerprint(simulate_match("m", 42)) == fingerprint(simulate_match("m", 42))


def test_different_seeds_differ():
    assert fingerprint(simulate_match("m", 1)) != fingerprint(simulate_match("m", 2))


def test_full_match_structure():
    state, events, frames = simulate_match("m", 7, steps_per_half=20)
    assert state.phase is MatchPhase.FULL_TIME
    assert state.clock_minute == 90
    assert len(frames) == 40 * FRAMES_PER_STEP
    assert [f.seq for f in frames] == list(range(len(frames)))
    types = [e.type for e in events]
    assert types.count(EventType.HALF_TIME) == 1 and types[-1] is EventType.FULL_TIME
    goals = [e for e in events if e.type is EventType.GOAL]
    assert state.score.blue == sum(e.team_id is TeamId.BLUE for e in goals)
    assert state.score.red == sum(e.team_id is TeamId.RED for e in goals)


def test_frames_satisfy_the_contract_and_reference_real_players():
    state, _, frames = simulate_match("m", 3)
    ids = {p.player_id for t in state.teams for p in t.players}
    for frame in frames:
        Frame.model_validate(frame.model_dump())  # coordinates within 0..100
        assert {p.player_id for p in frame.players} == ids
        assert frame.ball.owner_player_id is None or frame.ball.owner_player_id in ids
        for event in frame.events:
            assert set(event.player_ids) <= ids


def test_arrow_events_name_at_least_two_players():
    _, events, _ = simulate_match("m", 11)
    for event in events:
        if event.type in (
            EventType.PASS_SEQUENCE,
            EventType.COUNTERATTACK,
            EventType.PRESSING_SUCCESS,
            EventType.TURNOVER,
        ):
            assert len(event.player_ids) >= 2


def test_top_team_attacks_toward_y_100():
    assert to_pitch(PitchSide.TOP, depth=90, lateral=50)[1] == 90
    assert to_pitch(PitchSide.BOTTOM, depth=90, lateral=50)[1] == 10
    # A top team's left touchline is screen-right.
    assert to_pitch(PitchSide.TOP, depth=50, lateral=0)[0] == 100


def test_cannot_step_at_halftime_or_change_tactics_mid_half():
    sim = MatchSimulator(new_match_state("m", 1, steps_per_half=2))
    sim.step()
    result = sim.apply_tactics("a1", TeamId.BLUE, DEFAULT_TACTICS[TeamId.RED], 0)
    assert not result.applied and "halftime" in result.reason
    sim.step()
    assert sim.state.phase is MatchPhase.HALFTIME
    with pytest.raises(SimulatorError):
        sim.step()


def test_apply_tactics_is_idempotent_by_action_id():
    sim = MatchSimulator(new_match_state("m", 1, steps_per_half=2))
    sim.step(), sim.step()
    plan = DEFAULT_TACTICS[TeamId.BLUE].model_copy(update={"pressing": Level.LOW})
    first = sim.apply_tactics("act-1", TeamId.BLUE, plan, sim.state.state_version)
    version = sim.state.state_version
    again = sim.apply_tactics("act-1", TeamId.BLUE, plan, 0)
    assert first.applied and again == first
    assert sim.state.state_version == version  # not applied twice
    assert sim.team(TeamId.BLUE).tactics.pressing is Level.LOW
    [change] = sim.drain_pending_events()
    assert change.type is EventType.TACTICAL_CHANGE and change.details["action_id"] == "act-1"
    assert sim.action_result("act-1") == first
    assert sim.action_result("never-sent") is None


def test_halftime_plan_changes_second_half_behaviour():
    aggressive = DEFAULT_TACTICS[TeamId.RED].model_copy(
        update={"pressing": Level.HIGH, "mentality": Mentality.ATTACKING, "tempo": Tempo.FAST}
    )
    base = [simulate_match(f"m{s}", s)[0] for s in range(40)]
    alt = [simulate_match(f"m{s}", s, plans={TeamId.RED: aggressive})[0] for s in range(40)]
    assert mean(x.stats[TeamId.RED].shots for x in alt) > mean(
        x.stats[TeamId.RED].shots for x in base
    )
    assert mean(x.stats[TeamId.BLUE].turnovers for x in alt) > mean(
        x.stats[TeamId.BLUE].turnovers for x in base
    )


def test_high_pressing_costs_stamina():
    state, _, _ = simulate_match("m", 5)
    blue, red = (sum(p.stamina for p in t.players) for t in state.teams)
    assert DEFAULT_TACTICS[TeamId.BLUE].pressing is Level.HIGH
    assert blue < red
