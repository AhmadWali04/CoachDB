"""ElevenLabs text-to-speech adapter (PRD §11, CLAUDE.md "ElevenLabs requirements").

Presentation only: never a source of match truth, never blocks the match.
Callers must catch `TextToSpeechError` and fall back to text.
"""

from __future__ import annotations

from typing import Protocol

import httpx

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_TIMEOUT_SECONDS = 10.0


class TextToSpeechError(Exception):
    """Raised on any TTS failure (timeout, HTTP error, bad credentials)."""


class TextToSpeechClient(Protocol):
    def synthesize(self, text: str, voice_id: str) -> bytes: ...


class ElevenLabsClient:
    def __init__(self, api_key: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def synthesize(self, text: str, voice_id: str) -> bytes:
        try:
            response = httpx.post(
                ELEVENLABS_TTS_URL.format(voice_id=voice_id),
                headers={"xi-api-key": self._api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_turbo_v2_5"},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise TextToSpeechError(str(exc)) from exc


class FakeTextToSpeechClient:
    """Deterministic fake for tests: never touches the network."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def synthesize(self, text: str, voice_id: str) -> bytes:
        self.calls.append((text, voice_id))
        if self.fail:
            raise TextToSpeechError("synthetic failure")
        return f"AUDIO:{voice_id}:{len(text)}".encode()
