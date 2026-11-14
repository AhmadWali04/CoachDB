"""Process-wide match service: MongoDB when configured, in memory otherwise."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config.mongo import get_client, get_db
from app.config.settings import get_settings

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


@lru_cache
def get_match_service() -> MatchService:
    return MatchService(get_repository(), step_seconds=get_settings().match_step_seconds)
