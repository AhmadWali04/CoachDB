"""Metrica tracking data -> block shape and an inferred formation (PRD §14.2).

Tracking files are about 30 MB per team and match. They are cached in
`backend/.cache/data/raw/metrica/` and never stored in MongoDB; only the few
derived numbers below reach a profile.

What is measured, for each team, only while the opponent has the ball:
- `defensive_line_height_m`: average x of the four deepest outfield players.
- `block_length_m` / `block_width_m`: outfield spread along and across.
- formation: average positions of the starting outfield players in the first
  half, matched to the closest standard line pattern (`infer_formation`).

Possession comes from the synchronized event file (same frame numbers). The
formation is a heuristic from average positions, not the announced lineup, so
profiles mark it `formation_source="tracking"`.
"""

from __future__ import annotations

import bisect
import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ._http import fetch_cached
from .tactical_style import PITCH_LENGTH_M, PITCH_WIDTH_M

BASE_URL = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data"
FRAME_RATE = 25
SAMPLE_EVERY_FRAMES = FRAME_RATE  # one sample per second
# A possession is considered stale after this long without an on-ball event.
POSSESSION_STALE_FRAMES = 15 * FRAME_RATE
MIN_OUTFIELD_PLAYERS = 9
STARTER_SHARE = 0.5

# Line patterns tried by `infer_formation`, back to front.
FORMATION_LINES: dict[str, tuple[int, ...]] = {
    "4-4-2": (4, 4, 2),
    "4-3-3": (4, 3, 3),
    "4-5-1": (4, 5, 1),
    "3-5-2": (3, 5, 2),
    "3-4-3": (3, 4, 3),
    "5-3-2": (5, 3, 2),
    "5-4-1": (5, 4, 1),
    "4-2-3-1": (4, 2, 3, 1),
    "4-1-4-1": (4, 1, 4, 1),
    "4-4-1-1": (4, 4, 1, 1),
    "4-3-2-1": (4, 3, 2, 1),
    "3-4-2-1": (3, 4, 2, 1),
}
# An extra line must cut the mean squared depth spread by at least this much
# (m^2) to be chosen; otherwise noise in average positions would always favor
# four-line patterns.
EXTRA_LINE_PENALTY_M2 = 4.0

Position = tuple[float, float]


@dataclass(frozen=True)
class TrackingSample:
    period: str
    frame: int
    players: dict[str, Position]  # raw 0..1 screen coordinates


def fetch_tracking_csv(game: str, team: str) -> str:
    name = f"{game}_RawTrackingData_{team}_Team.csv"
    return fetch_cached(f"{BASE_URL}/{game}/{name}", f"metrica/{name}", timeout=120).decode("utf-8")


def _coord(value: str) -> float | None:
    try:
        v = float(value)
    except ValueError:
        return None
    return v if 0.0 <= v <= 1.0 else None


def parse_tracking(text: str, sample_every: int = SAMPLE_EVERY_FRAMES) -> list[TrackingSample]:
    """Parse one team's tracking CSV, keeping every `sample_every`-th frame."""
    reader = csv.reader(io.StringIO(text))
    try:
        next(reader)  # team names
        next(reader)  # jersey numbers
        header = next(reader)
    except StopIteration:
        return []
    columns = [(i, name) for i, name in enumerate(header) if name.startswith("Player")]

    samples = []
    for row in reader:
        if len(row) < len(header) - 1:
            continue
        try:
            frame = int(row[1])
        except ValueError:
            continue
        if frame % sample_every:
            continue
        players = {}
        for i, name in columns:
            x, y = _coord(row[i]), _coord(row[i + 1]) if i + 1 < len(row) else None
            if x is not None and y is not None:
                players[name] = (x, y)
        samples.append(TrackingSample(row[0], frame, players))
    return samples


# --- Possession -------------------------------------------------------------


class PossessionTimeline:
    """Which team has the ball at a frame, from the synchronized event file."""

    def __init__(self, event_rows: Iterable[dict[str, str]]) -> None:
        changes: list[tuple[int, str | None]] = []
        for row in event_rows:
            kind = (row.get("Type") or "").upper()
            team = row.get("Team")
            try:
                frame = int(row["Start Frame"])
            except (KeyError, ValueError):
                continue
            if kind in ("PASS", "SHOT", "RECOVERY", "SET PIECE"):
                changes.append((frame, team))
            elif kind == "BALL LOST":
                changes.append((frame, "Away" if team == "Home" else "Home"))
            elif kind == "BALL OUT":
                changes.append((frame, None))
        changes.sort(key=lambda c: c[0])
        self._frames = [f for f, _ in changes]
        self._owners = [o for _, o in changes]

    def owner(self, frame: int) -> str | None:
        i = bisect.bisect_right(self._frames, frame) - 1
        if i < 0 or frame - self._frames[i] > POSSESSION_STALE_FRAMES:
            return None
        return self._owners[i]


# --- Shape ------------------------------------------------------------------------


def _oriented(position: Position, attacks_right: bool) -> Position:
    x, y = position
    if not attacks_right:
        x, y = 1 - x, 1 - y
    return x * PITCH_LENGTH_M, y * PITCH_WIDTH_M


def goalkeeper(samples: Sequence[TrackingSample], direction: dict[str, bool]) -> str | None:
    """The regular player with the deepest average position."""
    totals: dict[str, list[float]] = {}
    for s in samples:
        for name, pos in s.players.items():
            totals.setdefault(name, []).append(_oriented(pos, direction[s.period])[0])
    regulars = {
        n: sum(xs) / len(xs) for n, xs in totals.items() if len(xs) >= STARTER_SHARE * len(samples)
    }
    return min(regulars, key=regulars.__getitem__) if regulars else None


def infer_formation(positions: Sequence[Position]) -> str | None:
    """Closest line pattern for ten outfield average positions (metres)."""
    if len(positions) != 10:
        return None
    depths = sorted(x for x, _ in positions)
    best: tuple[float, str] | None = None
    for name, lines in FORMATION_LINES.items():
        spread, start = 0.0, 0
        for size in lines:
            line = depths[start : start + size]
            mean = sum(line) / size
            spread += sum((d - mean) ** 2 for d in line)
            start += size
        cost = spread / 10 + EXTRA_LINE_PENALTY_M2 * (len(lines) - 3)
        if best is None or cost < best[0]:
            best = (cost, name)
    return best[1] if best else None


@dataclass(frozen=True)
class TrackingShape:
    features: dict[str, float | None]
    formation: str | None


def team_shape(
    samples: Sequence[TrackingSample],
    team: str,
    direction: dict[str, bool],
    possession: PossessionTimeline,
) -> TrackingShape:
    """`direction` maps period -> whether `team` attacks toward x=1."""
    gk = goalkeeper(samples, direction)
    line, length, width = [], [], []
    first_half: dict[str, list[Position]] = {}
    first_half_samples = 0

    for s in samples:
        owner = possession.owner(s.frame)
        if owner is None or owner == team or s.period not in direction:
            continue
        outfield = {n: _oriented(p, direction[s.period]) for n, p in s.players.items() if n != gk}
        if len(outfield) < MIN_OUTFIELD_PLAYERS:
            continue
        xs = sorted(x for x, _ in outfield.values())
        ys = [y for _, y in outfield.values()]
        line.append(sum(xs[:4]) / 4)
        length.append(xs[-1] - xs[0])
        width.append(max(ys) - min(ys))
        if s.period == "1":
            first_half_samples += 1
            for n, p in outfield.items():
                first_half.setdefault(n, []).append(p)

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    starters = sorted(first_half, key=lambda n: len(first_half[n]), reverse=True)[:10]
    starters = [n for n in starters if len(first_half[n]) >= STARTER_SHARE * first_half_samples]
    averages = [
        (
            sum(x for x, _ in first_half[n]) / len(first_half[n]),
            sum(y for _, y in first_half[n]) / len(first_half[n]),
        )
        for n in starters
    ]

    return TrackingShape(
        features={
            "defensive_line_height_m": mean(line),
            "block_length_m": mean(length),
            "block_width_m": mean(width),
        },
        formation=infer_formation(averages),
    )
