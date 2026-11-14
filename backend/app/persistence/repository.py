"""Typed MongoDB persistence for authoritative simulator output.

Index creation is explicit. Inject app.config.mongo.get_db() at the composition
root. Service/driver failures propagate; process memory is never a fallback.
"""

from __future__ import annotations

from datetime import datetime

from bson import BSON
from bson.codec_options import CodecOptions
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.guardrails import rival_of
from app.schemas import CoachDecision, Frame, MatchEvent, MatchState, TeamId


class PersistenceConflict(RuntimeError):
    """A stable ID was reused with different content or a state version is stale."""


class MissingMatch(LookupError):
    """Child records must belong to a persisted authoritative match."""


def _aware_dates(value: object) -> None:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("persisted timestamps must be timezone-aware")
    elif isinstance(value, dict):
        for item in value.values():
            _aware_dates(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _aware_dates(item)


def _document(model: BaseModel) -> dict:
    # Revalidate mutable Pydantic instances and normalize to actual BSON precision.
    data = type(model).model_validate(model.model_dump(mode="python")).model_dump(mode="python")
    _aware_dates(data)
    return BSON.encode(data).decode(codec_options=CodecOptions(tz_aware=True))


def _without_id(document: dict) -> dict:
    return {key: value for key, value in document.items() if key not in {"_id", "_engine"}}


def _parse[Model: BaseModel](model: type[Model], document: dict | None) -> Model | None:
    return None if document is None else model.model_validate(_without_id(document))


def _insert_immutable(collection: Collection, key: dict, model: BaseModel) -> None:
    document = _document(model)
    try:
        collection.insert_one(document)
    except DuplicateKeyError as error:
        stored = collection.find_one(key)
        if stored is None or _without_id(stored) != _without_id(document):
            raise PersistenceConflict("stable record ID already has different content") from error


class MongoMatchRepository:
    """Match/frame/event writer and the voice module's CoachDecisionReader.

    This class does not run a simulation, create tactics, execute actions or
    acquire leases. Those services own when each typed record can be committed.
    """

    def __init__(self, database: Database):
        self.database = database
        self.matches = database["matches"]
        self.events = database["match_events"]
        self.frames = database["match_frames"]
        self.decisions = database["coach_decisions"]

    def ensure_indexes(self) -> None:
        self.matches.create_index("match_id", unique=True)
        self.events.create_index("event_id", unique=True)
        self.events.create_index(
            [
                ("match_id", ASCENDING),
                ("half", ASCENDING),
                ("step", ASCENDING),
                ("event_id", ASCENDING),
            ]
        )
        self.frames.create_index([("match_id", ASCENDING), ("seq", ASCENDING)], unique=True)
        self.decisions.create_index("decision_id", unique=True)
        self.decisions.create_index(
            [
                ("match_id", ASCENDING),
                ("team_id", ASCENDING),
                ("created_at", DESCENDING),
                ("decision_id", DESCENDING),
            ]
        )
        self.database["actions"].create_index("action_id", unique=True)
        self.database["actions"].create_index([("match_id", ASCENDING), ("status", ASCENDING)])
        self.database["tasks"].create_index("task_id", unique=True)
        self.database["tasks"].create_index([("match_id", ASCENDING), ("status", ASCENDING)])

    def create_match(self, state: MatchState) -> None:
        _insert_immutable(self.matches, {"match_id": state.match_id}, state)

    def get_match(self, match_id: str) -> MatchState | None:
        return _parse(MatchState, self.matches.find_one({"match_id": match_id}))

    def update_match(self, state: MatchState, *, expected_state_version: int) -> None:
        if (
            isinstance(expected_state_version, bool)
            or not isinstance(expected_state_version, int)
            or expected_state_version < 0
            or state.state_version <= expected_state_version
        ):
            raise ValueError(
                "new state_version must advance beyond the nonnegative expected version"
            )
        document = _document(state)
        result = self.matches.replace_one(
            {"match_id": state.match_id, "state_version": expected_state_version}, document
        )
        if result.matched_count != 1:
            raise PersistenceConflict(
                "match missing or state_version changed; reload before retrying"
            )

    def _require_match(self, match_id: str) -> MatchState:
        state = self.get_match(match_id)
        if state is None:
            raise MissingMatch(match_id)
        return state

    def append_event(self, event: MatchEvent) -> None:
        self._require_match(event.match_id)
        _insert_immutable(self.events, {"event_id": event.event_id}, event)

    def append_frame(self, frame: Frame) -> None:
        self._require_match(frame.match_id)
        if any(event.match_id != frame.match_id for event in frame.events):
            raise ValueError("frame contains events from a different match")
        _insert_immutable(self.frames, {"match_id": frame.match_id, "seq": frame.seq}, frame)

    def get_frames(self, match_id: str, *, from_seq: int = 0, limit: int = 50) -> list[Frame]:
        self._validate_limit(limit)
        if isinstance(from_seq, bool) or not isinstance(from_seq, int) or from_seq < 0:
            raise ValueError("from_seq must be a nonnegative integer")
        cursor = self.frames.find({"match_id": match_id, "seq": {"$gte": from_seq}})
        return [
            Frame.model_validate(_without_id(doc))
            for doc in cursor.sort("seq", ASCENDING).limit(limit)
        ]

    def get_events(
        self, match_id: str, *, after_event_id: str | None = None, limit: int = 200
    ) -> list[MatchEvent]:
        self._validate_limit(limit)
        query: dict = {"match_id": match_id}
        if after_event_id is not None:
            anchor = self.events.find_one({"match_id": match_id, "event_id": after_event_id})
            if anchor is None:
                raise ValueError("after_event_id is not an event in this match")
            query["$or"] = [
                {"half": {"$gt": anchor["half"]}},
                {"half": anchor["half"], "step": {"$gt": anchor["step"]}},
                {
                    "half": anchor["half"],
                    "step": anchor["step"],
                    "event_id": {"$gt": anchor["event_id"]},
                },
            ]
        cursor = (
            self.events.find(query)
            .sort([("half", ASCENDING), ("step", ASCENDING), ("event_id", ASCENDING)])
            .limit(limit)
        )
        return [MatchEvent.model_validate(_without_id(doc)) for doc in cursor]

    def save_decision(self, decision: CoachDecision) -> None:
        state = self._require_match(decision.match_id)
        team = next(team for team in state.teams if team.team_id == decision.team_id)
        reports = (decision.analysis, decision.scouting, decision.plan)
        if any(
            report.match_id != decision.match_id or report.team_id != decision.team_id
            for report in reports
        ):
            raise ValueError("decision reports must belong to the same match and team")
        version = decision.plan.based_on_state_version
        if (
            decision.analysis.state_version != version
            or decision.scouting.state_version != version
            or version < 0
            or version > state.state_version
        ):
            raise ValueError("decision reports must reference one existing snapshot version")
        if decision.scouting.rival_team_id != rival_of(decision.team_id):
            raise ValueError("scouting rival must be the opposing team")
        if decision.coach_id != team.coach_id:
            raise ValueError("decision coach does not belong to this team")
        _insert_immutable(self.decisions, {"decision_id": decision.decision_id}, decision)

    def get_latest_decision(self, match_id: str, team_id: TeamId) -> CoachDecision | None:
        return _parse(
            CoachDecision,
            self.decisions.find_one(
                {"match_id": match_id, "team_id": TeamId(team_id).value},
                sort=[("created_at", DESCENDING), ("decision_id", DESCENDING)],
            ),
        )

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer between 1 and 200")
