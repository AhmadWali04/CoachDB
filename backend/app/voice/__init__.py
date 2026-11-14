"""ElevenLabs voice adapter: cache by briefing ID, text fallback (PRD §11)."""

from .cache import AudioCache, CachedAudio
from .decisions import CoachDecisionReader, InMemoryCoachDecisionReader
from .dependencies import AUDIO_CACHE_DIR, get_briefing_service, get_shared_decision_reader
from .service import BriefingNotFoundError, BriefingService
from .tts import ElevenLabsClient, FakeTextToSpeechClient, TextToSpeechClient, TextToSpeechError

__all__ = [
    "AUDIO_CACHE_DIR",
    "AudioCache",
    "BriefingNotFoundError",
    "BriefingService",
    "CachedAudio",
    "CoachDecisionReader",
    "ElevenLabsClient",
    "FakeTextToSpeechClient",
    "InMemoryCoachDecisionReader",
    "TextToSpeechClient",
    "TextToSpeechError",
    "get_briefing_service",
    "get_shared_decision_reader",
]
