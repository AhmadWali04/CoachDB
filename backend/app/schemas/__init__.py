"""Shared contract. Changes here need a CHECKLIST.md Handoff log entry."""

from .action import Action
from .api import (
    Briefing,
    CreateMatchRequest,
    ErrorResponse,
    HealthResponse,
    InjectCrashRequest,
    InjectCrashResponse,
)
from .coach import (
    AnalystReport,
    CoachDecision,
    LikelyAdjustment,
    Observation,
    ObservedTactics,
    OpponentPrediction,
    ScoutReport,
    TacticalPlan,
)
from .enums import *  # noqa: F403
from .event import MatchEvent
from .frame import BallPosition, Frame, FramesPage, PlayerPosition
from .match import (
    MatchState,
    Player,
    PlayerSkills,
    Score,
    TacticalSettings,
    Team,
    TeamStats,
)

__all__ = [
    "Action",
    "AnalystReport",
    "BallPosition",
    "Briefing",
    "CoachDecision",
    "CreateMatchRequest",
    "ErrorResponse",
    "Frame",
    "FramesPage",
    "HealthResponse",
    "InjectCrashRequest",
    "InjectCrashResponse",
    "LikelyAdjustment",
    "MatchEvent",
    "MatchState",
    "Observation",
    "ObservedTactics",
    "OpponentPrediction",
    "Player",
    "PlayerPosition",
    "PlayerSkills",
    "ScoutReport",
    "Score",
    "TacticalPlan",
    "TacticalSettings",
    "Team",
    "TeamStats",
]
