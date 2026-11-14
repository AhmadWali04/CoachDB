from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import mongomock
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.coaches.workflow import CoachWorkflow
from app.config.settings import Settings
from app.orchestration.engine import Engine
from app.orchestration.store import LeaseLost
from app.simulator import MatchSimulator


@pytest.fixture
def engine():
    instance = Engine(
        mongomock.MongoClient(tz_aware=True).engine_test,
        Settings(_env_file=None, engine_step_seconds=0, llm_provider="deterministic"),
        checkpointer=InMemorySaver(),
    )
    yield instance
    instance.close()


def test_match_recovers_after_submission_without_duplicate_effects(engine, monkeypatch):
    state = engine.create(42, 3, fast=True)
    assert engine.store.arm_crash(state.match_id)
    engine.run(state.match_id)
    doc = engine.store.read(state.match_id)
    assert doc["phase"] == "second_half"
    assert all(a["status"] == "submitted" for a in doc["_engine"]["actions"].values())
    effects = doc["_engine"]["runtime"]["applied_actions"]
    monkeypatch.setattr(CoachWorkflow, "run", Mock(side_effect=AssertionError("coach replayed")))
    engine.run(state.match_id)
    doc = engine.store.read(state.match_id)
    assert doc["phase"] == "full_time" and doc["_engine"]["recoveries"] == 1
    assert doc["_engine"]["runtime"]["applied_actions"] == effects
    assert engine.db.match_frames.count_documents({}) == 6
    assert engine.db.match_events.count_documents({"type": "tactical_change"}) == 2
    assert engine.db.actions.count_documents({"status": "verified"}) == 2
    assert engine.db.coach_experiences.count_documents({"verified": True}) == 2


def test_expired_worker_cannot_commit_or_renew(engine):
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]
    engine.store.now = lambda: clock[0]
    state = engine.create(42, 3, fast=True)
    first = engine.store.claim(state.match_id, "first")
    sim = MatchSimulator.restore(first["_engine"]["runtime"])
    assert engine.store.claim(state.match_id, "second") is None
    clock[0] += timedelta(seconds=16)
    assert engine.store.claim(state.match_id, "second")["_engine"]["fence"] == 2
    with pytest.raises(LeaseLost):
        engine.store.commit(sim, "first", 1)
    with pytest.raises(LeaseLost):
        engine.store.heartbeat(state.match_id, "first", 1)
