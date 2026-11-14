"""Local vector search helpers, handed to Track A for the scout/coach
(CHECKLIST.md). Swappable later for Atlas `$vectorSearch`: both
`search_styles` and `search_experiences` only need something that can
list candidate vectors, so the in-memory stores here can be replaced by
Mongo-backed ones without changing either search function's signature.

`search_styles` has no privacy constraint -- style profiles are public,
historical data. `search_experiences` always calls `require_own_namespace`
first (AGENTS.md §2), so a coach can never retrieve a rival's experiences,
even by mistake. Vector results are hints, not truth (PRD §8.2): callers
must verify any retrieved claim against stored structured data before
acting on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.guardrails import require_own_namespace
from app.schemas import TeamId

from .style_profile import StyleProfile, cosine_similarity


class InMemoryStyleProfileStore:
    def __init__(self, profiles: list[StyleProfile] | None = None) -> None:
        self._profiles = list(profiles or [])

    def add_many(self, profiles: list[StyleProfile]) -> None:
        self._profiles.extend(profiles)

    def all(self) -> list[StyleProfile]:
        return list(self._profiles)


def search_styles(
    store: InMemoryStyleProfileStore, query_vector: list[float], limit: int = 5
) -> list[tuple[StyleProfile, float]]:
    scored = [(profile, cosine_similarity(query_vector, profile.vector)) for profile in store.all()]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


@dataclass(frozen=True)
class Experience:
    experience_id: str
    namespace: str
    vector: list[float]
    situation_summary: str
    payload: dict = field(default_factory=dict)


class InMemoryExperienceStore:
    def __init__(self) -> None:
        self._by_namespace: dict[str, list[Experience]] = {}

    def add(self, experience: Experience) -> None:
        self._by_namespace.setdefault(experience.namespace, []).append(experience)

    def by_namespace(self, namespace: str) -> list[Experience]:
        return list(self._by_namespace.get(namespace, []))


def search_experiences(
    store: InMemoryExperienceStore,
    coach_team_id: TeamId,
    namespace: str,
    query_vector: list[float],
    limit: int = 5,
) -> list[tuple[Experience, float]]:
    require_own_namespace(coach_team_id, namespace)
    candidates = store.by_namespace(namespace)
    scored = [
        (experience, cosine_similarity(query_vector, experience.vector))
        for experience in candidates
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]
