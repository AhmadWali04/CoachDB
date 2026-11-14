"""AI coaches: Match Analyst, Opposition Scout, Tactical Coach (PRD §6)."""

from .agents import Efforts, safe_default_plan
from .coach import Coach, CoachResult
from .llm import ClaudeStructuredLLM, LLMUnavailable, StructuredLLM

__all__ = [
    "ClaudeStructuredLLM",
    "Coach",
    "CoachResult",
    "Efforts",
    "LLMUnavailable",
    "StructuredLLM",
    "safe_default_plan",
]
