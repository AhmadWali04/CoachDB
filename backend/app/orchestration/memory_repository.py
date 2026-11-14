"""In-memory twin of `MongoMatchRepository` for tests and database-less runs.

Same method names and the same conflict rules (immutable IDs, version-checked
match updates), so services can be tested without MongoDB.
"""

from __future__ import annotations

import threading

from app.persistence import MissingMatch, PersistenceConflict
from app.schemas import CoachDecision, Frame, MatchEvent, MatchState, TeamId


class InMemoryMatchRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._matches: dict[str, MatchState] = {}
        self._events: dict[str, MatchEvent] = {}
        self._frames: dict[tuple[str, int], Frame] = {}
        self._decisions: dict[str, CoachDecision] = {}
        self.documents: dict[str, dict[str, dict]] = {}  # generic collections

    def ensure_indexes(self) -> None:
        return None

    def create_match(self, state: MatchState) -> None:
        with self._lock:
            if state.match_id in self._matches:
                raise PersistenceConflict("match already exists")
            self._matches[state.match_id] = state.model_copy(deep=True)

    def get_match(self, match_id: str) -> MatchState | None:
        with self._lock:
            state = self._matches.get(match_id)
            return state.model_copy(deep=True) if state else None

    def update_match(self, state: MatchState, *, expected_state_version: int) -> None:
        if state.state_version <= expected_state_version:
            raise ValueError("new state_version must advance beyond the expected version")
        with self._lock:
            current = self._matches.get(state.match_id)
            if current is None or current.state_version != expected_state_version:
                raise PersistenceConflict("match missing or state_version changed")
            self._matches[state.match_id] = state.model_copy(deep=True)

    def _require(self, match_id: str) -> None:
        if match_id not in self._matches:
            raise MissingMatch(match_id)

    def append_event(self, event: MatchEvent) -> None:
        with self._lock:
            self._require(event.match_id)
            existing = self._events.get(event.event_id)
            if existing is not None and existing != event:
                raise PersistenceConflict("event ID already has different content")
            self._events[event.event_id] = event

    def append_frame(self, frame: Frame) -> None:
        with self._lock:
            self._require(frame.match_id)
            key = (frame.match_id, frame.seq)
            existing = self._frames.get(key)
            if existing is not None and existing != frame:
                raise PersistenceConflict("frame seq already has different content")
            self._frames[key] = frame

    def get_frames(self, match_id: str, *, from_seq: int = 0, limit: int = 50) -> list[Frame]:
        with self._lock:
            frames = [f for (m, s), f in self._frames.items() if m == match_id and s >= from_seq]
        return sorted(frames, key=lambda f: f.seq)[:limit]

    def get_events(
        self, match_id: str, *, after_event_id: str | None = None, limit: int = 200
    ) -> list[MatchEvent]:
        with self._lock:
            events = sorted(
                (e for e in self._events.values() if e.match_id == match_id),
                key=lambda e: (e.half, e.step, e.event_id),
            )
        if after_event_id is not None:
            ids = [e.event_id for e in events]
            if after_event_id not in ids:
                raise ValueError("after_event_id is not an event in this match")
            events = events[ids.index(after_event_id) + 1 :]
        return events[:limit]

    def save_decision(self, decision: CoachDecision) -> None:
        with self._lock:
            self._require(decision.match_id)
            existing = self._decisions.get(decision.decision_id)
            if existing is not None and existing != decision:
                raise PersistenceConflict("decision ID already has different content")
            self._decisions[decision.decision_id] = decision

    def get_latest_decision(self, match_id: str, team_id: TeamId) -> CoachDecision | None:
        with self._lock:
            found = [
                d
                for d in self._decisions.values()
                if d.match_id == match_id and d.team_id == TeamId(team_id)
            ]
        return max(found, key=lambda d: (d.created_at, d.decision_id), default=None)
