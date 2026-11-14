"""FastAPI-facing wiring for the voice module. Keeps `app/api/matches.py`
down to a single call."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config.settings import get_settings
from app.schemas import TeamId

from .cache import AudioCache
from .decisions import CoachDecisionReader
from .service import BriefingService
from .tts import ElevenLabsClient, TextToSpeechClient

AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "audio"


def get_shared_decision_reader() -> CoachDecisionReader:
    """The match repository: `MongoMatchRepository` or its in-memory twin."""
    from app.orchestration.dependencies import get_repository

    return get_repository()


@lru_cache
def get_briefing_service() -> BriefingService:
    settings = get_settings()
    tts: TextToSpeechClient | None = None
    if settings.elevenlabs_api_key is not None:
        tts = ElevenLabsClient(api_key=settings.elevenlabs_api_key.get_secret_value())
    return BriefingService(
        decisions=get_shared_decision_reader(),
        cache=AudioCache(AUDIO_CACHE_DIR),
        tts=tts,
        voice_ids={
            TeamId.BLUE: settings.elevenlabs_blue_voice_id,
            TeamId.RED: settings.elevenlabs_red_voice_id,
        },
    )
