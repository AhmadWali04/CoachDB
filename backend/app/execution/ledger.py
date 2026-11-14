"""Action ledger: proposed -> submitted -> applied -> verified (PRD §9.1).

Terminal alternatives: rejected, failed, unknown. Each transition is a
conditional update on (action_id, allowed previous status) and carries the
writer's fencing token, checked against the lease first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.schemas import Action, ActionStatus

from .leases import LeaseManager

S = ActionStatus
ALLOWED_FROM: dict[ActionStatus, set[ActionStatus]] = {
    S.SUBMITTED: {S.PROPOSED},
    S.APPLIED: {S.SUBMITTED, S.UNKNOWN},
    S.VERIFIED: {S.APPLIED},
    S.REJECTED: {S.PROPOSED, S.SUBMITTED, S.UNKNOWN},
    S.FAILED: {S.PROPOSED, S.SUBMITTED, S.APPLIED, S.UNKNOWN},
    S.UNKNOWN: {S.SUBMITTED},
}
OPEN = {S.PROPOSED, S.SUBMITTED, S.APPLIED, S.UNKNOWN}


class TransitionRefused(RuntimeError):
    pass


class ActionLedger:
    def __init__(self, collection: Any, leases: LeaseManager) -> None:
        self.actions = collection
        self.leases = leases

    def ensure_indexes(self) -> None:
        self.actions.create_index("action_id", unique=True)

    def propose(self, action: Action, task_id: str) -> Action:
        """Idempotent: an existing action with this ID is returned unchanged."""
        self.leases.require(task_id, action.fencing_token)
        try:
            self.actions.insert_one(action.model_dump(mode="python"))
            return action
        except DuplicateKeyError:
            return self.get(action.action_id)

    def transition(
        self, action_id: str, to: ActionStatus, *, task_id: str, token: int, **fields: Any
    ) -> Action:
        self.leases.require(task_id, token)
        doc = self.actions.find_one_and_update(
            {
                "action_id": action_id,
                "status": {"$in": [s.value for s in ALLOWED_FROM[to]]},
                "fencing_token": {"$lte": token},
            },
            {
                "$set": {
                    "status": to.value,
                    "fencing_token": token,
                    "updated_at": datetime.now(UTC),
                    **fields,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            current = self.get(action_id)
            raise TransitionRefused(
                f"{action_id}: cannot move {current.status.value if current else 'missing'}"
                f" -> {to.value} with token {token}"
            )
        return Action.model_validate({k: v for k, v in doc.items() if k != "_id"})

    def get(self, action_id: str) -> Action | None:
        doc = self.actions.find_one({"action_id": action_id})
        return Action.model_validate({k: v for k, v in doc.items() if k != "_id"}) if doc else None

    def for_match(self, match_id: str) -> list[Action]:
        docs = self.actions.find({"match_id": match_id})
        actions = [Action.model_validate({k: v for k, v in d.items() if k != "_id"}) for d in docs]
        return sorted(actions, key=lambda a: (a.created_at, a.action_id))
