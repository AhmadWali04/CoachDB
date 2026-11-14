"""Guards the one thing that can't be type-checked across the two Track B
data modules: a document this pipeline writes must be queryable by Codex's
`search_styles` (see `backend/app/data/README.md`'s storage contract)."""

from app.data.retrieval import STYLE_NAMESPACE
from app.data.style_profile import EMBEDDING_MODEL, FEATURE_NAMES, StyleProfile


def test_namespace_matches_the_retrieval_modules_constant():
    assert (
        StyleProfile(
            profile_id="p",
            source="statsbomb",
            source_match_id="m",
            team_label="Team",
            formation=None,
            features={},
        ).to_dict()["namespace"]
        == STYLE_NAMESPACE
    )


def test_stored_document_has_every_field_the_storage_contract_requires():
    profile = StyleProfile(
        profile_id="p",
        source="statsbomb",
        source_match_id="m",
        team_label="Team",
        formation="4-3-3",
        features=dict.fromkeys(FEATURE_NAMES, 1.0),
    )
    document = profile.to_dict()

    for field in ("profile_id", "summary", "source", "source_match_id"):
        assert field in document

    assert document["namespace"] == STYLE_NAMESPACE
    assert document["embedding_model"] == EMBEDDING_MODEL
    assert len(document["embedding"]) == len(FEATURE_NAMES)
    assert all(isinstance(value, float) for value in document["embedding"])
