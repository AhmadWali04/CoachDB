"""StatsBomb/Metrica style-profile ingestion (Claude, `b/track-b-experience`)
and historical retrieval (Codex, `b/data-memory`) -- see README.md.
Historical context informs coach memory and benchmarks only; the simulator
remains the source of truth for the simulated match (CLAUDE.md principle 1).
"""

from .pipeline import build_all_profiles, write_profiles
from .retrieval import ExperienceHit, StyleHit, search_experiences, search_styles
from .style_profile import FEATURE_NAMES, StyleProfile, derive_tags

__all__ = [
    "FEATURE_NAMES",
    "ExperienceHit",
    "StyleHit",
    "StyleProfile",
    "build_all_profiles",
    "derive_tags",
    "search_experiences",
    "search_styles",
    "write_profiles",
]
