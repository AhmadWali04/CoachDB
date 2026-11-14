import random

import pytest

from app.data.metrica_tracking import (
    PossessionTimeline,
    TrackingSample,
    goalkeeper,
    infer_formation,
    parse_tracking,
    team_shape,
)
from app.data.style_profile import StyleProfile, finalize_profiles

# --- parsing ---------------------------------------------------------------------

TRACKING_CSV = """,,,Home,,Home,,,
,,,11,,1,,,
Period,Frame,Time [s],Player11,,Player1,,Ball,
1,25,1.0,0.01,0.5,0.4,0.3,0.5,0.5
1,26,1.04,0.01,0.5,0.4,0.3,0.5,0.5
1,50,2.0,0.02,0.5,NaN,NaN,0.5,0.5
"""


def test_parse_keeps_one_frame_per_second_and_drops_missing_players():
    samples = parse_tracking(TRACKING_CSV, sample_every=25)
    assert [s.frame for s in samples] == [25, 50]
    assert samples[0].players == {"Player11": (0.01, 0.5), "Player1": (0.4, 0.3)}
    assert samples[1].players == {"Player11": (0.02, 0.5)}


# --- possession ------------------------------------------------------------------


def events(*rows):
    return [{"Type": kind, "Team": team, "Start Frame": str(frame)} for kind, team, frame in rows]


def test_possession_follows_on_ball_events():
    timeline = PossessionTimeline(
        events(
            ("PASS", "Home", 100),
            ("BALL LOST", "Home", 200),  # Away has it afterwards
            ("BALL OUT", "Away", 300),
            ("SET PIECE", "Home", 400),
        )
    )
    assert timeline.owner(50) is None
    assert timeline.owner(150) == "Home"
    assert timeline.owner(250) == "Away"
    assert timeline.owner(350) is None
    assert timeline.owner(450) == "Home"


def test_possession_goes_stale_without_events():
    timeline = PossessionTimeline(events(("PASS", "Home", 0)))
    assert timeline.owner(15 * 25) == "Home"
    assert timeline.owner(15 * 25 + 1) is None


# --- formation -------------------------------------------------------------------

LINE_DEPTHS = {
    "4-4-2": (20, 40, 60),
    "4-3-3": (20, 40, 60),
    "3-5-2": (20, 40, 60),
    "4-2-3-1": (20, 33, 47, 62),
    "4-1-4-1": (20, 30, 42, 60),
}


def layout(name: str, noise: float = 1.5, seed: int = 0) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    sizes = [int(n) for n in name.split("-")]
    positions = []
    for size, depth in zip(sizes, LINE_DEPTHS[name], strict=True):
        for i in range(size):
            positions.append((depth + rng.gauss(0, noise), 68 * (i + 1) / (size + 1)))
    return positions


@pytest.mark.parametrize("name", list(LINE_DEPTHS))
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_infers_formation_from_average_positions(name, seed):
    assert infer_formation(layout(name, seed=seed)) == name


def test_needs_exactly_ten_outfield_players():
    assert infer_formation(layout("4-4-2")[:9]) is None


# --- shape -------------------------------------------------------------------------


def sample(frame, period, positions):
    return TrackingSample(period, frame, positions)


def test_goalkeeper_is_the_deepest_regular_player_in_the_teams_own_frame():
    # Period 2: team attacks left on screen, so the keeper is near x=1.
    samples = [
        sample(25, "1", {"gk": (0.02, 0.5), "a": (0.3, 0.5)}),
        sample(50, "2", {"gk": (0.98, 0.5), "a": (0.7, 0.5)}),
    ]
    assert goalkeeper(samples, {"1": True, "2": False}) == "gk"


def test_block_shape_is_measured_only_when_the_opponent_has_the_ball():
    gk = {"gk": (0.02, 0.5)}
    # 10 outfield players: deepest four at x=0.2 (21 m), spread 0.2..0.6, y 0.1..0.9
    outfield = {f"p{i}": (0.2 if i < 4 else 0.6, 0.1 + 0.08 * i) for i in range(10)}
    samples = [
        sample(25, "1", {**gk, **outfield}),  # opponent in possession
        sample(50, "1", {**gk, **{n: (0.9, y) for n, (_, y) in outfield.items()}}),  # own ball
    ]
    possession = PossessionTimeline(events(("PASS", "Away", 0), ("PASS", "Home", 40)))
    shape = team_shape(samples, "Home", {"1": True}, possession)
    assert shape.features["defensive_line_height_m"] == pytest.approx(21.0)
    assert shape.features["block_length_m"] == pytest.approx(42.0)
    assert shape.features["block_width_m"] == pytest.approx(0.72 * 68, abs=0.01)


def test_no_out_of_possession_frames_means_no_shape():
    samples = [sample(25, "1", {"gk": (0.02, 0.5)})]
    shape = team_shape(samples, "Home", {"1": True}, PossessionTimeline([]))
    assert shape.features == {
        "defensive_line_height_m": None,
        "block_length_m": None,
        "block_width_m": None,
    }
    assert shape.formation is None


# --- ranking ------------------------------------------------------------------------


def metrica_profile(pid, regain, line):
    return StyleProfile(
        profile_id=pid,
        source="metrica",
        source_match_id=pid,
        team_label=pid,
        formation="4-4-2",
        formation_source="tracking",
        features={},
        tactical_features={"regain_height_m": regain, "defensive_line_height_m": line},
    )


def test_tracked_defensive_line_is_used_when_every_profile_has_it():
    # Regain height says the opposite of the tracked line; tracking wins.
    a, b = finalize_profiles([metrica_profile("a", 50, 25), metrica_profile("b", 30, 40)])
    assert (a.tactics["defensive_line"], b.tactics["defensive_line"]) == ("low", "high")
    assert "inferred from tracking" in a.summary
