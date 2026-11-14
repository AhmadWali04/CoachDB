"""Guards the one thing that can't be type-checked across the two Track B
data modules: a document this pipeline writes must be queryable by Codex's
`search_styles` (see `backend/app/data/README.md`'s storage contract)."""

import pytest

from app.data.indexes import vector_index_definition
from app.data.retrieval import STYLE_NAMESPACE
from app.data.style_profile import (
    EMBEDDING_MODEL,
    FEATURE_NAMES,
    StyleProfile,
    finalize_profiles,
)
from app.data.tactical_style import DIMENSIONS


def bare(profile_id="p", formation=None, features=None):
    return StyleProfile(
        profile_id=profile_id,
        source="statsbomb",
        source_match_id="m",
        team_label="Team",
        formation=formation,
        features=features or {},
    )


def test_namespace_matches_the_retrieval_modules_constant():
    [profile] = finalize_profiles([bare()])
    assert profile.to_dict()["namespace"] == STYLE_NAMESPACE


def test_unranked_profile_cannot_be_stored():
    with pytest.raises(ValueError, match="finalize_profiles"):
        bare().to_dict()


def test_embedding_fits_the_provisioned_index():
    [profile] = finalize_profiles([bare(formation="4-3-3")])
    index = vector_index_definition(DIMENSIONS)
    assert len(profile.to_dict()["embedding"]) == index["fields"][0]["numDimensions"]


def test_stored_document_has_every_field_the_storage_contract_requires():
    [profile] = finalize_profiles(
        [bare(formation="4-3-3", features=dict.fromkeys(FEATURE_NAMES, 1.0))]
    )
    document = profile.to_dict()

    for field in ("profile_id", "summary", "source", "source_match_id"):
        assert field in document

    assert document["namespace"] == STYLE_NAMESPACE
    assert document["embedding_model"] == EMBEDDING_MODEL
    assert len(document["embedding"]) == DIMENSIONS
    assert all(isinstance(value, float) for value in document["embedding"])
