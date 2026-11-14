"""Halftime: both coaches decide on the same sealed snapshot, then plans apply.

1. Freeze the halftime state and read the persisted first-half events.
2. Build each coach's `CoachView` (guardrail) from that one snapshot.
3. Run both coaches in parallel; neither sees the other's pipeline.
4. Persist each decision, submit its plan to `SealedHalftimePlans`.
5. Reveal both plans only when both are in, then hand them to the executor.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from app.coaches import Coach, CoachResult
from app.guardrails import SealedHalftimePlans, build_coach_view
from app.schemas import TacticalPlan, TeamId

from .service import MatchRun

logger = logging.getLogger(__name__)


class PlanExecutor(Protocol):
    def apply(self, run: MatchRun, plans: dict[TeamId, TacticalPlan]) -> None: ...


class DirectExecutor:
    """Applies revealed plans with stable, idempotent action IDs."""

    def apply(self, run: MatchRun, plans: dict[TeamId, TacticalPlan]) -> None:
        for team_id, plan in sorted(plans.items()):
            run.simulator.apply_tactics(
                f"{run.match_id}:{team_id.value}:halftime",
                team_id,
                plan.plan,
                plan.based_on_state_version,
            )


class CoachingHalftime:
    def __init__(self, coaches: dict[TeamId, Coach], executor: PlanExecutor | None = None):
        if set(coaches) != set(TeamId):
            raise ValueError("halftime needs one coach per team")
        self.coaches = coaches
        self.executor = executor or DirectExecutor()
        self.last_results: dict[str, dict[TeamId, CoachResult]] = {}

    def __call__(self, run: MatchRun) -> None:
        snapshot = run.simulator.state
        events = run.repository.get_events(run.match_id, limit=200)
        views = {team: build_coach_view(snapshot, events, team) for team in TeamId}
        sealed = SealedHalftimePlans(run.match_id, snapshot.state_version)

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="halftime") as pool:
            futures = {team: pool.submit(self.coaches[team].decide, views[team]) for team in TeamId}
            results = {team: future.result() for team, future in futures.items()}

        for team, result in results.items():
            run.repository.save_decision(result.decision)
            sealed.submit(team, result.decision.plan)
            logger.info(
                "coach decided",
                extra={"match_id": run.match_id, "team_id": team.value, **result.fallbacks},
            )
        self.last_results[run.match_id] = results
        self.executor.apply(run, sealed.reveal())
