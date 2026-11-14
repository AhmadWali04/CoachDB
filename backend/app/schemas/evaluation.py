from typing import Annotated, Literal

from pydantic import Field

from .base import Contract
from .enums import TeamId
from .match import Score


class BatchRequest(Contract):
    seeds: Annotated[list[int], Field(min_length=1, max_length=10)] = [42, 43]
    steps_per_half: Annotated[int, Field(ge=2, le=90)] = 20


class MatchResult(Contract):
    match_id: str
    seed: int
    sides_swapped: bool
    score: Score


class CoachMetrics(Contract):
    prediction_accuracy: float = 0
    decision_validity: float = 0
    execution_reliability: float = 0
    recovery_correctness: float = 0
    evidence_grounding: float = 0
    avg_decision_latency_ms: float = 0
    shot_delta: float = 0
    goal_difference: float = 0


class EvaluationBatch(Contract):
    batch_id: str
    status: Literal["running", "complete", "failed"]
    results: list[MatchResult] = []
    metrics: dict[TeamId, CoachMetrics]
