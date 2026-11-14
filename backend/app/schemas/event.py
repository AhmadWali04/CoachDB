from datetime import datetime
from typing import Annotated, Any

from pydantic import Field

from .base import Contract
from .enums import EventType, TeamId


class MatchEvent(Contract):
    """Append-only simulation event (PRD §5.4)."""

    event_id: str
    match_id: str
    schema_version: int = 1
    half: Annotated[int, Field(ge=1, le=2)]
    step: Annotated[int, Field(ge=0)]
    clock_minute: Annotated[int, Field(ge=0, le=120)]
    team_id: TeamId | None = None
    type: EventType
    player_ids: list[str] = Field(
        default_factory=list,
        description="Players involved, in order (e.g. passer then receiver).",
    )
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
