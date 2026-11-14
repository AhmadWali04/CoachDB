"""Real $vectorSearch round trip. Skipped unless TEST_MONGODB_URI is set, e.g.

    docker compose up -d
    TEST_MONGODB_URI='mongodb://localhost:27017/?directConnection=true' .venv/bin/pytest \\
        tests/test_data_atlas_integration.py
"""

import os
import uuid

import pytest

from app.data import search_styles
from app.data.loader import load_style_profiles
from app.data.tactical_style import DIMENSIONS, EMBEDDING_MODEL, style_query_vector
from app.schemas import ObservedTactics

from .test_data_tactical_style import profile

URI = os.environ.get("TEST_MONGODB_URI")
pytestmark = pytest.mark.skipif(not URI, reason="TEST_MONGODB_URI not set")


@pytest.fixture
def collection_name():
    return f"style_profiles_test_{uuid.uuid4().hex[:8]}"


def test_loaded_profiles_are_found_by_search_styles(collection_name):
    from pymongo import AsyncMongoClient, MongoClient

    from app.data.style_profile import finalize_profiles

    cohort = finalize_profiles(
        [
            profile("low_block", 0.05, "4-4-2"),
            profile("mid_block", 0.15, "4-2-3-1"),
            profile("high_press", 0.40, "4-3-3"),
        ]
    )
    sync = MongoClient(URI, serverSelectionTimeoutMS=3000, tz_aware=True)
    db = sync["rival_coaches_test"]
    try:
        result = load_style_profiles(db[collection_name], [p.to_dict() for p in cohort])
        assert result.upserted == 3
        assert result.index_status == "READY"

        async def query():
            client = AsyncMongoClient(URI, serverSelectionTimeoutMS=3000, tz_aware=True)
            try:
                return await search_styles(
                    client["rival_coaches_test"][collection_name],
                    style_query_vector(
                        ObservedTactics(formation="4-3-3", pressing="high", defensive_line="high")
                    ),
                    embedding_model=EMBEDDING_MODEL,
                    dimensions=DIMENSIONS,
                    limit=3,
                    timeout=10.0,
                )
            finally:
                await client.close()

        import asyncio
        import time

        # A freshly built index can lag the documents by a moment.
        hits = []
        for _ in range(20):
            hits = asyncio.run(query())
            if len(hits) == 3:
                break
            time.sleep(1)
        assert [h.profile_id for h in hits][0] == "high_press"
        assert all(0 <= h.score <= 1 for h in hits)
    finally:
        db.drop_collection(collection_name)
        sync.close()
