from datetime import datetime
from typing import Annotated

from pydantic import Field, model_validator

from .base import Contract
from .enums import (
    AttackFocus,
    Formation,
    Level,
    MatchPhase,
    Mentality,
    PitchSide,
    PlayerRole,
    TeamId,
    Tempo,
)

Rating = Annotated[int, Field(ge=0, le=100)]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]


class TacticalSettings(Contract):
    formation: Formation
    mentality: Mentality
    pressing: Level
    defensive_line: Level
    attack_focus: AttackFocus
    tempo: Tempo


class PlayerSkills(Contract):
    passing: Rating
    shooting: Rating
    defending: Rating
    pace: Rating
    goalkeeping: Rating = 0


class Player(Contract):
    player_id: str
    team_id: TeamId
    name: str
    number: Annotated[int, Field(ge=1, le=99)]
    role: PlayerRole
    skills: PlayerSkills
    stamina: Fraction = 1.0
    available: bool = True


class Team(Contract):
    team_id: TeamId
    name: str
    coach_id: str
    coach_name: str
    side: PitchSide
    tactics: TacticalSettings
    players: list[Player]


class TeamStats(Contract):
    possession_pct: Annotated[float, Field(ge=0.0, le=100.0)] = 0.0
    shots: int = 0
    shots_on_target: int = 0
    turnovers: int = 0
    pressing_successes: int = 0


class Score(Contract):
    blue: Annotated[int, Field(ge=0)] = 0
    red: Annotated[int, Field(ge=0)] = 0


class MatchState(Contract):
    """Authoritative match state. Only the simulator produces this."""

    match_id: str
    seed: int
    phase: MatchPhase
    half: Annotated[int, Field(ge=1, le=2)] | None = None
    step: Annotated[int, Field(ge=0)] = 0
    steps_per_half: Annotated[int, Field(ge=2, le=90)] = 20
    clock_minute: Annotated[int, Field(ge=0, le=120)] = 0
    score: Score
    stats: dict[TeamId, TeamStats]
    teams: list[Team]
    state_version: Annotated[int, Field(ge=0)]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _two_opposing_teams(self) -> "MatchState":
        if len(self.teams) != 2:
            raise ValueError("a match has exactly two teams")
        if {t.team_id for t in self.teams} != set(TeamId):
            raise ValueError("teams must be blue and red")
        if {t.side for t in self.teams} != set(PitchSide):
            raise ValueError("teams must occupy opposite sides")
        return self
