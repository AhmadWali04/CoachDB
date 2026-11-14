from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from bson import BSON
from pydantic import ValidationError
from pymongo.errors import AutoReconnect, DuplicateKeyError

from app.persistence import MissingMatch, MongoMatchRepository, PersistenceConflict
from app.schemas import CoachDecision, Frame, MatchEvent, MatchState, TeamId
from app.voice import AudioCache, BriefingService

from .test_schemas import frame_payload, match_payload
from .test_voice import decision_payload


@pytest.fixture
def repo():
    db = MagicMock()
    collections = {}
    db.__getitem__.side_effect = lambda name: collections.setdefault(name, MagicMock())
    repository = MongoMatchRepository(db)
    repository.matches.find_one.return_value = MatchState.model_validate(
        match_payload(state_version=12)
    ).model_dump(mode="python")
    return repository


def event():
    return MatchEvent(
        event_id="event_001",
        match_id="match_001",
        half=1,
        step=1,
        clock_minute=2,
        type="shot",
        team_id="blue",
        created_at=datetime.now(UTC),
    )


def test_indexes_are_explicit_and_stable_ids_are_unique(repo):
    repo.matches.create_index.assert_not_called()
    repo.ensure_indexes()
    repo.matches.create_index.assert_called_once_with("match_id", unique=True)
    repo.frames.create_index.assert_called_once_with([("match_id", 1), ("seq", 1)], unique=True)
    assert repo.events.create_index.call_args_list[0].kwargs == {"unique": True}
    assert repo.decisions.create_index.call_args_list[0].kwargs == {"unique": True}
    repo.database["actions"].create_index.assert_any_call("action_id", unique=True)
    repo.database["tasks"].create_index.assert_any_call("task_id", unique=True)


def test_match_roundtrip_normalizes_bson_and_removes_only_mongo_id(repo):
    state = MatchState.model_validate(match_payload())
    repo.create_match(state)
    document = repo.matches.insert_one.call_args.args[0]
    assert isinstance(document["created_at"], datetime)
    assert document["created_at"].microsecond % 1000 == 0
    assert document["phase"] == "first_half"
    BSON.encode(document)
    repo.matches.find_one.return_value = {"_id": "mongo-id", **document}
    loaded = repo.get_match(state.match_id)
    assert loaded.seed == state.seed
    assert loaded.created_at.tzinfo is not None
    assert loaded.model_dump(mode="python") == document


def test_missing_match_returns_none(repo):
    repo.matches.find_one.return_value = None
    assert repo.get_match("absent") is None


@pytest.mark.parametrize(
    "method, collection, record",
    [
        ("create_match", "matches", MatchState.model_validate(match_payload())),
        ("append_event", "events", event()),
        ("append_frame", "frames", Frame.model_validate(frame_payload())),
        ("save_decision", "decisions", CoachDecision.model_validate(decision_payload())),
    ],
)
def test_stable_id_retry_is_idempotent_after_bson_precision_loss(repo, method, collection, record):
    target = getattr(repo, collection)
    getattr(repo, method)(record)
    stored = target.insert_one.call_args.args[0]
    target.insert_one.side_effect = DuplicateKeyError("duplicate")
    target.find_one.return_value = {"_id": "generated", **stored}
    getattr(repo, method)(record)
    target.replace_one.assert_not_called()
    target.update_one.assert_not_called()


@pytest.mark.parametrize(
    "method, collection, record",
    [
        ("create_match", "matches", MatchState.model_validate(match_payload())),
        ("append_event", "events", event()),
        ("append_frame", "frames", Frame.model_validate(frame_payload())),
        ("save_decision", "decisions", CoachDecision.model_validate(decision_payload())),
    ],
)
def test_reusing_stable_id_with_other_content_is_rejected(repo, method, collection, record):
    target = getattr(repo, collection)
    target.insert_one.side_effect = DuplicateKeyError("duplicate")
    # A different record must never overwrite append-only history.
    target.find_one.return_value = {"different": "content"}
    with pytest.raises(PersistenceConflict):
        getattr(repo, method)(record)
    target.replace_one.assert_not_called()
    target.update_one.assert_not_called()


def test_match_update_is_compare_and_swap_without_upsert(repo):
    state = MatchState.model_validate(match_payload(state_version=13))
    repo.matches.replace_one.return_value.matched_count = 1
    repo.update_match(state, expected_state_version=12)
    args, kwargs = repo.matches.replace_one.call_args
    assert args[0] == {"match_id": "match_001", "state_version": 12}
    assert args[1]["state_version"] == 13
    assert not kwargs.get("upsert")


def test_stale_worker_cannot_overwrite_newer_state(repo):
    repo.matches.replace_one.return_value.matched_count = 0
    with pytest.raises(PersistenceConflict, match="reload"):
        repo.update_match(
            MatchState.model_validate(match_payload(state_version=13)), expected_state_version=12
        )


@pytest.mark.parametrize("version", [-1, True, 1.5, "1", 13, 14])
def test_invalid_or_nonadvancing_version_rejected_before_write(repo, version):
    with pytest.raises(ValueError):
        repo.update_match(
            MatchState.model_validate(match_payload(state_version=13)),
            expected_state_version=version,
        )
    repo.matches.replace_one.assert_not_called()


def test_mutated_invalid_model_is_revalidated(repo):
    state = MatchState.model_validate(match_payload())
    state.clock_minute = 200
    with pytest.raises(ValidationError):
        repo.create_match(state)
    repo.matches.insert_one.assert_not_called()


def test_naive_timestamp_rejected_before_write(repo):
    state = MatchState.model_validate(match_payload())
    state.created_at = datetime(2026, 11, 14)
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.create_match(state)
    repo.matches.insert_one.assert_not_called()


@pytest.mark.parametrize(
    "method, record",
    [
        ("append_event", event()),
        ("append_frame", Frame.model_validate(frame_payload())),
        ("save_decision", CoachDecision.model_validate(decision_payload())),
    ],
)
def test_orphan_records_are_not_written(repo, method, record):
    repo.matches.find_one.return_value = None
    with pytest.raises(MissingMatch):
        getattr(repo, method)(record)


def test_frame_cannot_embed_another_matchs_events(repo):
    frame = Frame.model_validate(frame_payload())
    foreign = event().model_copy(update={"match_id": "foreign"})
    frame.events = [foreign]
    with pytest.raises(ValueError, match="different match"):
        repo.append_frame(frame)
    repo.frames.insert_one.assert_not_called()


def test_frame_query_is_ordered_bounded_and_scoped(repo):
    frame = Frame.model_validate(frame_payload())
    repo.frames.find.return_value.sort.return_value.limit.return_value = [frame.model_dump()]
    assert repo.get_frames("match_001", from_seq=4, limit=3) == [frame]
    repo.frames.find.assert_called_once_with({"match_id": "match_001", "seq": {"$gte": 4}})
    repo.frames.find.return_value.sort.assert_called_once_with("seq", 1)
    repo.frames.find.return_value.sort.return_value.limit.assert_called_once_with(3)


@pytest.mark.parametrize(
    "options",
    [
        {"from_seq": -1},
        {"from_seq": True},
        {"from_seq": 0.5},
        {"limit": 0},
        {"limit": True},
        {"limit": 201},
    ],
)
def test_invalid_pagination_makes_no_frame_query(repo, options):
    with pytest.raises(ValueError):
        repo.get_frames("match_001", **options)
    repo.frames.find.assert_not_called()


def test_event_cursor_is_scoped_and_uses_the_same_order_as_sort(repo):
    anchor = event().model_dump()
    repo.events.find_one.return_value = anchor
    repo.events.find.return_value.sort.return_value.limit.return_value = []
    assert repo.get_events("match_001", after_event_id="event_001", limit=2) == []
    repo.events.find_one.assert_called_once_with({"match_id": "match_001", "event_id": "event_001"})
    query = repo.events.find.call_args.args[0]
    assert query["match_id"] == "match_001"
    assert query["$or"] == [
        {"half": {"$gt": 1}},
        {"half": 1, "step": {"$gt": 1}},
        {"half": 1, "step": 1, "event_id": {"$gt": "event_001"}},
    ]
    repo.events.find.return_value.sort.assert_called_once_with(
        [("half", 1), ("step", 1), ("event_id", 1)]
    )


def test_foreign_or_missing_event_cursor_is_rejected(repo):
    repo.events.find_one.return_value = None
    with pytest.raises(ValueError, match="not an event in this match"):
        repo.get_events("match_001", after_event_id="red-match-event")
    repo.events.find.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"analysis": {"team_id": "red"}},
        {"plan": {"match_id": "foreign"}},
        {"scouting": {"state_version": 11}},
        {"scouting": {"rival_team_id": "blue"}},
        {"plan": {"based_on_state_version": 13}},
        {"coach_id": "rival-coach"},
    ],
)
def test_inconsistent_decision_is_rejected(repo, change):
    data = decision_payload()
    for field, value in change.items():
        if isinstance(value, dict):
            data[field].update(value)
        else:
            data[field] = value
    with pytest.raises(ValueError):
        repo.save_decision(CoachDecision.model_validate(data))
    repo.decisions.insert_one.assert_not_called()


def test_latest_decision_is_scoped_and_ties_are_deterministic(repo):
    decision = CoachDecision.model_validate(decision_payload())
    repo.decisions.find_one.return_value = {"_id": "mongo-id", **decision.model_dump()}
    assert repo.get_latest_decision("match_001", TeamId.BLUE) == decision
    repo.decisions.find_one.assert_called_once_with(
        {"match_id": "match_001", "team_id": "blue"},
        sort=[("created_at", -1), ("decision_id", -1)],
    )


def test_repository_satisfies_voice_reader_without_in_memory_decisions(repo, tmp_path):
    decision = CoachDecision.model_validate(decision_payload())
    repo.decisions.find_one.return_value = decision.model_dump()
    service = BriefingService(decisions=repo, cache=AudioCache(tmp_path), tts=None, voice_ids={})
    assert service.get_briefing("match_001", TeamId.BLUE).transcript == decision.plan.voice_script


def test_driver_failure_is_not_reported_as_success(repo):
    repo.matches.insert_one.side_effect = AutoReconnect("connection lost")
    with pytest.raises(AutoReconnect):
        repo.create_match(MatchState.model_validate(match_payload()))
