"""Deterministic soccer simulator (PRD §5). The only source of match truth;
see CLAUDE.md principle 1."""

from .engine import MatchSimulator, SimulationResult, run_match
from .roster import build_team

__all__ = ["MatchSimulator", "SimulationResult", "build_team", "run_match"]
