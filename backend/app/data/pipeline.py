"""Orchestrates the StatsBomb + Metrica -> style profile pipeline (PRD §14.2,
CHECKLIST.md "Data and memory"). Network fetches happen here; the parsing
itself lives in `statsbomb.py`/`metrica.py` so it can be tested offline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import metrica, statsbomb
from .style_profile import StyleProfile

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent / ".cache" / "data" / "style_profiles.json"
)

# Small, fixed sample: one real StatsBomb match and the three public Metrica
# sample games. Keeps the pipeline fast and well under the M0 512 MB budget --
# this writes a few KB of derived features, never the raw datasets.
DEFAULT_STATSBOMB_MATCH_IDS: tuple[int, ...] = (3857271,)  # England v Iran, FIFA World Cup 2022
# Sample_Game_3 ships in a different (JSON) event format than 1 and 2's CSV
# and isn't supported by this parser; add a second parser before including it.
DEFAULT_METRICA_GAMES: tuple[str, ...] = ("Sample_Game_1", "Sample_Game_2")


def build_all_profiles(
    statsbomb_match_ids: tuple[int, ...] = DEFAULT_STATSBOMB_MATCH_IDS,
    metrica_games: tuple[str, ...] = DEFAULT_METRICA_GAMES,
) -> list[StyleProfile]:
    profiles: list[StyleProfile] = []

    for match_id in statsbomb_match_ids:
        try:
            profiles.extend(statsbomb.build_match_profiles(match_id))
        except Exception:
            logger.warning(
                "skipping StatsBomb match %s after a fetch/parse error", match_id, exc_info=True
            )

    for game in metrica_games:
        try:
            profiles.extend(metrica.build_game_profiles(game))
        except Exception:
            logger.warning(
                "skipping Metrica game %s after a fetch/parse error", game, exc_info=True
            )

    return profiles


def write_profiles(profiles: list[StyleProfile], out_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([p.to_dict() for p in profiles], indent=2))
    return out_path
