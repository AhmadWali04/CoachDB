"""Bounded, read-only historical context for scouts and coaches.

Collections use PyMongo's async aggregate shape: await aggregate(pipeline),
then iterate the cursor asynchronously. No driver dependency is required here.
"""

import asyncio
import logging
import math
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.guardrails import coach_namespace, require_own_namespace
from app.schemas import TeamId

from .indexes import EXPERIENCE_INDEX, STYLE_INDEX

logger = logging.getLogger(__name__)
STYLE_NAMESPACE = "public:styles"


class SearchCollection(Protocol):
    async def aggregate(self, pipeline: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        """Return an async cursor; configure a finite driver server-selection timeout."""
        ...


class StyleHit(BaseModel):
    profile_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_match_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class ExperienceHit(BaseModel):
    experience_id: str = Field(min_length=1)
    namespace: str
    summary: str = Field(min_length=1)
    verified_outcome: str = Field(min_length=1)
    occurred_at: datetime
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


def _vector(values: Sequence[float], dimensions: int, limit: int, timeout: float) -> list[float]:
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise ValueError("dimensions must be a positive integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("timeout must be greater than 0 and at most 30 seconds")
    vector = [float(value) for value in values]
    if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
        raise ValueError("query vector must match dimensions and contain only finite values")
    if not any(vector):
        raise ValueError("cosine query vector must be nonzero")
    return vector


async def _search(
    collection: SearchCollection,
    vector: list[float],
    index: str,
    filters: dict[str, Any],
    fields: list[str],
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": index,
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": limit * 20,
                "limit": limit,
                "filter": filters,
            }
        },
        {
            "$project": {
                "_id": 0,
                **dict.fromkeys(fields, 1),
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    try:
        async with asyncio.timeout(timeout):
            cursor = await collection.aggregate(pipeline)
            try:
                documents = []
                async for document in cursor:
                    documents.append(document)
                    if len(documents) >= limit:
                        break
                return documents
            finally:
                close = getattr(cursor, "close", None)
                if close is not None:
                    await close()
    except Exception:
        # Do not log query vectors, documents, credentials, or exception text.
        logger.warning("historical retrieval unavailable", extra={"index_name": index})
        return []


async def search_styles(
    collection: SearchCollection,
    query_vector: Sequence[float],
    *,
    embedding_model: str,
    dimensions: int,
    limit: int = 5,
    timeout: float = 2.0,
) -> list[StyleHit]:
    """Public dataset profiles only; empty context on search service failure."""
    vector = _vector(query_vector, dimensions, limit, timeout)
    if not embedding_model.strip():
        raise ValueError("embedding_model is required")
    documents = await _search(
        collection,
        vector,
        STYLE_INDEX,
        {"namespace": STYLE_NAMESPACE, "embedding_model": embedding_model},
        ["profile_id", "summary", "source", "source_match_id"],
        limit,
        timeout,
    )
    hits = []
    for document in documents:
        try:
            hits.append(StyleHit.model_validate(document))
        except ValidationError:
            continue
    return hits


async def search_experiences(
    team_id: TeamId,
    collection: SearchCollection,
    query_vector: Sequence[float],
    *,
    before: datetime,
    embedding_model: str,
    dimensions: int,
    namespace: str | None = None,
    limit: int = 5,
    timeout: float = 2.0,
) -> list[ExperienceHit]:
    """Own verified outcomes strictly before the decision cutoff, never rival memory.

    The caller supplies the frozen decision time, not the wall clock at retry.
    Authorization and invalid input errors deliberately propagate to the caller.
    """
    namespace = require_own_namespace(
        team_id, coach_namespace(team_id) if namespace is None else namespace
    )
    vector = _vector(query_vector, dimensions, limit, timeout)
    if before.tzinfo is None or before.utcoffset() is None:
        raise ValueError("before must be timezone-aware")
    if not embedding_model.strip():
        raise ValueError("embedding_model is required")
    documents = await _search(
        collection,
        vector,
        EXPERIENCE_INDEX,
        {
            "namespace": namespace,
            "verified": True,
            "occurred_at": {"$lt": before},
            "embedding_model": embedding_model,
        },
        ["experience_id", "namespace", "summary", "verified", "verified_outcome", "occurred_at"],
        limit,
        timeout,
    )
    hits = []
    for document in documents:
        try:
            hit = ExperienceHit.model_validate(document)
            # Defense in depth against a misconfigured adapter or corrupt response.
            if (
                document.get("verified") is True
                and hit.namespace == namespace
                and hit.occurred_at.tzinfo is not None
                and hit.occurred_at < before
            ):
                hits.append(hit)
        except (ValidationError, TypeError):
            continue
    return hits
