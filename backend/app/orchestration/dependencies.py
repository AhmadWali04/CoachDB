"""Process-wide match service: MongoDB when configured, in memory otherwise."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config.mongo import get_client, get_db
from app.config.settings import get_settings
from app.execution import HalftimeWorkflow, collections_for
from app.schemas import TeamId

from .halftime import CoachingHalftime
from .memory_repository import InMemoryMatchRepository
from .service import MatchRepository, MatchService

logger = logging.getLogger(__name__)


@lru_cache
def get_repository() -> MatchRepository:
    if get_client() is None:
        logger.warning("MONGODB_URI not set; matches are kept in memory only")
        return InMemoryMatchRepository()
    from app.persistence import MongoMatchRepository

    repository = MongoMatchRepository(get_db())
    repository.ensure_indexes()
    return repository


def build_halftime(repository: MatchRepository) -> HalftimeWorkflow:
    """Durable halftime (ledger, leases, recovery) around the AI coaches."""
    return HalftimeWorkflow(build_coaches(), collections_for(repository))


def build_coaches() -> CoachingHalftime | None:
    settings = get_settings()
    if not settings.coaches_enabled:
        return None
    from app.coaches import ClaudeStructuredLLM, Coach
    from app.coaches.memory import atlas_style_search

    llm = ClaudeStructuredLLM(model=settings.coach_model)
    style_search = None
    if settings.mongodb_uri is not None and settings.mongodb_uri.get_secret_value().strip():
        style_search = atlas_style_search(
            settings.mongodb_uri.get_secret_value().strip(), settings.mongodb_database
        )
    # Separate Coach objects: own identity, prompts (persona) and memory binding.
    coaches = {
        team: Coach(team, f"coach_{team.value}", llm, style_search=style_search) for team in TeamId
    }
    return CoachingHalftime(coaches)


@lru_cache
def get_match_service() -> MatchService:
    settings = get_settings()
    repository = get_repository()
    return MatchService(
        repository, step_seconds=settings.match_step_seconds, halftime=build_halftime(repository)
    )
