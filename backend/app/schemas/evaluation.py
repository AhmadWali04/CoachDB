"""Evaluation harness contract (PRD §12). Matches frontend/src/types/evaluation.ts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .base import Contract
from .enums import TeamId

Rate = Annotated[float, Field(ge=0.0, le=1.0)]


class HalfDelta(Contract):
    """Second half minus first half, for one team."""

    shots: int
    turnovers: int
    pressing_successes: int


class MatchResult(Contract):
    match_id: str
    seed: int
    sides_swapped: bool
    score: dict[TeamId, int]
    tactical_impact: dict[TeamId, HalfDelta]


class CoachMetrics(Contract):
    prediction_accuracy: Rate
    decision_validity: Rate
    execution_reliability: Rate
    recovery_correctness: Rate
    evidence_grounding: Rate
    avg_decision_latency_ms: Annotated[float, Field(ge=0.0)]
    wins: int
    draws: int
    losses: int
    goal_difference: int


class EvaluationBatch(Contract):
    batch_id: str
    status: Literal["running", "done", "failed"]
    seeds: list[int]
    steps_per_half: int
    results: list[MatchResult]
    metrics: dict[TeamId, CoachMetrics]
    notes: list[str] = []


class RunEvaluationRequest(Contract):
    seeds: Annotated[list[int], Field(min_length=1, max_length=10)] = [1, 2]
    steps_per_half: Annotated[int, Field(ge=2, le=40)] = 10
