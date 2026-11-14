"""Read-only access to persisted coach decisions, for the voice module.

Track A owns `backend/app/persistence` and will write `coach_decisions`
there. Until a Mongo-backed reader is handed off (see the Requests table in
CHECKLIST.md), `InMemoryCoachDecisionReader` lets the briefing endpoint be
real, typed, and testable today; swapping in a persistence-backed
`CoachDecisionReader` later needs no change to `BriefingService`.
"""

from typing import Protocol

from app.schemas import CoachDecision, TeamId


class CoachDecisionReader(Protocol):
    def get_latest_decision(self, match_id: str, team_id: TeamId) -> CoachDecision | None: ...


class InMemoryCoachDecisionReader:
    def __init__(self) -> None:
        self._decisions: dict[tuple[str, TeamId], CoachDecision] = {}

    def put(self, decision: CoachDecision) -> None:
        self._decisions[(decision.match_id, decision.team_id)] = decision

    def get_latest_decision(self, match_id: str, team_id: TeamId) -> CoachDecision | None:
        return self._decisions.get((match_id, team_id))
