"""Formation shapes -> on-pitch positions (frame contract coordinates).

Each team is laid out in its own frame: depth 0 = own goal line, 100 =
opponent's; lateral 0 = its left touchline, 100 = its right. `to_pitch`
converts to the shared 0..100 screen coordinates (`schemas/frame.py`): the
`top` team attacks toward y=100, so its left touchline is screen-right.
"""

from __future__ import annotations

import random

from app.schemas import AttackFocus, Formation, Level, Mentality, PitchSide, TacticalSettings

# (depth, lateral, line) per player index; index 0 is the goalkeeper.
# line: 0 = GK, 1 = defence, 2 = midfield, 3 = attack.
_BACK_FOUR = [(21, 14, 1), (19, 38, 1), (19, 62, 1), (21, 86, 1)]
TEMPLATES: dict[Formation, list[tuple[float, float, int]]] = {
    Formation.F433: [
        (5, 50, 0),
        *_BACK_FOUR,
        (41, 30, 2),
        (38, 50, 2),
        (41, 70, 2),
        (62, 18, 3),
        (66, 50, 3),
        (62, 82, 3),
    ],
    Formation.F4231: [
        (5, 50, 0),
        *_BACK_FOUR,
        (35, 38, 2),
        (35, 62, 2),
        (52, 50, 2),
        (53, 18, 3),
        (66, 50, 3),
        (53, 82, 3),
    ],
    Formation.F442: [
        (5, 50, 0),
        *_BACK_FOUR,
        (41, 38, 2),
        (41, 62, 2),
        (43, 14, 2),
        (43, 86, 2),
        (63, 40, 3),
        (63, 60, 3),
    ],
}

LINE_SHIFT = {Level.LOW: -7.0, Level.MEDIUM: 0.0, Level.HIGH: 8.0}
MENTALITY_SHIFT = {Mentality.DEFENSIVE: -5.0, Mentality.BALANCED: 0.0, Mentality.ATTACKING: 5.0}
FOCUS_LANE = {AttackFocus.LEFT: 24.0, AttackFocus.MIDDLE: 50.0, AttackFocus.RIGHT: 76.0}


def line_of(formation: Formation, index: int) -> int:
    return TEMPLATES[formation][index][2]


def _clamp(v: float, lo: float = 1.0, hi: float = 99.0) -> float:
    return max(lo, min(hi, v))


def team_positions(
    tactics: TacticalSettings,
    player_ids: list[str],
    *,
    in_possession: bool,
    ball_depth: float,
    ball_lateral: float,
    rng: random.Random,
) -> dict[str, tuple[float, float]]:
    """Positions in the team's own frame (depth, lateral)."""
    template = TEMPLATES[tactics.formation]
    out: dict[str, tuple[float, float]] = {}
    for index, pid in enumerate(player_ids):
        depth, lateral, line = template[index]
        if line == 0:
            out[pid] = (_clamp(depth + (ball_depth - 50) * 0.06, 2, 14), 50 + rng.gauss(0, 1))
            continue
        depth += LINE_SHIFT[tactics.defensive_line] * (1.0 if line == 1 else 0.6)
        depth += MENTALITY_SHIFT[tactics.mentality]
        if in_possession:
            depth += 9 if line < 3 else 6
            lateral = 50 + (lateral - 50) * 1.12
            if line == 3:
                lateral += (FOCUS_LANE[tactics.attack_focus] - 50) * 0.25
        else:
            depth -= 4
            lateral = 50 + (lateral - 50) * 0.85
            if tactics.pressing is Level.HIGH and ball_depth > 55 and line >= 2:
                depth += 9
            elif tactics.pressing is Level.LOW:
                depth -= 4
        # The whole block slides toward the ball.
        depth += (ball_depth - 45) * 0.28
        lateral += (ball_lateral - lateral) * 0.22
        out[pid] = (
            _clamp(depth + rng.gauss(0, 1.2), 3, 97),
            _clamp(lateral + rng.gauss(0, 1.2)),
        )
    return out


def to_pitch(side: PitchSide, depth: float, lateral: float) -> tuple[float, float]:
    """Team frame -> screen frame (x, y), both 0..100."""
    if side is PitchSide.TOP:
        return round(100 - lateral, 2), round(depth, 2)
    return round(lateral, 2), round(100 - depth, 2)
