"""StatsBomb/Metrica style-profile pipeline and local vector search (PRD §14.2).

Historical data informs coach memory and benchmarks only -- the simulator
stays the source of truth for the simulated match (CLAUDE.md principle 1).
"""

from .pipeline import build_all_profiles, write_profiles
from .style_profile import FEATURE_NAMES, StyleProfile, cosine_similarity, derive_tags
from .vector_search import (
    Experience,
    InMemoryExperienceStore,
    InMemoryStyleProfileStore,
    search_experiences,
    search_styles,
)

__all__ = [
    "FEATURE_NAMES",
    "Experience",
    "InMemoryExperienceStore",
    "InMemoryStyleProfileStore",
    "StyleProfile",
    "build_all_profiles",
    "cosine_similarity",
    "derive_tags",
    "search_experiences",
    "search_styles",
    "write_profiles",
]
