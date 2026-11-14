"""Shared guardrails. Changes here need a CHECKLIST.md Handoff log entry."""

from .isolation import (
    GuardrailViolation,
    SealedHalftimePlans,
    build_coach_view,
    coach_namespace,
    require_own_namespace,
    rival_of,
)

__all__ = [
    "GuardrailViolation",
    "SealedHalftimePlans",
    "build_coach_view",
    "coach_namespace",
    "require_own_namespace",
    "rival_of",
]
