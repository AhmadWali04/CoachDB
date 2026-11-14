"""Explicit, idempotent provisioning for the private experience vector index.

No experience documents are read or written. Existing incompatible indexes are
never rebuilt automatically; the engine owner must choose the embedding model.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from pymongo import timeout
from pymongo.database import Database
from pymongo.errors import CollectionInvalid
from pymongo.operations import SearchIndexModel

from .indexes import EXPERIENCE_INDEX, vector_index_definition

EXPERIENCE_COLLECTION = "coach_experiences"


class IndexDefinitionMismatch(ValueError):
    """An existing index does not match the requested storage contract."""


@dataclass(frozen=True)
class ProvisionResult:
    created_collection: bool
    created_index: bool
    status: str


def _matches(actual: dict | None, expected: dict) -> bool:
    if not isinstance(actual, dict):
        return False
    # Atlas may return field definitions in a different order.
    actual = dict(actual)
    expected = dict(expected)
    actual["fields"] = sorted(actual.get("fields", []), key=lambda field: field.get("path", ""))
    expected["fields"] = sorted(expected["fields"], key=lambda field: field["path"])
    return actual == expected


def provision_experience_index(
    database: Database, dimensions: int, *, timeout_s: float = 30.0
) -> ProvisionResult:
    """Create only when missing, then verify READY and queryable before success.

    Require the writer's actual dimensions; styles' nine-dimensional embedding
    is not implicitly reused for experiences. Errors propagate to the operator.
    """
    definition = vector_index_definition(dimensions, experiences=True)
    if not math.isfinite(timeout_s) or not 0 < timeout_s <= 300:
        raise ValueError("timeout_s must be greater than zero and at most 300 seconds")
    created_collection = False
    created_index = False
    deadline = time.monotonic() + timeout_s
    with timeout(timeout_s):
        if EXPERIENCE_COLLECTION not in database.list_collection_names(
            filter={"name": EXPERIENCE_COLLECTION}
        ):
            try:
                database.create_collection(EXPERIENCE_COLLECTION)
                created_collection = True
            except CollectionInvalid:
                # Another operator created the collection between the read and create.
                pass
        collection = database[EXPERIENCE_COLLECTION]
        indexes = list(collection.list_search_indexes(EXPERIENCE_INDEX))
        if indexes:
            if not _matches(indexes[0].get("latestDefinition"), definition):
                raise IndexDefinitionMismatch(
                    "Existing coach_experiences_vector definition differs; "
                    "coordinate embedding dimensions and index migration with Track A. "
                    "No index was changed."
                )
        else:
            collection.create_search_index(
                SearchIndexModel(definition=definition, name=EXPERIENCE_INDEX, type="vectorSearch")
            )
            created_index = True

        while time.monotonic() < deadline:
            indexes = list(collection.list_search_indexes(EXPERIENCE_INDEX))
            if indexes:
                index = indexes[0]
                if not _matches(index.get("latestDefinition"), definition):
                    raise IndexDefinitionMismatch(
                        "Experience index definition changed while waiting; "
                        "coordinate with Track A."
                    )
                status = index.get("status", "UNKNOWN")
                if status in {"FAILED", "DELETING"}:
                    raise RuntimeError(f"Experience vector index is {status}; inspect it in Atlas")
                if status == "READY" and index.get("queryable") is True:
                    return ProvisionResult(created_collection, created_index, status)
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
    raise TimeoutError(
        "Experience vector index did not become READY/queryable before the deadline; "
        "it may still be building. Rerun the same command to check; do not drop the index."
    )
