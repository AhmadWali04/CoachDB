from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    Frame,
    MatchState,
    TacticalPlan,
)

NOW = datetime.now(UTC).isoformat()


def plan_payload(**overrides):
    payload = {
        "match_id": "match_001",
        "team_id": "blue",
        "based_on_state_version": 12,
        "plan": {
            "formation": "4-2-3-1",
            "mentality": "attacking",
            "pressing": "high",
            "defensive_line": "medium",
            "attack_focus": "left",
            "tempo": "fast",
        },
        "opponent_prediction": {
            "likely_change": "lower defensive line",
            "confidence": 0.72,
            "evidence": ["event_014"],
        },
        "primary_objective": "Create more chances down the left.",
        "rationale": "Left channel produced most entries.",
        "voice_script": "We have found space down the left.",
    }
    payload.update(overrides)
    return payload


def team(team_id, side):
    return {
        "team_id": team_id,
        "name": team_id.title(),
        "coach_id": f"coach_{team_id}",
        "coach_name": f"Coach {team_id.title()}",
        "side": side,
        "tactics": plan_payload()["plan"],
        "players": [],
    }


def match_payload(**overrides):
    payload = {
        "match_id": "match_001",
        "seed": 42,
        "phase": "first_half",
        "half": 1,
        "score": {"blue": 0, "red": 0},
        "stats": {"blue": {}, "red": {}},
        "teams": [team("blue", "top"), team("red", "bottom")],
        "state_version": 0,
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(overrides)
    return payload


def test_valid_plan_parses():
    assert TacticalPlan.model_validate(plan_payload()).plan.formation == "4-2-3-1"


def test_invalid_tactical_enum_is_rejected():
    bad = plan_payload()
    bad["plan"]["formation"] = "3-5-2"
    with pytest.raises(ValidationError):
        TacticalPlan.model_validate(bad)


def test_unknown_field_is_rejected_not_ignored():
    with pytest.raises(ValidationError):
        TacticalPlan.model_validate(plan_payload(substitute_everyone=True))


@pytest.mark.parametrize("confidence", [-0.1, 1.01])
def test_confidence_out_of_range_is_rejected(confidence):
    bad = plan_payload()
    bad["opponent_prediction"]["confidence"] = confidence
    with pytest.raises(ValidationError):
        TacticalPlan.model_validate(bad)


def test_prediction_requires_evidence():
    bad = plan_payload()
    bad["opponent_prediction"]["evidence"] = []
    with pytest.raises(ValidationError):
        TacticalPlan.model_validate(bad)


def test_match_requires_opposite_sides():
    MatchState.model_validate(match_payload())
    with pytest.raises(ValidationError):
        MatchState.model_validate(match_payload(teams=[team("blue", "top"), team("red", "top")]))


def frame_payload(x=50.0):
    return {
        "match_id": "match_001",
        "seq": 0,
        "half": 1,
        "step": 0,
        "clock_minute": 0,
        "phase": "first_half",
        "state_version": 0,
        "players": [{"player_id": "blue_9", "team_id": "blue", "x": x, "y": 40.0}],
        "ball": {"x": 50.0, "y": 50.0, "owner_player_id": "blue_9"},
    }


def test_frame_parses():
    assert Frame.model_validate(frame_payload()).ball.owner_player_id == "blue_9"


@pytest.mark.parametrize("x", [-1.0, 100.5])
def test_frame_coordinates_must_be_on_pitch(x):
    with pytest.raises(ValidationError):
        Frame.model_validate(frame_payload(x=x))
