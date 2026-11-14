from app.schemas import TacticalSettings
from app.simulator import run_match


def tactics(**overrides) -> TacticalSettings:
    base = {
        "formation": "4-3-3",
        "mentality": "balanced",
        "pressing": "medium",
        "defensive_line": "medium",
        "attack_focus": "middle",
        "tempo": "normal",
    }
    base.update(overrides)
    return TacticalSettings.model_validate(base)


def play(seed=42, steps_per_half=20, **kwargs):
    return run_match(
        "match_test",
        seed,
        tactics(),
        tactics(),
        steps_per_half=steps_per_half,
        **kwargs,
    )


def _without_timestamps(event):
    return event.model_dump(exclude={"created_at"})


def _frame_without_timestamps(frame):
    return frame.model_dump(exclude={"events": {"__all__": {"created_at"}}})


def test_same_seed_gives_identical_output():
    a = play(seed=7)
    b = play(seed=7)

    assert [_without_timestamps(e) for e in a.events] == [_without_timestamps(e) for e in b.events]
    assert [_frame_without_timestamps(f) for f in a.frames] == [
        _frame_without_timestamps(f) for f in b.frames
    ]
    assert a.final_state.model_dump(
        exclude={"created_at", "updated_at"}
    ) == b.final_state.model_dump(exclude={"created_at", "updated_at"})


def test_different_seeds_can_diverge():
    a = play(seed=1)
    b = play(seed=2)
    assert [_without_timestamps(e) for e in a.events] != [_without_timestamps(e) for e in b.events]


def test_emits_exactly_one_half_time_and_one_full_time_event():
    result = play()
    types = [e.type.value for e in result.events]
    assert types.count("half_time") == 1
    assert types.count("full_time") == 1
    # half_time must come before full_time
    assert types.index("half_time") < types.index("full_time")


def test_frame_count_matches_two_halves_of_steps():
    result = play(steps_per_half=15)
    assert len(result.frames) == 2 * 15


def test_frame_positions_and_ball_stay_on_the_pitch():
    result = play()
    for frame in result.frames:
        for player in frame.players:
            assert 0 <= player.x <= 100
            assert 0 <= player.y <= 100
        assert 0 <= frame.ball.x <= 100
        assert 0 <= frame.ball.y <= 100


def test_every_goal_event_has_a_matching_score_increment():
    result = play(steps_per_half=30)
    goals = [e for e in result.events if e.type.value == "goal"]
    total_goals_scored = sum(1 for e in goals)
    assert result.final_state.score.blue + result.final_state.score.red == total_goals_scored


def test_high_pressing_defense_forces_more_turnovers_than_low_pressing():
    seeds = range(10)
    high_press_turnovers = 0
    low_press_turnovers = 0

    for seed in seeds:
        high = run_match("m", seed, tactics(), tactics(pressing="high"), steps_per_half=20)
        low = run_match("m", seed, tactics(), tactics(pressing="low"), steps_per_half=20)
        high_press_turnovers += sum(
            1 for e in high.events if e.type.value == "turnover" and e.team_id == "blue"
        )
        low_press_turnovers += sum(
            1 for e in low.events if e.type.value == "turnover" and e.team_id == "blue"
        )

    assert high_press_turnovers > low_press_turnovers


def test_attacking_mentality_increases_shot_volume_over_defensive():
    seeds = range(10)
    attacking_shots = 0
    defensive_shots = 0

    for seed in seeds:
        attacking = run_match(
            "m", seed, tactics(mentality="attacking"), tactics(), steps_per_half=20
        )
        defensive = run_match(
            "m", seed, tactics(mentality="defensive"), tactics(), steps_per_half=20
        )
        attacking_shots += sum(
            1 for e in attacking.events if e.type.value == "shot" and e.team_id == "blue"
        )
        defensive_shots += sum(
            1 for e in defensive.events if e.type.value == "shot" and e.team_id == "blue"
        )

    assert attacking_shots > defensive_shots


def test_second_half_tactics_are_applied_at_halftime():
    from app.schemas import TeamId

    result = run_match(
        "match_test",
        seed=3,
        blue_tactics=tactics(formation="4-4-2"),
        red_tactics=tactics(),
        steps_per_half=10,
        second_half_tactics={TeamId.BLUE: tactics(formation="4-2-3-1")},
    )
    blue_team = next(t for t in result.final_state.teams if t.team_id == "blue")
    assert blue_team.tactics.formation.value == "4-2-3-1"

    first_half_frames = [f for f in result.frames if f.half == 1]
    second_half_frames = [f for f in result.frames if f.half == 2]
    assert len(first_half_frames) == 10
    assert len(second_half_frames) == 10


def test_stamina_decreases_over_the_match():
    result = play(steps_per_half=20)
    blue_team = next(t for t in result.final_state.teams if t.team_id == "blue")
    outfield = [p for p in blue_team.players if p.role.value != "GK"]
    assert all(p.stamina < 1.0 for p in outfield)


def test_match_id_and_seed_propagate():
    result = play(seed=99)
    assert result.seed == 99
    assert result.final_state.seed == 99
    assert result.final_state.match_id == "match_test"
    assert all(e.match_id == "match_test" for e in result.events)
    assert all(f.match_id == "match_test" for f in result.frames)
