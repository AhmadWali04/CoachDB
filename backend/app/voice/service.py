"""Builds the halftime `Briefing`: read the persisted decision, then look up
or generate its audio (PRD §11).

Never generates tactics or match facts, and never regenerates audio that is
already cached. A TTS failure degrades to a text-only briefing; it must
never raise and never stop the match (CLAUDE.md "ElevenLabs requirements").
"""

from __future__ import annotations

import logging

from app.schemas import AudioStatus, Briefing, TeamId

from .cache import AudioCache
from .decisions import CoachDecisionReader
from .tts import TextToSpeechClient, TextToSpeechError

logger = logging.getLogger(__name__)

_COACH_NAMES = {TeamId.BLUE: "Blue Coach", TeamId.RED: "Red Coach"}


class BriefingNotFoundError(Exception):
    """No persisted halftime decision yet for this match/team."""


class BriefingService:
    def __init__(
        self,
        decisions: CoachDecisionReader,
        cache: AudioCache,
        tts: TextToSpeechClient | None,
        voice_ids: dict[TeamId, str | None],
        audio_url_base: str = "/audio",
    ) -> None:
        self._decisions = decisions
        self._cache = cache
        self._tts = tts
        self._voice_ids = voice_ids
        self._audio_url_base = audio_url_base

    def get_briefing(self, match_id: str, team_id: TeamId) -> Briefing:
        decision = self._decisions.get_latest_decision(match_id, team_id)
        if decision is None:
            raise BriefingNotFoundError(f"no decision yet for match={match_id} team={team_id}")

        briefing_id = decision.decision_id
        transcript = decision.plan.voice_script
        audio_status, audio_url = self._resolve_audio(briefing_id, transcript, team_id)

        return Briefing(
            briefing_id=briefing_id,
            match_id=match_id,
            team_id=team_id,
            coach_id=decision.coach_id,
            coach_name=_COACH_NAMES[team_id],
            transcript=transcript,
            audio_status=audio_status,
            audio_url=audio_url,
        )

    def _resolve_audio(
        self, briefing_id: str, transcript: str, team_id: TeamId
    ) -> tuple[AudioStatus, str | None]:
        cached = self._cache.get(briefing_id)
        if cached is not None:
            return AudioStatus.READY, f"{self._audio_url_base}/{cached.relative_path}"

        voice_id = self._voice_ids.get(team_id)
        if self._tts is None or not voice_id:
            return AudioStatus.UNAVAILABLE, None

        try:
            audio_bytes = self._tts.synthesize(transcript, voice_id)
        except TextToSpeechError:
            logger.warning(
                "tts synthesis failed, falling back to text",
                extra={"briefing_id": briefing_id, "team_id": team_id},
            )
            return AudioStatus.UNAVAILABLE, None

        cached = self._cache.put(briefing_id, audio_bytes)
        return AudioStatus.READY, f"{self._audio_url_base}/{cached.relative_path}"
