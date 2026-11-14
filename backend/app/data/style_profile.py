"""Compact style profile derived from historical match data (PRD §14.2).

A profile informs coach memory and benchmarks only; it never feeds the live
simulation (CLAUDE.md principle 1).

Two kinds of numbers:
- `features`: descriptive stats per source (pass completion, xG, ...).
- `tactical_features`: the same tactical measures for every source
  (`tactical_style.tactical_features`). After `finalize_profiles` ranks the
  whole set, they become `tactics` labels and the `embedding`.

Field names (`summary`, `source_match_id`, `namespace`, `embedding_model`,
`embedding`) match the storage contract in `backend/app/data/README.md`, so a
stored document is queryable by `search_styles` without translation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal

from . import tactical_style
from .tactical_style import EMBEDDING_MODEL, rank_cohort

Source = Literal["statsbomb", "metrica"]

# Must match retrieval.STYLE_NAMESPACE; test_data_style_profile_contract.py
# asserts the two stay in sync.
STYLE_NAMESPACE = "public:styles"

SOURCE_LABELS = {"statsbomb": "StatsBomb", "metrica": "Metrica, anonymized"}

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
    # "lineup" (announced, StatsBomb) or "tracking" (inferred from positions).
    formation_source: str | None = None
    tags: list[str] = field(default_factory=list)
    context: str | None = None
    tactical_features: dict[str, float | None] = field(default_factory=dict)
    tactics: dict[str, str | None] = field(default_factory=dict)
    style_vector: tuple[float, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def embedding(self) -> list[float]:
        return list(self.style_vector)

    @property
    def summary(self) -> str:
        where = SOURCE_LABELS[self.source]
        if self.context:
            where = f"{where}, {self.context}"
        formation = self.formation or "formation unknown"
        if self.formation and self.formation_source == "tracking":
            formation = f"{formation} (inferred from tracking)"
        if not self.tactics:
            return f"{self.team_label} ({where}): {formation}, {', '.join(self.tags)}"

        t = self.tactics
        parts = [
            f"{t['pressing']} press" if t.get("pressing") else None,
            f"{t['defensive_line']} line" if t.get("defensive_line") else None,
            f"{t['tempo']} tempo" if t.get("tempo") else None,
            t.get("mentality"),
        ]
        focus = t.get("attack_focus")
        if focus:
            share = self.tactical_features.get(f"{focus}_entry_share")
            pct = f" ({share:.0%} of final-third entries)" if share is not None else ""
            parts.append(f"attacks mainly through the {focus}{pct}")
        length = self.tactical_features.get("block_length_m")
        line = self.tactical_features.get("defensive_line_height_m")
        if length is not None and line is not None:
            parts.append(
                f"out of possession a {length:.0f} m long block, last line at {line:.0f} m"
            )
        described = ", ".join(p for p in parts if p) or "too little data to label"
        return f"{self.team_label} ({where}): {formation}; {described}."

    def to_dict(self) -> dict:
        if len(self.style_vector) != tactical_style.DIMENSIONS:
            raise ValueError(
                f"profile {self.profile_id} is not finalized; call finalize_profiles first"
            )
        return {
            "profile_id": self.profile_id,
            "source": self.source,
            "source_match_id": self.source_match_id,
            "team_label": self.team_label,
            "context": self.context,
            "formation": self.formation,
            "formation_source": self.formation_source,
            "summary": self.summary,
            "namespace": STYLE_NAMESPACE,
            "embedding_model": EMBEDDING_MODEL,
            "embedding": self.embedding,
            "tactics": self.tactics,
            "tactical_features": self.tactical_features,
            "features": self.features,
            "tags": self.tags,
            "created_at": self.created_at,
        }


def finalize_profiles(profiles: Sequence[StyleProfile]) -> list[StyleProfile]:
    """Rank and attach tactics labels and the embedding to each profile.

    Each source is ranked on its own: StatsBomb and Metrica log events
    differently (Metrica records far more recoveries), so pooling them would
    label every Metrica team by its data provider rather than its play.
    "High press" means high relative to the other teams in the same dataset.
    """
    finalized: dict[str, StyleProfile] = {}
    for source in dict.fromkeys(p.source for p in profiles):
        group = [p for p in profiles if p.source == source]
        ranked = rank_cohort([p.tactical_features for p in group], [p.formation for p in group])
        for p, r in zip(group, ranked, strict=True):
            finalized[p.profile_id] = replace(p, tactics=r.tactics, style_vector=r.style_vector)
    return [finalized[p.profile_id] for p in profiles]


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
