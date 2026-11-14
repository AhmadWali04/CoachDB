"""Request/response bodies that exist only at the HTTP boundary."""

from typing import Annotated

from pydantic import Field

from .base import Contract
from .enums import AudioStatus, CrashPoint, TeamId


class CreateMatchRequest(Contract):
    seed: int | None = Field(default=None, description="Random seed; generated if omitted.")
    steps_per_half: Annotated[int, Field(ge=2, le=90)] = 20


class Briefing(Contract):
    """A coach's approved halftime briefing. The transcript is always present."""

    briefing_id: str
    match_id: str
    team_id: TeamId
    coach_id: str
    coach_name: str
    transcript: str
    audio_status: AudioStatus
    audio_url: str | None = None


class InjectCrashRequest(Contract):
    match_id: str
    point: CrashPoint = CrashPoint.AFTER_SUBMIT_BEFORE_VERIFY


class InjectCrashResponse(Contract):
    match_id: str
    point: CrashPoint
    armed: bool


class HealthResponse(Contract):
    status: str
    version: str


class ErrorResponse(Contract):
    detail: str
