"""Frame contract for the tactical pitch (PRD §13.5).

Coordinate system (shared by backend and frontend):
- Top-down pitch, normalized to 0..100 on both axes.
- x: 0 = left touchline, 100 = right touchline (as seen on screen).
- y: 0 = top goal line, 100 = bottom goal line.
- The team with side `top` defends y=0 and attacks toward y=100.

Frames are produced only by the simulator. The frontend interpolates between
consecutive frames but never invents positions.
"""

from typing import Annotated

from pydantic import Field

from .base import Contract
from .enums import MatchPhase, TeamId
from .event import MatchEvent

Coord = Annotated[float, Field(ge=0.0, le=100.0)]


class PlayerPosition(Contract):
    player_id: str
    team_id: TeamId
    x: Coord
    y: Coord


class BallPosition(Contract):
    x: Coord
    y: Coord
    owner_player_id: str | None = None


class Frame(Contract):
    match_id: str
    seq: Annotated[int, Field(ge=0, description="Monotonic frame index across the match.")]
    half: Annotated[int, Field(ge=1, le=2)]
    step: Annotated[int, Field(ge=0)]
    clock_minute: Annotated[int, Field(ge=0, le=120)]
    phase: MatchPhase
    state_version: Annotated[int, Field(ge=0)]
    players: list[PlayerPosition]
    ball: BallPosition
    events: list[MatchEvent] = Field(
        default_factory=list, description="Events that happened during this step."
    )


class FramesPage(Contract):
    match_id: str
    frames: list[Frame]
    next_seq: int | None = Field(
        default=None, description="Pass as `from_seq` to get newer frames; null when finished."
    )
    phase: MatchPhase
    fixture: bool = Field(
        default=False,
        description="True when served from a recorded fixture rather than a live run.",
    )
