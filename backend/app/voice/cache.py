"""Audio cache keyed by stable briefing ID (PRD §11).

Stores generated audio bytes on local disk and a small JSON sidecar.
MongoDB (Track A) should persist only the reference/metadata that
`Briefing.audio_url` carries, never the audio blob itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedAudio:
    briefing_id: str
    relative_path: str


class AudioCache:
    """Filesystem-backed cache. Swappable for object storage later; callers
    only depend on `get`/`put`."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def get(self, briefing_id: str) -> CachedAudio | None:
        meta_path = self._meta_path(briefing_id)
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text())
        return CachedAudio(briefing_id=briefing_id, relative_path=meta["relative_path"])

    def put(self, briefing_id: str, audio_bytes: bytes) -> CachedAudio:
        audio_path = self._audio_path(briefing_id)
        audio_path.write_bytes(audio_bytes)
        relative_path = audio_path.name
        self._meta_path(briefing_id).write_text(json.dumps({"relative_path": relative_path}))
        return CachedAudio(briefing_id=briefing_id, relative_path=relative_path)

    def _audio_path(self, briefing_id: str) -> Path:
        return self._root / f"{briefing_id}.mp3"

    def _meta_path(self, briefing_id: str) -> Path:
        return self._root / f"{briefing_id}.json"
