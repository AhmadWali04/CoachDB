"""Seeded tactical match simulator: the source of match truth (PRD §5)."""

from .engine import (
    FRAMES_PER_STEP,
    ApplyResult,
    MatchSimulator,
    SimulatorError,
    StepOutput,
    new_match_state,
    simulate_match,
)

__all__ = [
    "FRAMES_PER_STEP",
    "ApplyResult",
    "MatchSimulator",
    "SimulatorError",
    "StepOutput",
    "new_match_state",
    "simulate_match",
]
