"""One team's AI coach: Analyst and Scout in parallel, then the Tactical Coach.

A coach's only match input is its own `CoachView`, and its memory lookups are
bound to its own team, so nothing from the rival's pipeline can reach it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.data import ExperienceHit, StyleHit
from app.guardrails import require_own_namespace
from app.schemas import CoachDecision, TeamId
from app.schemas.coach_view import CoachView

from .agents import Efforts, StyleSearch, run_analyst, run_scout, run_tactical_coach
from .llm import StructuredLLM
from .prompts import PERSONAS

ExperienceSearch = Callable[[CoachView], list[ExperienceHit]]


@dataclass(frozen=True)
class CoachResult:
    decision: CoachDecision
    styles: list[StyleHit]
    experiences: list[ExperienceHit]
    fallbacks: dict[str, bool] = field(default_factory=dict)


@dataclass
class Coach:
    team_id: TeamId
    coach_id: str
    llm: StructuredLLM
    style_search: StyleSearch | None = None
    experience_search: ExperienceSearch | None = None
    efforts: Efforts = field(default_factory=Efforts)

    def decide(self, view: CoachView) -> CoachResult:
        if view.team_id != self.team_id:
            raise ValueError(f"coach {self.team_id} was handed the {view.team_id} view")
        require_own_namespace(self.team_id, view.memory_namespace)
        persona = PERSONAS[self.team_id]

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"coach-{self.team_id}") as pool:
            analyst = pool.submit(run_analyst, view, self.llm, persona, self.efforts.analyst)
            scout = pool.submit(
                run_scout, view, self.llm, persona, self.style_search, self.efforts.scout
            )
            analysis, analyst_fallback = analyst.result()
            scouting, styles, scout_fallback = scout.result()

        experiences: list[ExperienceHit] = []
        if self.experience_search is not None:
            try:
                experiences = self.experience_search(view)
            except Exception:  # memory is a hint; its failure must not stop halftime
                experiences = []

        plan, plan_fallback = run_tactical_coach(
            view,
            analysis,
            scouting,
            styles,
            experiences,
            self.llm,
            persona,
            self.efforts.tactical,
        )
        decision = CoachDecision(
            decision_id=f"{view.match_id}:{self.team_id.value}:{uuid.uuid4().hex[:8]}",
            match_id=view.match_id,
            team_id=self.team_id,
            coach_id=self.coach_id,
            analysis=analysis,
            scouting=scouting,
            plan=plan,
            used_fallback=plan_fallback,
            created_at=datetime.now(UTC),
        )
        return CoachResult(
            decision,
            styles,
            experiences,
            {"analyst": analyst_fallback, "scout": scout_fallback, "tactical": plan_fallback},
        )
