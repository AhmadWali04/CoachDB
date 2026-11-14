"""Opt-in real MongoDB persistence test in its own disposable test database."""

import os
from uuid import uuid4

import pytest
from pymongo import MongoClient

from app.persistence import MongoMatchRepository, PersistenceConflict
from app.schemas import CoachDecision, Frame, MatchState, TeamId

from .test_persistence import event
from .test_schemas import frame_payload, match_payload
from .test_voice import decision_payload

URI = os.environ.get("TEST_MONGODB_URI")
pytestmark = pytest.mark.skipif(not URI, reason="TEST_MONGODB_URI not set")


def test_repository_survives_new_client_and_enforces_unique_ids_and_versions():
    name = f"rival_coaches_repository_test_{uuid4().hex}"
    with MongoClient(URI, serverSelectionTimeoutMS=3000, tz_aware=True) as client:
        try:
            repo = MongoMatchRepository(client[name])
            repo.ensure_indexes()
            state = MatchState.model_validate(match_payload(state_version=12))
            repo.create_match(state)
            repo.create_match(state)
            original_event = event()
            repo.append_event(original_event)
            repo.append_event(original_event)
            with pytest.raises(PersistenceConflict):
                repo.append_event(original_event.model_copy(update={"details": {"changed": True}}))
            frame = Frame.model_validate(frame_payload())
            repo.append_frame(frame)
            repo.append_frame(frame)
            decision = CoachDecision.model_validate(decision_payload())
            repo.save_decision(decision)
            repo.save_decision(decision)
            state.state_version = 13
            repo.update_match(state, expected_state_version=12)
            with pytest.raises(PersistenceConflict):
                repo.update_match(state, expected_state_version=12)
            with MongoClient(URI, serverSelectionTimeoutMS=3000, tz_aware=True) as second:
                recovered = MongoMatchRepository(second[name])
                assert recovered.get_match(state.match_id).state_version == 13
                assert len(recovered.get_events(state.match_id)) == 1
                assert len(recovered.get_frames(state.match_id)) == 1
                assert (
                    recovered.get_latest_decision(state.match_id, TeamId.BLUE).decision_id
                    == decision.decision_id
                )
        finally:
            client.drop_database(name)
