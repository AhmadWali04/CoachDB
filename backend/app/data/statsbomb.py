"""StatsBomb Open Data (github.com/statsbomb/open-data) adapter.

Only free, published data; attribute it in the UI (PRD §14.2). Network
fetches are isolated in `fetch_events` so `parse_statsbomb_events` stays a
pure function you can unit test offline.
"""

from __future__ import annotations

import json
from typing import Any

from ._http import urlopen
from .style_profile import StyleProfile, derive_tags

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
REQUEST_TIMEOUT_SECONDS = 20.0
LONG_PASS_THRESHOLD_YARDS = 30.0


def fetch_events(match_id: int) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/events/{match_id}.json"
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)


def _formation_label(raw: int | None) -> str | None:
    if raw is None:
        return None
    digits = str(raw)
    return "-".join(digits)


def team_ids_and_names(events: list[dict[str, Any]]) -> dict[int, str]:
    teams: dict[int, str] = {}
    for event in events:
        team = event.get("team")
        if team:
            teams[team["id"]] = team["name"]
    return teams


def parse_statsbomb_events(
    events: list[dict[str, Any]], match_id: int, team_id: int
) -> StyleProfile | None:
    """Builds one team's style profile from a full match event list."""
    team_name: str | None = None
    formation: str | None = None

    passes_attempted = 0
    passes_completed = 0
    pass_lengths: list[float] = []
    long_passes = 0
    pressures = 0
    shots = 0
    xg_total = 0.0
    team_events = 0
    team_possession_events = 0
    total_possession_events = 0
    possession_ids: set[int] = set()

    for event in events:
        team = event.get("team")
        if team and team["id"] == team_id:
            team_name = team["name"]

        possession_team = event.get("possession_team")
        if possession_team:
            total_possession_events += 1
            if possession_team["id"] == team_id:
                team_possession_events += 1
                possession = event.get("possession")
                if possession is not None:
                    possession_ids.add(possession)

        if not team or team["id"] != team_id:
            continue
        team_events += 1

        event_type = event["type"]["name"]
        if event_type == "Starting XI":
            formation = _formation_label(event.get("tactics", {}).get("formation"))
        elif event_type == "Pass":
            passes_attempted += 1
            pass_info = event.get("pass", {})
            if "outcome" not in pass_info:
                passes_completed += 1
            length = pass_info.get("length")
            if length is not None:
                pass_lengths.append(length)
                if length >= LONG_PASS_THRESHOLD_YARDS:
                    long_passes += 1
        elif event_type == "Pressure":
            pressures += 1
        elif event_type == "Shot":
            shots += 1
            xg_total += event.get("shot", {}).get("statsbomb_xg", 0.0)

    if team_name is None or team_events == 0:
        return None

    possession_pct = (
        (team_possession_events / total_possession_events) * 100 if total_possession_events else 0.0
    )
    pass_completion_rate = (
        round(passes_completed / passes_attempted, 3) if passes_attempted else 0.0
    )
    avg_pass_length_m = round(sum(pass_lengths) / len(pass_lengths), 2) if pass_lengths else 0.0
    long_pass_ratio = round(long_passes / passes_attempted, 3) if passes_attempted else 0.0
    passes_per_possession = (
        round(passes_attempted / len(possession_ids), 2) if possession_ids else 0.0
    )
    features = {
        "possession_pct": round(possession_pct, 2),
        "pass_completion_rate": pass_completion_rate,
        "avg_pass_length_m": avg_pass_length_m,
        "long_pass_ratio": long_pass_ratio,
        "pressures_per_match": float(pressures),
        "shots_per_match": float(shots),
        "xg_per_match": round(xg_total, 3),
        "passes_per_possession": passes_per_possession,
    }

    return StyleProfile(
        profile_id=f"statsbomb:{match_id}:{team_id}",
        source="statsbomb",
        source_match_id=str(match_id),
        team_label=team_name,
        formation=formation,
        features=features,
        tags=derive_tags(features),
    )


def build_match_profiles(match_id: int) -> list[StyleProfile]:
    events = fetch_events(match_id)
    profiles = []
    for team_id in team_ids_and_names(events):
        profile = parse_statsbomb_events(events, match_id, team_id)
        if profile is not None:
            profiles.append(profile)
    return profiles
