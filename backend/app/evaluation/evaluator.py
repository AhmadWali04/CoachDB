"""Deterministic evaluator (PRD §12). Independent of both coaches.

Every number comes from stored structured records: match state, events,
persisted coach decisions, the action ledger and the simulator's own count of
applied effects. The same records always give the same metrics.

Prediction accuracy is a documented heuristic: a prediction counts as correct
if its text names at least one tactic the rival actually changed (by keyword),
or, when the rival changed nothing, if it predicted no change.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.coaches.context import METRIC_NAMES
from app.schemas import (
    Action,
    ActionStatus,
    CoachDecision,
    EventType,
    MatchEvent,
    MatchState,
    TeamId,
)
from app.schemas.evaluation import CoachMetrics, HalfDelta, MatchResult

KEYWORDS: dict[str, tuple[str, ...]] = {
    "formation": ("formation", "4-3-3", "4-2-3-1", "4-4-2", "shape"),
    "mentality": ("attack", "defens", "mentality", "conservative", "aggress"),
    "pressing": ("press",),
    "defensive_line": ("line", "deeper", "drop", "block", "higher up", "push up"),
    "attack_focus": ("left", "right", "middle", "central", "wing", "flank", "channel"),
    "tempo": ("tempo", "pace", "quicker", "faster", "slower", "speed"),
}
NO_CHANGE = ("no change", "unchanged", "same shape", "stick with", "no confident")


@dataclass(frozen=True)
class MatchRecords:
    state: MatchState
    events: Sequence[MatchEvent]
    decisions: dict[TeamId, CoachDecision | None]
    actions: Sequence[Action]
    effects: dict[str, int]  # action_id -> times the simulator applied it
    latency_ms: dict[TeamId, float]
    sides_swapped: bool


def rival_of(team: TeamId) -> TeamId:
    return TeamId.RED if team is TeamId.BLUE else TeamId.BLUE


def changed_dimensions(events: Sequence[MatchEvent], team: TeamId) -> set[str]:
    changed: set[str] = set()
    for e in events:
        if e.type is EventType.TACTICAL_CHANGE and e.team_id is team:
            before, after = e.details.get("from", {}), e.details.get("to", {})
            changed |= {k for k in after if before.get(k) != after.get(k)}
    return changed


def prediction_correct(decision: CoachDecision | None, rival_changes: set[str]) -> bool:
    if decision is None:
        return False
    text = decision.plan.opponent_prediction.likely_change.lower()
    if not rival_changes:
        return any(k in text for k in NO_CHANGE)
    return any(any(k in text for k in KEYWORDS[dim]) for dim in rival_changes)


def evidence_grounding(decision: CoachDecision | None, events: Sequence[MatchEvent]) -> float:
    if decision is None:
        return 0.0
    allowed = {e.event_id for e in events} | {f"metric:{m}" for m in METRIC_NAMES}
    allowed |= set(decision.scouting.closest_style_profile_ids)
    cited: list[str] = []
    for report in (decision.analysis, decision.scouting, decision.plan):
        for name in ("own_strengths", "own_weaknesses", "fatigue_concerns", "patterns"):
            for obs in getattr(report, name, []):
                cited += obs.evidence
    cited += [r for adj in decision.scouting.likely_adjustments for r in adj.evidence]
    cited += decision.plan.opponent_prediction.evidence
    grounded = [r for r in cited if r in allowed or r.startswith("experience:")]
    return len(grounded) / len(cited) if cited else 0.0


def half_delta(events: Sequence[MatchEvent], team: TeamId) -> HalfDelta:
    def count(half: int, kinds: tuple[EventType, ...], acting: TeamId) -> int:
        return sum(1 for e in events if e.half == half and e.type in kinds and e.team_id is acting)

    shots = (EventType.SHOT,)
    # A turnover/pressing success is recorded on the team that won the ball.
    lost = (EventType.TURNOVER, EventType.PRESSING_SUCCESS)
    return HalfDelta(
        shots=count(2, shots, team) - count(1, shots, team),
        turnovers=count(2, lost, rival_of(team)) - count(1, lost, rival_of(team)),
        pressing_successes=count(2, (EventType.PRESSING_SUCCESS,), team)
        - count(1, (EventType.PRESSING_SUCCESS,), team),
    )


def match_result(records: MatchRecords) -> MatchResult:
    s = records.state
    return MatchResult(
        match_id=s.match_id,
        seed=s.seed,
        sides_swapped=records.sides_swapped,
        score={TeamId.BLUE: s.score.blue, TeamId.RED: s.score.red},
        tactical_impact={t: half_delta(records.events, t) for t in TeamId},
    )


def coach_metrics(matches: Sequence[MatchRecords], team: TeamId) -> CoachMetrics:
    n = len(matches) or 1
    predictions = valid = grounding = latency = 0.0
    attempted = verified = once = 0
    wins = draws = losses = goal_diff = 0
    for m in matches:
        decision = m.decisions.get(team)
        predictions += prediction_correct(decision, changed_dimensions(m.events, rival_of(team)))
        valid += decision is not None and not decision.used_fallback
        grounding += evidence_grounding(decision, m.events)
        latency += m.latency_ms.get(team, 0.0)
        mine = [a for a in m.actions if a.team_id is team]
        attempted += len(mine)
        done = [a for a in mine if a.status is ActionStatus.VERIFIED]
        verified += len(done)
        once += sum(1 for a in done if m.effects.get(a.action_id, 0) == 1)
        own, other = (
            (m.state.score.blue, m.state.score.red)
            if team is TeamId.BLUE
            else (m.state.score.red, m.state.score.blue)
        )
        wins += own > other
        draws += own == other
        losses += own < other
        goal_diff += own - other
    return CoachMetrics(
        prediction_accuracy=round(predictions / n, 3),
        decision_validity=round(valid / n, 3),
        execution_reliability=round(verified / attempted, 3) if attempted else 0.0,
        recovery_correctness=round(once / verified, 3) if verified else 0.0,
        evidence_grounding=round(grounding / n, 3),
        avg_decision_latency_ms=round(latency / n, 1),
        wins=wins,
        draws=draws,
        losses=losses,
        goal_difference=goal_diff,
    )
