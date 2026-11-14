"""Load derived style profiles into MongoDB and provision their vector index.

Run explicitly from `scripts/build_style_profiles.py --load`, never at match
startup (see indexes.py). Profiles are ranked as a set, so a load replaces the
whole `public:styles` set for this embedding model.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from pymongo import ReplaceOne
from pymongo.collection import Collection
from pymongo.operations import SearchIndexModel

from .indexes import STYLE_INDEX, vector_index_definition
from .style_profile import STYLE_NAMESPACE
from .tactical_style import DIMENSIONS, EMBEDDING_MODEL

STYLE_COLLECTION = "style_profiles"


@dataclass(frozen=True)
class LoadResult:
    upserted: int
    modified: int
    removed: int
    index_status: str


def ensure_style_index(collection: Collection, dimensions: int = DIMENSIONS) -> None:
    definition = vector_index_definition(dimensions)
    existing = list(collection.list_search_indexes(STYLE_INDEX))
    if not existing:
        collection.create_search_index(
            SearchIndexModel(definition=definition, name=STYLE_INDEX, type="vectorSearch")
        )
    elif existing[0].get("latestDefinition") != definition:
        collection.update_search_index(STYLE_INDEX, definition)


def wait_until_queryable(collection: Collection, timeout_s: float = 120.0) -> str:
    deadline = time.monotonic() + timeout_s
    status = "MISSING"
    while time.monotonic() < deadline:
        indexes = list(collection.list_search_indexes(STYLE_INDEX))
        if indexes:
            status = indexes[0].get("status", "UNKNOWN")
            if indexes[0].get("queryable") and status == "READY":
                return status
        time.sleep(1.0)
    raise TimeoutError(f"vector index {STYLE_INDEX} not queryable after {timeout_s}s ({status})")


def load_style_profiles(
    collection: Collection, documents: Sequence[dict], *, wait_s: float = 120.0
) -> LoadResult:
    for doc in documents:
        if doc.get("namespace") != STYLE_NAMESPACE or doc.get("embedding_model") != EMBEDDING_MODEL:
            raise ValueError(f"unexpected namespace/model on {doc.get('profile_id')}")
        if len(doc.get("embedding", [])) != DIMENSIONS:
            raise ValueError(f"embedding has wrong dimensions on {doc.get('profile_id')}")

    collection.create_index("profile_id", unique=True)
    result = collection.bulk_write(
        [ReplaceOne({"profile_id": d["profile_id"]}, d, upsert=True) for d in documents],
        ordered=False,
    )
    # Drop profiles from an earlier, differently ranked set of the same model.
    removed = collection.delete_many(
        {
            "namespace": STYLE_NAMESPACE,
            "embedding_model": EMBEDDING_MODEL,
            "profile_id": {"$nin": [d["profile_id"] for d in documents]},
        }
    ).deleted_count

    ensure_style_index(collection)
    status = wait_until_queryable(collection, wait_s)
    return LoadResult(result.upserted_count, result.modified_count, removed, status)
