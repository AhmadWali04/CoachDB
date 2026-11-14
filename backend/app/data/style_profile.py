"""Compact style profile derived from historical match data (PRD §14.2).

A profile informs coach memory and benchmarks only; it never feeds the
live simulation (CLAUDE.md principle 1). Features are plain, named
numbers rather than a learned embedding -- there's no embedding model in
this MVP -- but `vector` (the same values in a fixed order) is shaped so
it can be indexed by Atlas Vector Search like any other embedding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Source = Literal["statsbomb", "metrica"]

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
    source_ref: str
    team_label: str
    formation: str | None
    features: dict[str, float]
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def vector(self) -> list[float]:
        return [self.features.get(name, 0.0) for name in FEATURE_NAMES]

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "source": self.source,
            "source_ref": self.source_ref,
            "team_label": self.team_label,
            "formation": self.formation,
            "features": self.features,
            "vector": self.vector,
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


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
