"""Coach agent outputs (AGENTS.md §3–4, PRD §6)."""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from .base import Contract
from .enums import (
    AttackFocus,
    Formation,
    Level,
    Mentality,
    TeamId,
    Tempo,
)
from .match import TacticalSettings

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
Evidence = Annotated[
    list[str],
    Field(min_length=1, description="Event IDs, `metric:<name>`, or `profile:<id>`."),
]


class Observation(Contract):
    observation: str
    evidence: Evidence


class AnalystReport(Contract):
    match_id: str
    team_id: TeamId
    state_version: int
    summary: str
    own_strengths: Annotated[list[Observation], Field(max_length=3)] = []
    own_weaknesses: Annotated[list[Observation], Field(max_length=3)] = []
    fatigue_concerns: list[Observation] = []
    uncertainties: list[str] = []


class ObservedTactics(Contract):
    """What the scout believes the rival is doing. Every field is optional."""

    formation: Formation | None = None
    mentality: Mentality | None = None
    pressing: Level | None = None
    defensive_line: Level | None = None
    attack_focus: AttackFocus | None = None
    tempo: Tempo | None = None


class LikelyAdjustment(Contract):
    change: str
    confidence: Confidence
    evidence: Evidence


class ScoutReport(Contract):
    match_id: str
    team_id: TeamId = Field(description="The coach this report belongs to, not the rival.")
    rival_team_id: TeamId
    state_version: int
    observed_tactics: ObservedTactics
    patterns: list[Observation] = []
    closest_style_profile_ids: list[str] = []
    likely_adjustments: list[LikelyAdjustment] = []
    uncertainties: list[str] = []


class OpponentPrediction(Contract):
    likely_change: str
    confidence: Confidence
    evidence: Evidence


class TacticalPlan(Contract):
    match_id: str
    team_id: TeamId
    based_on_state_version: int
    plan: TacticalSettings
    opponent_prediction: OpponentPrediction
    primary_objective: str
    expected_effects: list[str] = []
    risks: list[str] = []
    success_indicators: list[str] = []
    rationale: str
    voice_script: Annotated[str, Field(max_length=900)]


class CoachDecision(Contract):
    decision_id: str
    match_id: str
    team_id: TeamId
    coach_id: str
    analysis: AnalystReport
    scouting: ScoutReport
    plan: TacticalPlan
    used_fallback: bool = False
    created_at: datetime
