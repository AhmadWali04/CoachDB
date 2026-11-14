"""Fixed abstract roster and player attributes (PRD §5.1: "fixed roster and
player attributes for the MVP"). Only tactics and stamina vary; skills
never do, so every match that starts fresh looks the same until the RNG
and stamina decay diverge it.
"""

from __future__ import annotations

from app.schemas import (
    PitchSide,
    Player,
    PlayerRole,
    PlayerSkills,
    TacticalSettings,
    Team,
    TeamId,
    TeamStats,
)

from .formations import starting_positions

_BASELINE_SKILLS: dict[PlayerRole, PlayerSkills] = {
    PlayerRole.GK: PlayerSkills(passing=50, shooting=20, defending=55, pace=50, goalkeeping=75),
    PlayerRole.DF: PlayerSkills(passing=55, shooting=25, defending=75, pace=60, goalkeeping=0),
    PlayerRole.MF: PlayerSkills(passing=72, shooting=55, defending=55, pace=62, goalkeeping=0),
    PlayerRole.FW: PlayerSkills(passing=58, shooting=75, defending=30, pace=72, goalkeeping=0),
}

TEAM_NAMES: dict[TeamId, str] = {TeamId.BLUE: "Blue", TeamId.RED: "Red"}


def build_team(team_id: TeamId, side: PitchSide, tactics: TacticalSettings) -> Team:
    layout = starting_positions(tactics.formation, side)
    players = [
        Player(
            player_id=f"{team_id.value}_{number}",
            team_id=team_id,
            name=f"{TEAM_NAMES[team_id]} {role.value}{number}",
            number=number,
            role=role,
            skills=_BASELINE_SKILLS[role],
            stamina=1.0,
            available=True,
        )
        for number, (role, _x, _y) in enumerate(layout, start=1)
    ]
    return Team(
        team_id=team_id,
        name=TEAM_NAMES[team_id],
        coach_id=f"coach_{team_id.value}",
        coach_name=f"{TEAM_NAMES[team_id]} Coach",
        side=side,
        tactics=tactics,
        players=players,
    )


def initial_team_stats() -> TeamStats:
    return TeamStats()
