"""The only match input a coach agent may receive (guardrail, PRD §7).

Built by `app.guardrails.build_coach_view`. It contains the coach's own team in
full, and only publicly observable information about the rival. It never
contains the rival's tactics (other than the formation seen at kickoff),
stamina, decisions, plans, predictions, briefings, or memory. The scout infers
the rest from the kickoff formation and public events.
"""

from typing import Annotated

from pydantic import Field

from .base import Contract
from .enums import Formation, MatchPhase, PitchSide, PlayerRole, TeamId
from .event import MatchEvent
from .match import Score, Team, TeamStats


class PublicPlayer(Contract):
    player_id: str
    name: str
    number: int
    role: PlayerRole
    available: bool


class PublicTeam(Contract):
    """What anyone watching the match can see about a team."""

    team_id: TeamId
    name: str
    coach_name: str
    side: PitchSide
    kickoff_formation: Formation = Field(
        description="The formation the team lined up in at kickoff, visible to anyone watching."
    )
    players: list[PublicPlayer]


class CoachView(Contract):
    match_id: str
    team_id: TeamId
    rival_team_id: TeamId
    memory_namespace: str
    snapshot_state_version: Annotated[
        int, Field(description="Both coaches decide on this same halftime snapshot.")
    ]
    phase: MatchPhase
    score: Score
    stats: dict[TeamId, TeamStats]
    own_team: Team
    rival_team: PublicTeam
    public_events: list[MatchEvent]
