"""Worker leases with fencing tokens (PRD §9.3).

A worker owns a task while its lease is fresh. Every (re)acquisition after
expiry increments the fencing token, and writes check the token, so a stale
worker that wakes up after a replacement took over cannot commit.
A heartbeat only proves the process is alive; task progress lives in `tasks`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class LeaseLost(RuntimeError):
    """The caller's fencing token is no longer current."""


def _now() -> datetime:
    return datetime.now(UTC)


class LeaseManager:
    def __init__(self, collection: Any, ttl_seconds: float = 3.0) -> None:
        self.leases = collection
        self.ttl = timedelta(seconds=ttl_seconds)

    def acquire(self, task_id: str, owner: str) -> int | None:
        """Claim a free or expired lease; returns the new fencing token, or None if held."""
        now = _now()
        try:
            doc = self.leases.find_one_and_update(
                {"task_id": task_id, "expires_at": {"$lt": now}},
                {
                    "$set": {"owner": owner, "expires_at": now + self.ttl, "heartbeat_at": now},
                    "$inc": {"token": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            if doc is None:
                doc = self.leases.find_one_and_update(
                    {"task_id": task_id},
                    {
                        "$setOnInsert": {
                            "owner": owner,
                            "expires_at": now + self.ttl,
                            "heartbeat_at": now,
                            "token": 1,
                        }
                    },
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                if doc.get("owner") != owner or doc.get("token") != 1:
                    return None
        except DuplicateKeyError:
            return None
        return int(doc["token"])

    def heartbeat(self, task_id: str, owner: str, token: int) -> None:
        now = _now()
        doc = self.leases.find_one_and_update(
            {"task_id": task_id, "owner": owner, "token": token},
            {"$set": {"expires_at": now + self.ttl, "heartbeat_at": now}},
        )
        if doc is None:
            raise LeaseLost(task_id)

    def require(self, task_id: str, token: int) -> None:
        doc = self.leases.find_one({"task_id": task_id})
        if doc is None or doc.get("token") != token:
            raise LeaseLost(task_id)

    def expired(self, task_id: str) -> bool:
        doc = self.leases.find_one({"task_id": task_id})
        return doc is not None and doc["expires_at"] < _now()

    def release(self, task_id: str, owner: str, token: int) -> None:
        self.leases.find_one_and_update(
            {"task_id": task_id, "owner": owner, "token": token},
            {"$set": {"expires_at": _now() - timedelta(seconds=1)}},
        )
