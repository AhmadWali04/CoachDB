"""Collections for the ledger, leases and tasks: MongoDB or an in-memory twin.

`MemoryCollection` implements only the PyMongo calls this package uses, with
the same atomicity (one lock), so the ledger and lease logic is written once.
Supported filters: equality, `$in`, `$lt`, `$lte`, `$gt`; updates: `$set`, `$inc`,
`$setOnInsert`.
"""

from __future__ import annotations

import copy
import threading
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def _matches(doc: dict, query: dict) -> bool:
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                if op == "$in" and value not in arg:
                    return False
                if op == "$lt" and not (value is not None and value < arg):
                    return False
                if op == "$lte" and not (value is not None and value <= arg):
                    return False
                if op == "$gt" and not (value is not None and value > arg):
                    return False
        elif value != cond:
            return False
    return True


class MemoryCollection:
    def __init__(self, unique_key: str) -> None:
        self._docs: list[dict] = []
        self._key = unique_key
        self._lock = threading.Lock()

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        return None

    def insert_one(self, doc: dict) -> None:
        with self._lock:
            if any(d.get(self._key) == doc.get(self._key) for d in self._docs):
                raise DuplicateKeyError(f"duplicate {self._key}")
            self._docs.append(copy.deepcopy(doc))

    def find_one(self, query: dict) -> dict | None:
        with self._lock:
            found = next((d for d in self._docs if _matches(d, query)), None)
            return copy.deepcopy(found) if found else None

    def find(self, query: dict) -> list[dict]:
        with self._lock:
            return [copy.deepcopy(d) for d in self._docs if _matches(d, query)]

    def find_one_and_update(
        self,
        query: dict,
        update: dict,
        *,
        upsert: bool = False,
        return_document: ReturnDocument = ReturnDocument.BEFORE,
    ) -> dict | None:
        with self._lock:
            doc = next((d for d in self._docs if _matches(d, query)), None)
            if doc is None:
                if not upsert:
                    return None
                doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
                if any(d.get(self._key) == doc.get(self._key) for d in self._docs):
                    raise DuplicateKeyError(f"duplicate {self._key}")
                doc.update(update.get("$setOnInsert", {}))
                self._docs.append(doc)
                before = None
            else:
                before = copy.deepcopy(doc)
            doc.update(update.get("$set", {}))
            for k, n in update.get("$inc", {}).items():
                doc[k] = doc.get(k, 0) + n
            return copy.deepcopy(doc if return_document is ReturnDocument.AFTER else before)


def collections_for(repository: Any) -> dict[str, Any]:
    """`actions`, `worker_leases`, `tasks` next to the match repository's data."""
    database = getattr(repository, "database", None)
    if database is not None:
        return {name: database[name] for name in ("actions", "worker_leases", "tasks")}
    cached = getattr(repository, "_execution_collections", None)
    if cached is None:
        cached = {
            "actions": MemoryCollection("action_id"),
            "worker_leases": MemoryCollection("task_id"),
            "tasks": MemoryCollection("task_id"),
        }
        repository._execution_collections = cached
    return cached
