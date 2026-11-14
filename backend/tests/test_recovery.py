import time
from datetime import UTC, datetime

import pytest

from app.execution import (
    ActionLedger,
    HalftimeWorkflow,
    LeaseLost,
    LeaseManager,
    MemoryCollection,
    action_id_for,
    collections_for,
    task_id_for,
)
from app.orchestration import InMemoryMatchRepository, MatchService
from app.orchestration.halftime import CoachingHalftime
from app.schemas import Action, ActionStatus, MatchPhase, TeamId

from .test_coaches import FakeLLM, ViewAwareCoach

S = ActionStatus


def coaches():
    return CoachingHalftime(
        {
            team: ViewAwareCoach(team, f"coach_{team.value}", FakeLLM(None, {"attack_focus": f}))
            for team, f in ((TeamId.BLUE, "left"), (TeamId.RED, "right"))
        }
    )


def service_with_workflow(**ttl):
    repo = InMemoryMatchRepository()
    workflow = HalftimeWorkflow(
        coaches(), collections_for(repo), lease_ttl_s=ttl.get("ttl", 0.3), heartbeat_s=0.05
    )
    service = MatchService(repo, step_seconds=0, halftime=workflow, recovery_interval_s=0.05)
    return service, workflow


def test_normal_halftime_verifies_both_actions():
    service, workflow = service_with_workflow()
    match_id = service.create_match(8, 4, start=False).match_id
    assert service.run_to_completion(match_id).phase is MatchPhase.FULL_TIME
    actions = workflow.ledger.for_match(match_id)
    assert [a.status for a in actions] == [S.VERIFIED, S.VERIFIED]
    assert all(a.fencing_token == 1 for a in actions)
    assert all(a.observed_state_version > a.expected_state_version for a in actions)
    task = workflow.task(match_id)
    assert task["status"] == "done" and task["step"] == "done" and task["recoveries"] == 0


def test_injected_crash_is_recovered_without_replaying_the_effect():
    service, workflow = service_with_workflow()
    match_id = service.create_match(8, 4).match_id
    assert service.arm_crash(match_id)
    final = service.wait_for(match_id, MatchPhase.FULL_TIME, timeout=15)
    assert final.phase is MatchPhase.FULL_TIME

    actions = {a.team_id: a for a in workflow.ledger.for_match(match_id)}
    assert {a.status for a in actions.values()} == {S.VERIFIED}
    # Blue's plan was applied, then the worker died before recording it.
    assert actions[TeamId.BLUE].fencing_token == 2
    sim = service.run(match_id).simulator
    assert sim.effects_of(action_id_for(match_id, TeamId.BLUE)) == 1
    assert sim.effects_of(action_id_for(match_id, TeamId.RED)) == 1
    task = workflow.task(match_id)
    assert task["recoveries"] == 1
    assert task["resubmissions"] == 0  # reconciled from simulator state, not re-sent
    assert task["duplicate_effects"] == 0
    # The coaches were not asked again: one decision per team.
    decisions = [service.repository.get_latest_decision(match_id, t) for t in TeamId]
    assert all(d.plan.based_on_state_version == task["snapshot_state_version"] for d in decisions)


def test_submitted_action_that_never_reached_the_simulator_is_resent_once():
    service, workflow = service_with_workflow(ttl=0.1)
    match_id = service.create_match(8, 4, start=False).match_id
    run = service.run(match_id)
    while run.simulator.state.phase is not MatchPhase.HALFTIME:
        service.advance(run)
    # Simulate a worker that recorded "submitted" and died before calling the simulator.
    task_id = task_id_for(match_id)
    token = workflow.leases.acquire(task_id, "dead-worker")
    workflow.tasks.find_one_and_update(
        {"task_id": task_id},
        {
            "$set": {
                "status": "running",
                "step": "executing",
                "recoveries": 0,
                "resubmissions": 0,
                "duplicate_effects": 0,
                "snapshot_state_version": run.simulator.state.state_version,
            }
        },
        upsert=True,
    )
    plans = workflow.decider.decide(run, run.simulator.state.state_version)
    now = datetime.now(UTC)
    blue_id = action_id_for(match_id, TeamId.BLUE)
    workflow.ledger.propose(
        Action(
            action_id=blue_id,
            match_id=match_id,
            team_id=TeamId.BLUE,
            requested=plans[TeamId.BLUE].plan,
            expected_state_version=plans[TeamId.BLUE].based_on_state_version,
            status=S.PROPOSED,
            fencing_token=token,
            created_at=now,
            updated_at=now,
        ),
        task_id,
    )
    workflow.ledger.transition(blue_id, S.SUBMITTED, task_id=task_id, token=token)
    time.sleep(0.15)  # lease expires; no heartbeat

    assert service.check_recovery() == [match_id]
    assert workflow.ledger.get(blue_id).status is S.VERIFIED
    assert run.simulator.effects_of(blue_id) == 1
    assert workflow.task(match_id)["resubmissions"] == 1
    assert run.simulator.state.phase is MatchPhase.SECOND_HALF


def test_stale_worker_cannot_commit_after_takeover():
    leases = LeaseManager(MemoryCollection("task_id"), ttl_seconds=0.05)
    ledger = ActionLedger(MemoryCollection("action_id"), leases)
    old = leases.acquire("t", "old")
    assert leases.acquire("t", "other") is None  # held
    now = datetime.now(UTC)
    from app.simulator.roster import DEFAULT_TACTICS

    ledger.propose(
        Action(
            action_id="a",
            match_id="m",
            team_id=TeamId.BLUE,
            requested=DEFAULT_TACTICS[TeamId.BLUE],
            expected_state_version=1,
            status=S.PROPOSED,
            fencing_token=old,
            created_at=now,
            updated_at=now,
        ),
        "t",
    )
    time.sleep(0.08)
    new = leases.acquire("t", "new")
    assert new == old + 1
    with pytest.raises(LeaseLost):
        ledger.transition("a", S.SUBMITTED, task_id="t", token=old)
    with pytest.raises(LeaseLost):
        leases.heartbeat("t", "old", old)
    assert ledger.transition("a", S.SUBMITTED, task_id="t", token=new).fencing_token == new


def test_ledger_refuses_skipping_states():
    leases = LeaseManager(MemoryCollection("task_id"))
    ledger = ActionLedger(MemoryCollection("action_id"), leases)
    token = leases.acquire("t", "w")
    from app.execution import TransitionRefused
    from app.simulator.roster import DEFAULT_TACTICS

    now = datetime.now(UTC)
    ledger.propose(
        Action(
            action_id="a",
            match_id="m",
            team_id=TeamId.RED,
            requested=DEFAULT_TACTICS[TeamId.RED],
            expected_state_version=1,
            status=S.PROPOSED,
            fencing_token=token,
            created_at=now,
            updated_at=now,
        ),
        "t",
    )
    with pytest.raises(TransitionRefused):
        ledger.transition("a", S.VERIFIED, task_id="t", token=token)


def test_inject_crash_endpoint_arms_the_match():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.orchestration.dependencies import get_match_service

    service, _ = service_with_workflow()
    app.dependency_overrides[get_match_service] = lambda: service
    try:
        client = TestClient(app)
        match_id = service.create_match(1, 4, start=False).match_id
        body = client.post("/demo/inject-crash", json={"match_id": match_id}).json()
        assert body["armed"] is True
        assert client.post("/demo/inject-crash", json={"match_id": "nope"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_decisions_and_actions_endpoints():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.orchestration.dependencies import get_match_service

    service, _ = service_with_workflow()
    app.dependency_overrides[get_match_service] = lambda: service
    try:
        client = TestClient(app)
        match_id = service.create_match(8, 4, start=False).match_id
        assert client.get(f"/matches/{match_id}/decisions").json() == {}
        assert client.get(f"/matches/{match_id}/actions").json() == []
        service.run_to_completion(match_id)
        decisions = client.get(f"/matches/{match_id}/decisions").json()
        assert set(decisions) == {"blue", "red"}
        assert decisions["blue"]["plan"]["voice_script"]
        actions = client.get(f"/matches/{match_id}/actions").json()
        assert [a["status"] for a in actions] == ["verified", "verified"]
        assert client.get("/matches/nope/actions").status_code == 404
    finally:
        app.dependency_overrides.clear()
