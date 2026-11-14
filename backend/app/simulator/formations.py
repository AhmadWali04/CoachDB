"""Starting-shape templates (PRD §5.2). Positions are normalized 0..100 on
both axes, for a team defending y=0 and attacking toward y=100 (frame
contract, `schemas/frame.py`); `starting_positions` mirrors this for a
`bottom`-side team so it defends y=100 instead.

Abstract roster only -- no attempt at realistic professional positioning,
just enough shape for pressing/defensive-line/attack-focus to mean
something visually (CLAUDE.md: label it a simplified tactical simulator).
"""

from __future__ import annotations

from app.schemas import Formation, PitchSide, PlayerRole

# (role, x, y) for all 11 starters, GK first.
FORMATION_LAYOUTS: dict[Formation, list[tuple[PlayerRole, float, float]]] = {
    Formation.F433: [
        (PlayerRole.GK, 50, 5),
        (PlayerRole.DF, 15, 22),
        (PlayerRole.DF, 35, 18),
        (PlayerRole.DF, 65, 18),
        (PlayerRole.DF, 85, 22),
        (PlayerRole.MF, 30, 40),
        (PlayerRole.MF, 50, 38),
        (PlayerRole.MF, 70, 40),
        (PlayerRole.FW, 20, 55),
        (PlayerRole.FW, 50, 58),
        (PlayerRole.FW, 80, 55),
    ],
    Formation.F4231: [
        (PlayerRole.GK, 50, 5),
        (PlayerRole.DF, 15, 22),
        (PlayerRole.DF, 35, 18),
        (PlayerRole.DF, 65, 18),
        (PlayerRole.DF, 85, 22),
        (PlayerRole.MF, 35, 35),
        (PlayerRole.MF, 65, 35),
        (PlayerRole.MF, 20, 50),
        (PlayerRole.MF, 50, 48),
        (PlayerRole.MF, 80, 50),
        (PlayerRole.FW, 50, 60),
    ],
    Formation.F442: [
        (PlayerRole.GK, 50, 5),
        (PlayerRole.DF, 15, 22),
        (PlayerRole.DF, 35, 18),
        (PlayerRole.DF, 65, 18),
        (PlayerRole.DF, 85, 22),
        (PlayerRole.MF, 15, 42),
        (PlayerRole.MF, 38, 40),
        (PlayerRole.MF, 62, 40),
        (PlayerRole.MF, 85, 42),
        (PlayerRole.FW, 40, 58),
        (PlayerRole.FW, 60, 58),
    ],
}


def starting_positions(
    formation: Formation, side: PitchSide
) -> list[tuple[PlayerRole, float, float]]:
    layout = FORMATION_LAYOUTS[formation]
    if side == PitchSide.TOP:
        return list(layout)
    return [(role, x, 100 - y) for role, x, y in layout]
