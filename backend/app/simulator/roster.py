"""Fixed, fictional MVP rosters (PRD §5.1). No real teams or players."""

from __future__ import annotations

from app.schemas import (
    AttackFocus,
    Formation,
    Level,
    Mentality,
    PitchSide,
    Player,
    PlayerRole,
    PlayerSkills,
    TacticalSettings,
    Team,
    TeamId,
    Tempo,
)

# Index 0 is the goalkeeper, 1-4 the back four, 5-10 midfield and attack.
ROLES = (PlayerRole.GK, *[PlayerRole.DF] * 4, *[PlayerRole.MF] * 3, *[PlayerRole.FW] * 3)

_NAMES = {
    TeamId.BLUE: (
        "Okafor",
        "Lindqvist",
        "Brennan",
        "Sato",
        "Marchetti",
        "Duarte",
        "Holloway",
        "Achterberg",
        "Nkemelu",
        "Varga",
        "Castell",
    ),
    TeamId.RED: (
        "Ferreira",
        "Kowal",
        "Ashdown",
        "Ilunga",
        "Moreau",
        "Takeda",
        "Rourke",
        "Benali",
        "Strand",
        "Quintero",
        "Vesely",
    ),
}

# Blue passes better; Red defends better. Halftime plans decide who exploits it.
_BASE = {
    TeamId.BLUE: {"passing": 74, "shooting": 68, "defending": 64, "pace": 70},
    TeamId.RED: {"passing": 66, "shooting": 66, "defending": 73, "pace": 69},
}
_ROLE_TILT = {
    PlayerRole.GK: {"passing": -20, "shooting": -45, "defending": -10, "pace": -15},
    PlayerRole.DF: {"passing": -4, "shooting": -18, "defending": 10, "pace": 0},
    PlayerRole.MF: {"passing": 8, "shooting": -2, "defending": 0, "pace": 0},
    PlayerRole.FW: {"passing": 0, "shooting": 14, "defending": -14, "pace": 6},
}

DEFAULT_TACTICS = {
    TeamId.BLUE: TacticalSettings(
        formation=Formation.F433,
        mentality=Mentality.BALANCED,
        pressing=Level.HIGH,
        defensive_line=Level.HIGH,
        attack_focus=AttackFocus.MIDDLE,
        tempo=Tempo.NORMAL,
    ),
    TeamId.RED: TacticalSettings(
        formation=Formation.F442,
        mentality=Mentality.BALANCED,
        pressing=Level.LOW,
        defensive_line=Level.LOW,
        attack_focus=AttackFocus.RIGHT,
        tempo=Tempo.SLOW,
    ),
}

TEAM_NAMES = {TeamId.BLUE: "Lakeside Blue", TeamId.RED: "Ironvale Red"}
COACH_NAMES = {TeamId.BLUE: "Blue Coach (AI)", TeamId.RED: "Red Coach (AI)"}


def _clamp(value: int) -> int:
    return max(1, min(99, value))


def build_team(team_id: TeamId, side: PitchSide) -> Team:
    players = []
    for i, role in enumerate(ROLES):
        base, tilt = _BASE[team_id], _ROLE_TILT[role]
        # Small fixed per-player variation so players are distinguishable.
        wobble = ((i * 7) % 5) - 2
        skills = {k: _clamp(base[k] + tilt[k] + wobble) for k in base}
        players.append(
            Player(
                player_id=f"{team_id.value}_{i + 1}",
                team_id=team_id,
                name=_NAMES[team_id][i],
                number=i + 1,
                role=role,
                skills=PlayerSkills(**skills, goalkeeping=78 if role is PlayerRole.GK else 5),
            )
        )
    return Team(
        team_id=team_id,
        name=TEAM_NAMES[team_id],
        coach_id=f"coach_{team_id.value}",
        coach_name=COACH_NAMES[team_id],
        side=side,
        tactics=DEFAULT_TACTICS[team_id],
        players=players,
    )


def default_teams() -> list[Team]:
    return [build_team(TeamId.BLUE, PitchSide.TOP), build_team(TeamId.RED, PitchSide.BOTTOM)]
