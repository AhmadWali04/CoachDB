import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.data import search_experiences, search_styles
from app.data.indexes import vector_index_definition
from app.guardrails import GuardrailViolation
from app.schemas import TeamId

CUTOFF = datetime(2026, 11, 14, tzinfo=UTC)
OPTIONS = {"embedding_model": "test-v1", "dimensions": 3}
VECTOR = [1.0, 0.5, 0.25]


class Cursor:
    def __init__(self, rows, *, fail=False, delay=0):
        self.rows = iter(rows)
        self.closed = False
        self.fail = fail
        self.delay = delay

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("private exception details")
        try:
            return next(self.rows)
        except StopIteration:
            raise StopAsyncIteration from None

    async def close(self):
        self.closed = True


class Collection:
    def __init__(self, rows=(), *, unavailable=False, fail=False, delay=0):
        self.calls = []
        self.unavailable = unavailable
        self.cursor = Cursor(rows, fail=fail, delay=delay)

    async def aggregate(self, pipeline):
        self.calls.append(pipeline)
        if self.unavailable:
            raise ConnectionError("private exception details")
        return self.cursor


def experience(namespace="coach:blue", **overrides):
    return {
        "experience_id": "exp-1",
        "namespace": namespace,
        "summary": "Left-channel entries",
        "verified": True,
        "verified_outcome": "2 verified shots in second half",
        "occurred_at": CUTOFF - timedelta(days=1),
        "score": 0.8,
        **overrides,
    }


def search(collection, **kwargs):
    return asyncio.run(
        search_experiences(TeamId.BLUE, collection, VECTOR, before=CUTOFF, **(OPTIONS | kwargs))
    )


def test_namespace_is_enforced_before_database_access():
    collection = Collection()
    with pytest.raises(GuardrailViolation):
        search(collection, namespace="coach:red")
    assert collection.calls == []


@pytest.mark.parametrize("team", [TeamId.BLUE, TeamId.RED])
def test_vector_query_prefilters_namespace_verified_cutoff_and_model(team):
    namespace = f"coach:{team.value}"
    collection = Collection([experience(namespace)])
    hits = asyncio.run(search_experiences(team, collection, VECTOR, before=CUTOFF, **OPTIONS))
    assert hits[0].namespace == namespace
    stage = collection.calls[0][0]["$vectorSearch"]
    assert stage["filter"] == {
        "namespace": namespace,
        "verified": True,
        "occurred_at": {"$lt": CUTOFF},
        "embedding_model": "test-v1",
    }
    assert stage["numCandidates"] == stage["limit"] * 20
    assert "embedding" not in collection.calls[0][1]["$project"]
    assert collection.cursor.closed


def test_foreign_unverified_future_and_malformed_results_never_escape():
    collection = Collection(
        [
            experience("coach:red"),
            experience(verified=False),
            experience(occurred_at=CUTOFF),
            experience(occurred_at=CUTOFF + timedelta(days=1)),
            experience(occurred_at=CUTOFF.replace(tzinfo=None)),
            experience(verified_outcome=None),
            experience(),
        ]
    )
    hits = search(collection, limit=10)
    assert len(hits) == 1
    assert hits[0].namespace == "coach:blue"
    assert not hasattr(hits[0], "embedding")


@pytest.mark.parametrize("kwargs", [{"unavailable": True}, {"fail": True}, {"delay": 0.1}])
def test_outage_cursor_failure_and_timeout_return_empty_context(kwargs, caplog):
    collection = Collection(**kwargs)
    assert search(collection, timeout=0.01) == []
    assert "historical retrieval unavailable" in caplog.text
    assert "private exception details" not in caplog.text
    if not kwargs.get("unavailable"):
        assert collection.cursor.closed


def test_cancellation_propagates():
    class CancelledCollection(Collection):
        async def aggregate(self, pipeline):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        search(CancelledCollection())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dimensions": 2},
        {"dimensions": True},
        {"limit": 0},
        {"limit": 21},
        {"limit": True},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"embedding_model": " "},
    ],
)
def test_invalid_options_fail_before_database_access(kwargs):
    collection = Collection()
    with pytest.raises(ValueError):
        search(collection, **kwargs)
    assert collection.calls == []


@pytest.mark.parametrize("vector", [[0, 0, 0], [float("nan"), 1, 0], [float("inf"), 0, 0]])
def test_invalid_vector_fails_before_database_access(vector):
    collection = Collection()
    with pytest.raises(ValueError):
        asyncio.run(search_experiences(TeamId.BLUE, collection, vector, before=CUTOFF, **OPTIONS))
    assert collection.calls == []


def test_naive_cutoff_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        asyncio.run(
            search_experiences(
                TeamId.BLUE, Collection(), VECTOR, before=CUTOFF.replace(tzinfo=None), **OPTIONS
            )
        )


def test_public_styles_are_separate_and_attributable():
    collection = Collection(
        [
            {
                "profile_id": "statsbomb:42:blue",
                "summary": "Pass-heavy historical profile",
                "source": "StatsBomb Open Data",
                "source_match_id": "42",
                "score": 0.9,
            },
            {"profile_id": "missing-attribution"},
        ]
    )
    hits = asyncio.run(search_styles(collection, VECTOR, **OPTIONS))
    assert len(hits) == 1
    assert hits[0].source == "StatsBomb Open Data"
    assert collection.calls[0][0]["$vectorSearch"]["filter"] == {
        "namespace": "public:styles",
        "embedding_model": "test-v1",
    }


def test_result_count_is_bounded_even_if_adapter_ignores_limit():
    collection = Collection([experience() for _ in range(10)])
    assert len(search(collection, limit=2)) == 2
    assert collection.cursor.closed


def test_vector_indexes_cover_every_query_filter():
    for experiences in (False, True):
        fields = vector_index_definition(384, experiences=experiences)["fields"]
        assert fields[0] == {
            "type": "vector",
            "path": "embedding",
            "numDimensions": 384,
            "similarity": "cosine",
        }
        filters = {field["path"] for field in fields[1:]}
        assert {"namespace", "embedding_model"} <= filters
        if experiences:
            assert {"verified", "occurred_at"} <= filters
    with pytest.raises(ValueError):
        vector_index_definition(0)
