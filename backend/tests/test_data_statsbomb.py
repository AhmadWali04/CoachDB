from app.data.statsbomb import parse_statsbomb_events, team_ids_and_names

BLUE = {"id": 1, "name": "Blue"}
RED = {"id": 2, "name": "Red"}


def event(overrides: dict | None = None) -> dict:
    base = {
        "type": {"name": "Pass"},
        "team": BLUE,
        "possession_team": BLUE,
        "possession": 1,
    }
    base.update(overrides or {})
    return base


def test_team_ids_and_names_collects_every_team_seen():
    events = [event({"team": BLUE}), event({"team": RED})]
    assert team_ids_and_names(events) == {1: "Blue", 2: "Red"}


def test_extracts_formation_from_starting_xi():
    events = [event({"type": {"name": "Starting XI"}, "tactics": {"formation": 4231}})]
    profile = parse_statsbomb_events(events, match_id=99, team_id=1)
    assert profile is not None
    assert profile.formation == "4-2-3-1"


def test_pass_completion_and_long_pass_ratio():
    events = [
        event({"pass": {"length": 10.0}}),  # complete, short
        event({"pass": {"length": 40.0}}),  # complete, long
        event({"pass": {"length": 5.0, "outcome": {"name": "Incomplete"}}}),  # incomplete
    ]
    profile = parse_statsbomb_events(events, match_id=99, team_id=1)
    assert profile is not None
    assert profile.features["pass_completion_rate"] == round(2 / 3, 3)
    assert profile.features["long_pass_ratio"] == round(1 / 3, 3)


def test_possession_pct_only_counts_this_teams_share():
    events = [
        event({"possession": 1, "possession_team": BLUE}),
        event({"possession": 1, "possession_team": BLUE}),
        event({"possession": 2, "possession_team": RED}),
    ]
    profile = parse_statsbomb_events(events, match_id=99, team_id=1)
    assert profile is not None
    assert profile.features["possession_pct"] == round(2 / 3 * 100, 2)


def test_shots_and_xg_are_summed_for_the_requested_team_only():
    events = [
        event({"type": {"name": "Shot"}, "team": BLUE, "shot": {"statsbomb_xg": 0.2}}),
        event(
            {
                "type": {"name": "Shot"},
                "team": RED,
                "shot": {"statsbomb_xg": 0.9},
                "possession_team": RED,
            }
        ),
    ]
    profile = parse_statsbomb_events(events, match_id=99, team_id=1)
    assert profile is not None
    assert profile.features["shots_per_match"] == 1.0
    assert profile.features["xg_per_match"] == 0.2


def test_tags_are_derived_not_hardcoded():
    events = [event({"possession": 1, "possession_team": BLUE}) for _ in range(10)]
    profile = parse_statsbomb_events(events, match_id=99, team_id=1)
    assert profile is not None
    assert profile.features["possession_pct"] == 100.0
    assert "possession-heavy" in profile.tags


def test_returns_none_for_a_team_with_no_events():
    events = [event({"team": RED, "possession_team": RED})]
    assert parse_statsbomb_events(events, match_id=99, team_id=1) is None


def test_profile_embedding_matches_feature_order():
    from app.data.style_profile import FEATURE_NAMES

    events = [event()]
    profile = parse_statsbomb_events(events, match_id=99, team_id=1)
    assert profile is not None
    assert profile.embedding == [profile.features[name] for name in FEATURE_NAMES]
