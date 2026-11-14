from datetime import UTC, datetime

import pytest

from app.guardrails import (
    GuardrailViolation,
    SealedHalftimePlans,
    build_coach_view,
    coach_namespace,
    require_own_namespace,
)
from app.schemas import MatchEvent, MatchState, TacticalPlan

from .test_schemas import match_payload, plan_payload

NOW = datetime.now(UTC).isoformat()

# Distinctive values so a leak shows up in the serialized view.
RED_SECRET_TACTICS = {
    "formation": "4-4-2",
    "mentality": "defensive",
    "pressing": "low",
    "defensive_line": "low",
    "attack_focus": "right",
    "tempo": "slow",
}


def player(team_id, n, stamina):
    return {
        "player_id": f"{team_id}_{n}",
        "team_id": team_id,
        "name": f"{team_id} {n}",
        "number": n,
        "role": "MF",
        "skills": {"passing": 70, "shooting": 60, "defending": 50, "pace": 65},
        "stamina": stamina,
    }


def halftime_state(**overrides) -> MatchState:
    payload = match_payload(phase="halftime", state_version=7, **overrides)
    payload["teams"][0]["players"] = [player("blue", 8, 0.81)]
    payload["teams"][1]["players"] = [player("red", 8, 0.37)]
    payload["teams"][1]["tactics"] = RED_SECRET_TACTICS
    return MatchState.model_validate(payload)


def event(event_id, half):
    return MatchEvent.model_validate(
        {
            "event_id": event_id,
            "match_id": "match_001",
            "half": half,
            "step": 3,
            "clock_minute": 10 if half == 1 else 50,
            "team_id": "red",
            "type": "tactical_change" if half == 2 else "shot",
            "created_at": NOW,
        }
    )


def plan(team_id, version=7) -> TacticalPlan:
    payload = plan_payload(team_id=team_id, based_on_state_version=version)
    return TacticalPlan.model_validate(payload)


# --- Coach view -----------------------------------------------------------------


def test_view_keeps_own_team_in_full():
    view = build_coach_view(halftime_state(), [], "blue")
    assert view.own_team.team_id == "blue"
    assert view.own_team.players[0].stamina == 0.81
    assert view.memory_namespace == "coach:blue"
    assert view.snapshot_state_version == 7


def test_view_shows_rival_kickoff_formation():
    view = build_coach_view(halftime_state(), [], "blue")
    assert view.rival_team.kickoff_formation == "4-4-2"


def test_view_hides_rival_tactics_and_stamina():
    view = build_coach_view(halftime_state(), [], "blue")
    assert not hasattr(view.rival_team, "tactics")
    assert not hasattr(view.rival_team.players[0], "stamina")
    assert not hasattr(view.rival_team.players[0], "skills")

    dumped = view.model_dump_json()
    for hidden in ('"defensive"', '"slow"', '"low"', '"right"'):
        assert hidden not in dumped, f"rival tactic {hidden} leaked"
    assert "0.37" not in dumped


def test_view_excludes_events_after_halftime_snapshot():
    view = build_coach_view(halftime_state(), [event("e1", 1), event("e2", 2)], "red")
    assert [e.event_id for e in view.public_events] == ["e1"]


def test_view_only_built_at_halftime():
    state = MatchState.model_validate(match_payload(phase="first_half"))
    with pytest.raises(GuardrailViolation):
        build_coach_view(state, [], "blue")


# --- Sealed plans -----------------------------------------------------------------


def test_plans_stay_sealed_until_both_submit():
    box = SealedHalftimePlans("match_001", snapshot_state_version=7)
    box.submit("blue", plan("blue"))
    with pytest.raises(GuardrailViolation):
        box.reveal()
    box.submit("red", plan("red"))
    assert set(box.reveal()) == {"blue", "red"}


def test_coach_cannot_submit_for_rival():
    box = SealedHalftimePlans("match_001", snapshot_state_version=7)
    with pytest.raises(GuardrailViolation):
        box.submit("blue", plan("red"))


def test_plan_must_use_shared_snapshot():
    box = SealedHalftimePlans("match_001", snapshot_state_version=7)
    with pytest.raises(GuardrailViolation):
        box.submit("blue", plan("blue", version=8))


def test_no_resubmission_after_sealing():
    box = SealedHalftimePlans("match_001", snapshot_state_version=7)
    box.submit("blue", plan("blue"))
    with pytest.raises(GuardrailViolation):
        box.submit("blue", plan("blue"))


# --- Memory namespaces ----------------------------------------------------------------


def test_coach_cannot_use_rival_namespace():
    assert require_own_namespace("blue", coach_namespace("blue")) == "coach:blue"
    with pytest.raises(GuardrailViolation):
        require_own_namespace("blue", coach_namespace("red"))
