import pytest

from app.data.metrica import attacking_right, to_on_pitch_events
from app.data.style_profile import StyleProfile, finalize_profiles
from app.data.tactical_style import (
    DIMENSION_NAMES,
    DIMENSIONS,
    OnPitchEvent,
    cosine,
    percentile_ranks,
    style_query_vector,
    tactical_features,
    tertile,
)
from app.schemas import ObservedTactics


def ev(team, kind, t, x, y=34.0, end_x=None, end_y=None):
    return OnPitchEvent(team, kind, t, x, y, end_x, end_y)


# --- tactical_features ---------------------------------------------------------


def test_possession_time_is_credited_until_the_next_on_ball_event_and_capped():
    events = [
        ev("A", "pass", 0, 30),
        ev("A", "pass", 4, 40),  # A credited 4 s
        ev("B", "pass", 40, 30),  # A credited 15 s (36 s gap capped)
        ev("B", "pass", 46, 40),  # B credited 6 s
    ]
    # A: 2 passes over 19 s of possession
    assert tactical_features(events, "A")["passes_per_possession_min"] == round(2 / (19 / 60), 2)


def test_press_rate_counts_high_regains_per_opponent_buildup_pass():
    events = [
        ev("B", "pass", 0, 20),  # build-up (x < 63 in B's frame)
        ev("B", "pass", 1, 50),  # build-up
        ev("B", "pass", 2, 80),  # not build-up
        ev("A", "regain", 3, 60),  # high (x > 42)
        ev("A", "regain", 4, 20),  # deep
    ]
    features = tactical_features(events, "A")
    assert features["press_rate"] == 0.5
    assert features["regain_height_m"] == 40.0


def test_final_third_entries_by_lane_and_share():
    events = [
        ev("A", "pass", 0, 60, end_x=80, end_y=5),  # left
        ev("A", "pass", 1, 60, end_x=80, end_y=60),  # right
        ev("A", "pass", 2, 60, end_x=80, end_y=34),  # middle
        ev("A", "pass", 3, 60, end_x=80, end_y=10),  # left
        ev("A", "pass", 4, 80, end_x=90, end_y=10),  # already in final third
        ev("B", "pass", 5, 60, end_x=75, end_y=34),
    ]
    f = tactical_features(events, "A")
    assert f["left_entry_share"] == 0.5
    assert f["middle_entry_share"] == 0.25
    assert f["right_entry_share"] == 0.25
    assert f["final_third_share"] == 0.8


def test_missing_evidence_is_none_not_zero():
    f = tactical_features([ev("A", "pass", 0, 30)], "A")
    assert f["press_rate"] is None
    assert f["regain_height_m"] is None
    assert f["left_entry_share"] is None


# --- cohort ranking ------------------------------------------------------------------


def test_percentiles_and_tertiles():
    assert percentile_ranks([1.0, None, 3.0, 2.0]) == [1 / 6, None, 5 / 6, 0.5]
    labels = ("low", "medium", "high")
    assert [tertile(p, labels) for p in (0.1, 0.5, 0.9, None)] == ["low", "medium", "high", None]


def profile(pid, press, formation=None):
    return StyleProfile(
        profile_id=pid,
        source="statsbomb",
        source_match_id=pid,
        team_label=pid,
        formation=formation,
        features={},
        tactical_features={
            "press_rate": press,
            "regain_height_m": press * 100,
            "passes_per_possession_min": 10.0,
            "final_third_share": 0.5,
            "left_entry_share": 0.5,
            "middle_entry_share": 0.2,
            "right_entry_share": 0.3,
        },
    )


@pytest.fixture
def cohort():
    return finalize_profiles(
        [
            profile("low_block", 0.05, "4-4-2"),
            profile("mid_block", 0.15, "4-2-3-1"),
            profile("high_press", 0.40, "4-3-3"),
        ]
    )


def test_labels_are_relative_to_the_set(cohort):
    assert [p.tactics["pressing"] for p in cohort] == ["low", "medium", "high"]
    assert cohort[2].tactics["formation"] == "4-3-3"
    assert cohort[0].tactics["attack_focus"] == "left"
    assert "high press" in cohort[2].summary
    assert "50% of final-third entries" in cohort[0].summary


def test_each_source_is_ranked_on_its_own():
    from dataclasses import replace

    statsbomb = [profile("sb_low", 0.05), profile("sb_high", 0.40)]
    # Metrica logs more recoveries, so its raw press rates are all higher.
    metrica = [replace(profile(f"m_{i}", r), source="metrica") for i, r in enumerate((0.6, 0.9))]
    out = {p.profile_id: p.tactics["pressing"] for p in finalize_profiles(statsbomb + metrica)}
    assert out == {"sb_low": "low", "sb_high": "high", "m_0": "low", "m_1": "high"}


def test_unsupported_formation_has_no_formation_dims():
    [p] = finalize_profiles([profile("x", 0.1, "3-5-2")])
    assert p.tactics["formation"] is None
    assert p.formation == "3-5-2"
    assert all(v == 0.0 for v in p.style_vector[6:])


# --- scout query -----------------------------------------------------------------------


def test_query_vector_has_the_index_dimensions():
    vector = style_query_vector(ObservedTactics(pressing="high"))
    assert len(vector) == DIMENSIONS == len(DIMENSION_NAMES)


def test_nothing_known_means_no_query():
    assert style_query_vector(ObservedTactics()) is None


def test_high_press_query_ranks_the_high_press_profile_first(cohort):
    query = style_query_vector(
        ObservedTactics(formation="4-3-3", pressing="high", defensive_line="high")
    )
    ranked = sorted(cohort, key=lambda p: cosine(query, p.style_vector), reverse=True)
    assert [p.profile_id for p in ranked] == ["high_press", "mid_block", "low_block"]


def test_low_block_query_ranks_the_low_block_profile_first(cohort):
    query = style_query_vector(ObservedTactics(pressing="low", defensive_line="low"))
    best = max(cohort, key=lambda p: cosine(query, p.style_vector))
    assert best.profile_id == "low_block"


# --- Metrica orientation -----------------------------------------------------------------------


def row(team, kind, period, x, y, ex="", ey="", t="0"):
    return {
        "Team": team,
        "Type": kind,
        "Period": period,
        "Start Time [s]": t,
        "Start X": str(x),
        "Start Y": str(y),
        "End X": str(ex),
        "End Y": str(ey),
    }


def test_attacking_direction_comes_from_shots_and_flips_at_halftime():
    rows = [
        row("Home", "SHOT", "1", 0.9, 0.5),
        row("Away", "SHOT", "2", 0.9, 0.5),
    ]
    direction = attacking_right(rows)
    assert direction[("Home", "1")] is True
    assert direction[("Away", "1")] is False  # opposite of Home in period 1
    assert direction[("Away", "2")] is True
    assert direction[("Home", "2")] is False  # opposite of Away in period 2


def test_team_attacking_left_is_rotated_into_its_own_frame():
    rows = [
        row("Away", "SHOT", "1", 0.1, 0.5),  # Away attacks left in period 1
        row("Away", "PASS", "1", 0.8, 0.2, ex=0.6, ey=0.1),
    ]
    shot, pass_ = to_on_pitch_events(rows)
    assert shot.x == pytest.approx(0.9 * 105)
    assert (pass_.x, pass_.y) == (pytest.approx(0.2 * 105), pytest.approx(0.8 * 68))
    assert (pass_.end_x, pass_.end_y) == (pytest.approx(0.4 * 105), pytest.approx(0.9 * 68))


def test_out_of_range_metrica_coordinates_are_skipped():
    rows = [row("Home", "SHOT", "1", 0.9, 0.5), row("Home", "PASS", "1", "NaN", 0.5)]
    assert [e.kind for e in to_on_pitch_events(rows)] == ["shot"]
