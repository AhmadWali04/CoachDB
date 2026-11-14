"""Memory lookups for coaches, bound to Atlas Vector Search.

Both return an empty list on any failure: memory is a hint, never a blocker.
"""

from __future__ import annotations

import asyncio
import logging

from app.data import StyleHit, search_styles
from app.data.loader import STYLE_COLLECTION
from app.data.tactical_style import DIMENSIONS, EMBEDDING_MODEL, style_query_vector
from app.schemas import ObservedTactics

from .agents import StyleSearch

logger = logging.getLogger(__name__)


def atlas_style_search(uri: str, database: str, limit: int = 3) -> StyleSearch:
    """Public style profiles (`public:styles`) closest to the scout's observations."""

    def search(observed: ObservedTactics) -> list[StyleHit]:
        vector = style_query_vector(observed)
        if vector is None:
            return []

        async def go() -> list[StyleHit]:
            from pymongo import AsyncMongoClient

            client = AsyncMongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
            try:
                return await search_styles(
                    client[database][STYLE_COLLECTION],
                    vector,
                    embedding_model=EMBEDDING_MODEL,
                    dimensions=DIMENSIONS,
                    limit=limit,
                    timeout=5.0,
                )
            finally:
                await client.close()

        try:
            return asyncio.run(go())
        except Exception:
            logger.warning("style search unavailable")
            return []

    return search
