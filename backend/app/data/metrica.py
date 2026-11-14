"""Metrica Sports sample data (github.com/metrica-sports/sample-data) adapter.

Matches are anonymized -- teams are "Home"/"Away", never identified
real teams or players (PRD §14.2). Only the lightweight events CSV is
used, not the (much larger) tracking data, to stay compact.
"""

from __future__ import annotations

import csv
import io

from ._http import fetch_cached
from .style_profile import StyleProfile, derive_tags
from .tactical_style import OnPitchEvent, tactical_features

BASE_URL = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data"
REQUEST_TIMEOUT_SECONDS = 30.0
LONG_PASS_THRESHOLD_NORMALIZED = 25.0 / 105.0  # ~25m on a 105m-long normalized pitch

# The sample data's x/y are normalized 0..1 over a standard pitch.
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


TEAMS = ("Home", "Away")


def fetch_events_csv(game: str) -> str:
    url = f"{BASE_URL}/{game}/{game}_RawEventsData.csv"
    return fetch_cached(url, f"metrica/{game}_RawEventsData.csv").decode("utf-8")


def _float(row: dict[str, str], key: str) -> float | None:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def attacking_right(rows: list[dict[str, str]]) -> dict[tuple[str, str], bool]:
    """`{(team, period): attacks toward x=1}` from where each team's shots start.

    Metrica coordinates are fixed to the screen and teams switch ends at
    halftime. A period with no shots for a team falls back to the opponent's
    shots, then to the same team's other period (flipped).
    """
    shots: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        x = _float(row, "Start X")
        if (row.get("Type") or "").upper() == "SHOT" and x is not None:
            shots.setdefault((row["Team"], row["Period"]), []).append(x)

    periods = sorted({row["Period"] for row in rows if row.get("Period")})
    known: dict[tuple[str, str], bool] = {key: sum(xs) / len(xs) > 0.5 for key, xs in shots.items()}
    for period in periods:
        for team in TEAMS:
            other = TEAMS[1 - TEAMS.index(team)]
            if (team, period) not in known and (other, period) in known:
                known[(team, period)] = not known[(other, period)]
    for period in periods:
        for team in TEAMS:
            if (team, period) in known:
                continue
            flipped = [not v for (t, p), v in known.items() if t == team and p != period]
            known[(team, period)] = flipped[0] if flipped else True
    return known


def to_on_pitch_events(rows: list[dict[str, str]]) -> list[OnPitchEvent]:
    direction = attacking_right(rows)
    kinds = {"PASS": "pass", "SHOT": "shot", "RECOVERY": "regain"}
    out: list[OnPitchEvent] = []
    for row in rows:
        kind = kinds.get((row.get("Type") or "").upper())
        team, period = row.get("Team"), row.get("Period")
        x, y = _float(row, "Start X"), _float(row, "Start Y")
        if kind is None or team not in TEAMS or x is None or y is None:
            continue
        try:
            t = float(row["Start Time [s]"])
        except (KeyError, ValueError):
            continue
        ex, ey = _float(row, "End X"), _float(row, "End Y")
        if not direction[(team, period)]:
            # Rotate 180 degrees so the team attacks +x with y=0 on its left.
            x, y = 1 - x, 1 - y
            ex = None if ex is None else 1 - ex
            ey = None if ey is None else 1 - ey
        out.append(
            OnPitchEvent(
                team,
                kind,  # type: ignore[arg-type]
                t,
                x * PITCH_LENGTH_M,
                y * PITCH_WIDTH_M,
                None if ex is None or kind != "pass" else ex * PITCH_LENGTH_M,
                None if ey is None or kind != "pass" else ey * PITCH_WIDTH_M,
            )
        )
    return out


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
    all_rows = list(csv.DictReader(io.StringIO(csv_text)))
    rows = [row for row in all_rows if row.get("Team") == team]
    if not rows:
        return None
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
        context=f"sample {game.replace('Sample_Game_', 'game ')}",
        tactical_features=tactical_features(to_on_pitch_events(all_rows), team),
    )


def build_game_profiles(game: str) -> list[StyleProfile]:
    csv_text = fetch_events_csv(game)
    profiles = []
    for team in ("Home", "Away"):
        profile = parse_metrica_events(csv_text, team, game)
        if profile is not None:
            profiles.append(profile)
    return profiles
