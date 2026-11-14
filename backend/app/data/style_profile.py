"""Compact style profile derived from historical match data (PRD §14.2).

A profile informs coach memory and benchmarks only; it never feeds the
live simulation (CLAUDE.md principle 1). Features are plain, named
numbers rather than a learned embedding -- there's no embedding model in
this MVP -- but `embedding` (the same values in a fixed order) is shaped
so it can be indexed by Atlas Vector Search like any other embedding.

Field names (`summary`, `source_match_id`, `namespace`, `embedding_model`,
`embedding`) match the storage contract in `backend/app/data/README.md`
(Codex, `search_styles`/`search_experiences`, `b/data-memory`), so a
document written by this pipeline is queryable by that retrieval code
without translation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Source = Literal["statsbomb", "metrica"]

# Must match retrieval.STYLE_NAMESPACE -- duplicated as a literal rather than
# imported to keep the ingestion pipeline independent of the retrieval
# module; test_style_profile.py asserts the two stay in sync.
STYLE_NAMESPACE = "public:styles"

# No embedding model is wired up in this MVP; these handcrafted stats stand
# in for one so the documents are still queryable via $vectorSearch.
EMBEDDING_MODEL = "handcrafted-stats-v1"

FEATURE_NAMES: tuple[str, ...] = (
    "possession_pct",
    "pass_completion_rate",
    "avg_pass_length_m",
    "long_pass_ratio",
    "pressures_per_match",
    "shots_per_match",
    "xg_per_match",
    "passes_per_possession",
)


@dataclass(frozen=True)
class StyleProfile:
    profile_id: str
    source: Source
    source_match_id: str
    team_label: str
    formation: str | None
    features: dict[str, float]
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def embedding(self) -> list[float]:
        return [self.features.get(name, 0.0) for name in FEATURE_NAMES]

    @property
    def summary(self) -> str:
        formation = self.formation or "formation unknown"
        tag_text = ", ".join(self.tags)
        return f"{self.team_label} ({self.source}): {formation}, {tag_text}"

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "source": self.source,
            "source_match_id": self.source_match_id,
            "team_label": self.team_label,
            "formation": self.formation,
            "summary": self.summary,
            "namespace": STYLE_NAMESPACE,
            "embedding_model": EMBEDDING_MODEL,
            "embedding": self.embedding,
            "features": self.features,
            "tags": self.tags,
            "created_at": self.created_at,
        }


def derive_tags(features: dict[str, float]) -> list[str]:
    tags: list[str] = []
    if features.get("possession_pct", 0) >= 55:
        tags.append("possession-heavy")
    if features.get("long_pass_ratio", 0) >= 0.25:
        tags.append("direct")
    if features.get("pressures_per_match", 0) >= 120:
        tags.append("high-press")
    if features.get("shots_per_match", 0) >= 14:
        tags.append("shot-heavy")
    if not tags:
        tags.append("balanced")
    return tags
