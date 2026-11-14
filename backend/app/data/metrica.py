"""Metrica Sports sample data (github.com/metrica-sports/sample-data) adapter.

Matches are anonymized -- teams are "Home"/"Away", never identified
real teams or players (PRD §14.2). Only the lightweight events CSV is
used, not the (much larger) tracking data, to stay compact.
"""

from __future__ import annotations

import csv
import io

from ._http import urlopen
from .style_profile import StyleProfile, derive_tags

BASE_URL = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data"
REQUEST_TIMEOUT_SECONDS = 20.0
LONG_PASS_THRESHOLD_NORMALIZED = 25.0 / 105.0  # ~25m on a 105m-long normalized pitch

# The sample data's x/y are normalized 0..1 over a standard pitch.
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


def fetch_events_csv(game: str) -> str:
    url = f"{BASE_URL}/{game}/{game}_RawEventsData.csv"
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def _pass_length_m(row: dict[str, str]) -> float | None:
    try:
        sx, sy, ex, ey = (float(row[k]) for k in ("Start X", "Start Y", "End X", "End Y"))
    except (KeyError, ValueError):
        return None
    dx = (ex - sx) * PITCH_LENGTH_M
    dy = (ey - sy) * PITCH_WIDTH_M
    return (dx**2 + dy**2) ** 0.5


def parse_metrica_events(csv_text: str, team: str, game: str) -> StyleProfile | None:
    """`team` is "Home" or "Away", matching the CSV's `Team` column."""
    rows = [row for row in csv.DictReader(io.StringIO(csv_text)) if row.get("Team") == team]
    if not rows:
        return None

    all_rows = list(csv.DictReader(io.StringIO(csv_text)))
    total_events = len(all_rows) or 1

    passes_attempted = 0
    passes_completed = 0
    pass_lengths_m: list[float] = []
    long_passes = 0
    shots = 0

    for row in rows:
        event_type = (row.get("Type") or "").upper()
        if event_type == "PASS":
            passes_attempted += 1
            if row.get("To"):
                passes_completed += 1
            length = _pass_length_m(row)
            if length is not None:
                pass_lengths_m.append(length)
                if length / PITCH_LENGTH_M >= LONG_PASS_THRESHOLD_NORMALIZED:
                    long_passes += 1
        elif event_type == "SHOT":
            shots += 1

    pass_completion_rate = (
        round(passes_completed / passes_attempted, 3) if passes_attempted else 0.0
    )
    avg_pass_length_m = (
        round(sum(pass_lengths_m) / len(pass_lengths_m), 2) if pass_lengths_m else 0.0
    )
    long_pass_ratio = round(long_passes / passes_attempted, 3) if passes_attempted else 0.0
    features = {
        "possession_pct": round(len(rows) / total_events * 100, 2),
        "pass_completion_rate": pass_completion_rate,
        "avg_pass_length_m": avg_pass_length_m,
        "long_pass_ratio": long_pass_ratio,
        # Metrica's sample events don't record a pressing/pressure event type.
        "pressures_per_match": 0.0,
        "shots_per_match": float(shots),
        "xg_per_match": 0.0,
        "passes_per_possession": 0.0,
    }

    return StyleProfile(
        profile_id=f"metrica:{game}:{team.lower()}",
        source="metrica",
        source_match_id=game,
        team_label=team,
        formation=None,
        features=features,
        tags=derive_tags(features),
    )


def build_game_profiles(game: str) -> list[StyleProfile]:
    csv_text = fetch_events_csv(game)
    profiles = []
    for team in ("Home", "Away"):
        profile = parse_metrica_events(csv_text, team, game)
        if profile is not None:
            profiles.append(profile)
    return profiles
