"""Orchestrates the StatsBomb + Metrica -> style profile pipeline (PRD §14.2).

Network fetches go through the raw cache (`_http.fetch_cached`); parsing lives
in `statsbomb.py`/`metrica.py` so it can be tested offline. Profiles are
ranked against each other (`finalize_profiles`), so the labels depend on the
whole set: rebuild and reload every profile together, never one at a time.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import metrica, statsbomb
from .style_profile import StyleProfile, finalize_profiles

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent / ".cache" / "data" / "style_profiles.json"
)

# FIFA World Cup 2022 (StatsBomb competition 43, season 106): first N matches
# by kickoff. About 3.5 MB of raw events per match is cached locally; only a
# few KB of derived profile per team is ever stored.
DEFAULT_STATSBOMB_COMPETITION: tuple[int, int] = (43, 106)
DEFAULT_STATSBOMB_MAX_MATCHES = 16
# Sample_Game_3 ships in a different (JSON/EPTS) format and isn't supported.
DEFAULT_METRICA_GAMES: tuple[str, ...] = ("Sample_Game_1", "Sample_Game_2")


def select_statsbomb_matches(
    competition: tuple[int, int], max_matches: int
) -> list[tuple[int, dict[int, str]]]:
    matches = statsbomb.fetch_matches(*competition)
    matches.sort(key=lambda m: (m["match_date"], m.get("kick_off") or "", m["match_id"]))
    return [(m["match_id"], statsbomb.match_context(m)) for m in matches[:max_matches]]


def build_all_profiles(
    statsbomb_competition: tuple[int, int] | None = DEFAULT_STATSBOMB_COMPETITION,
    statsbomb_max_matches: int = DEFAULT_STATSBOMB_MAX_MATCHES,
    metrica_games: tuple[str, ...] = DEFAULT_METRICA_GAMES,
) -> list[StyleProfile]:
    profiles: list[StyleProfile] = []

    if statsbomb_competition is not None and statsbomb_max_matches > 0:
        for match_id, context in select_statsbomb_matches(
            statsbomb_competition, statsbomb_max_matches
        ):
            try:
                profiles.extend(statsbomb.build_match_profiles(match_id, context))
            except Exception:
                logger.warning(
                    "skipping StatsBomb match %s after a fetch/parse error",
                    match_id,
                    exc_info=True,
                )

    for game in metrica_games:
        try:
            profiles.extend(metrica.build_game_profiles(game))
        except Exception:
            logger.warning(
                "skipping Metrica game %s after a fetch/parse error", game, exc_info=True
            )

    return finalize_profiles(profiles) if profiles else []


def write_profiles(profiles: list[StyleProfile], out_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([p.to_dict() for p in profiles], indent=2))
    return out_path


def read_profiles(path: Path = DEFAULT_OUTPUT_PATH) -> list[dict]:
    return json.loads(path.read_text())
