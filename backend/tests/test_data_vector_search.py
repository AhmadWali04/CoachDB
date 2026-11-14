import pytest

from app.data.style_profile import FEATURE_NAMES, StyleProfile, cosine_similarity
from app.data.vector_search import (
    Experience,
    InMemoryExperienceStore,
    InMemoryStyleProfileStore,
    search_experiences,
    search_styles,
)
from app.guardrails import GuardrailViolation, coach_namespace
from app.schemas import TeamId


def pad(vector: list[float]) -> list[float]:
    return vector + [0.0] * (len(FEATURE_NAMES) - len(vector))


def profile(profile_id: str, vector: list[float]) -> StyleProfile:
    features = dict(zip(FEATURE_NAMES, pad(vector), strict=True))
    return StyleProfile(
        profile_id=profile_id,
        source="statsbomb",
        source_ref="m1",
        team_label="Team",
        formation=None,
        features=features,
    )


def test_cosine_similarity_of_identical_vectors_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_of_opposite_vectors_is_negative_one():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_search_styles_ranks_most_similar_first():
    store = InMemoryStyleProfileStore(
        [profile("close", [1.0, 0.9]), profile("far", [0.0, 1.0]), profile("exact", [1.0, 1.0])]
    )
    results = search_styles(store, query_vector=pad([1.0, 1.0]), limit=2)
    assert [p.profile_id for p, _score in results] == ["exact", "close"]


def test_search_experiences_requires_own_namespace():
    store = InMemoryExperienceStore()
    with pytest.raises(GuardrailViolation):
        search_experiences(store, TeamId.BLUE, coach_namespace(TeamId.RED), query_vector=[1.0])


def test_blue_cannot_retrieve_red_experiences_even_within_the_same_store():
    store = InMemoryExperienceStore()
    store.add(Experience("e_blue", coach_namespace(TeamId.BLUE), [1.0, 0.0], "blue situation"))
    store.add(Experience("e_red", coach_namespace(TeamId.RED), [1.0, 0.0], "red situation"))

    blue_results = search_experiences(
        store, TeamId.BLUE, coach_namespace(TeamId.BLUE), query_vector=[1.0, 0.0]
    )

    assert [e.experience_id for e, _score in blue_results] == ["e_blue"]
