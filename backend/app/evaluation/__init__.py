"""Independent, deterministic evaluation harness (PRD §12)."""

from .batch import EvaluationRunner
from .evaluator import MatchRecords, coach_metrics, match_result

__all__ = ["EvaluationRunner", "MatchRecords", "coach_metrics", "match_result"]
