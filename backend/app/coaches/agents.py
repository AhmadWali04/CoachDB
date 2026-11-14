"""Match Analyst, Opposition Scout and Tactical Coach (AGENTS.md §3-4, PRD §6).

The model fills only the judgment fields ("drafts"). IDs, team, rival and the
snapshot version are copied from the `CoachView`, so the model can't get them
wrong. Every evidence reference is checked against the IDs the coach was
given. If the model fails twice, each agent falls back to a safe answer and
says so, and the halftime flow records the fallback.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from app.data import ExperienceHit, StyleHit
from app.data.tactical_style import style_query_vector
from app.schemas import (
    AnalystReport,
    AttackFocus,
    Level,
    LikelyAdjustment,
    Mentality,
    Observation,
    ObservedTactics,
    OpponentPrediction,
    ScoutReport,
    TacticalPlan,
    TacticalSettings,
    Tempo,
)
from app.schemas.base import Contract
from app.schemas.coach_view import CoachView

from .context import allowed_evidence, render_experiences, render_styles, render_view
from .llm import LLMUnavailable, StructuredLLM
from .prompts import CoachPersona, analyst_system, scout_system, tactical_system


@dataclass(frozen=True)
class Efforts:
    analyst: str = "low"
    scout: str = "low"
    tactical: str = "medium"


# --- drafts: what the model writes -------------------------------------------


class AnalystDraft(Contract):
    summary: str
    own_strengths: list[Observation]
    own_weaknesses: list[Observation]
    fatigue_concerns: list[Observation]
    uncertainties: list[str]


class ScoutDraft(Contract):
    observed_tactics: ObservedTactics
    patterns: list[Observation]
    likely_adjustments: list[LikelyAdjustment]
    uncertainties: list[str]


class PlanDraft(Contract):
    plan: TacticalSettings
    opponent_prediction: OpponentPrediction
    primary_objective: str
    expected_effects: list[str]
    risks: list[str]
    success_indicators: list[str]
    rationale: str
    voice_script: str


def _cited(draft: BaseModel) -> list[str]:
    refs: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                item = getattr(value, name)
                if name == "evidence" and isinstance(item, list):
                    refs.extend(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(draft)
    return refs


def evidence_checker(allowed: set[str]) -> Callable[[BaseModel], list[str]]:
    def check(draft: BaseModel) -> list[str]:
        unknown = sorted({ref for ref in _cited(draft) if ref not in allowed})
        return [f"Unknown evidence ID: {ref}" for ref in unknown[:10]]

    return check


# --- Match Analyst -------------------------------------------------------------------


def run_analyst(
    view: CoachView, llm: StructuredLLM, persona: CoachPersona, effort: str = "low"
) -> tuple[AnalystReport, bool]:
    """Returns (report, used_fallback)."""
    try:
        draft = llm.complete(
            system=analyst_system(persona),
            prompt=f"Match data (JSON):\n{render_view(view)}\n\nWrite your analysis.",
            output=AnalystDraft,
            effort=effort,
            check=evidence_checker(allowed_evidence(view)),
        )
        fallback = False
    except LLMUnavailable as exc:
        draft = AnalystDraft(
            summary="Automated analysis unavailable; relying on match statistics only.",
            own_strengths=[],
            own_weaknesses=[],
            fatigue_concerns=[],
            uncertainties=[f"Analyst fallback: {exc}"],
        )
        fallback = True
    return (
        AnalystReport(
            match_id=view.match_id,
            team_id=view.team_id,
            state_version=view.snapshot_state_version,
            summary=draft.summary,
            own_strengths=draft.own_strengths[:3],
            own_weaknesses=draft.own_weaknesses[:3],
            fatigue_concerns=draft.fatigue_concerns,
            uncertainties=draft.uncertainties,
        ),
        fallback,
    )


# --- Opposition Scout ------------------------------------------------------------------

StyleSearch = Callable[[ObservedTactics], list[StyleHit]]


def run_scout(
    view: CoachView,
    llm: StructuredLLM,
    persona: CoachPersona,
    style_search: StyleSearch | None = None,
    effort: str = "low",
) -> tuple[ScoutReport, list[StyleHit], bool]:
    """Returns (report, matched historical styles, used_fallback)."""
    try:
        draft = llm.complete(
            system=scout_system(persona),
            prompt=f"Match data (JSON):\n{render_view(view)}\n\nWrite your scouting report.",
            output=ScoutDraft,
            effort=effort,
            check=evidence_checker(allowed_evidence(view)),
        )
        fallback = False
    except LLMUnavailable as exc:
        draft = ScoutDraft(
            observed_tactics=ObservedTactics(),
            patterns=[],
            likely_adjustments=[],
            uncertainties=[f"Scout fallback: {exc}"],
        )
        fallback = True

    # The kickoff formation is public fact, whatever the model wrote.
    observed = draft.observed_tactics.model_copy(
        update={"formation": view.rival_team.kickoff_formation}
    )
    styles: list[StyleHit] = []
    if style_search is not None and style_query_vector(observed) is not None:
        try:
            styles = style_search(observed)
        except Exception:  # memory is a hint; its failure must not stop halftime
            styles = []
    return (
        ScoutReport(
            match_id=view.match_id,
            team_id=view.team_id,
            rival_team_id=view.rival_team_id,
            state_version=view.snapshot_state_version,
            observed_tactics=observed,
            patterns=draft.patterns[:3],
            closest_style_profile_ids=[f"profile:{h.profile_id}" for h in styles],
            likely_adjustments=draft.likely_adjustments[:3],
            uncertainties=draft.uncertainties,
        ),
        styles,
        fallback,
    )


# --- Tactical Coach -----------------------------------------------------------------------


def safe_default_plan(view: CoachView, reason: str) -> TacticalPlan:
    """Balanced fallback (PRD §6.2): keep the formation, neutral settings."""
    return TacticalPlan(
        match_id=view.match_id,
        team_id=view.team_id,
        based_on_state_version=view.snapshot_state_version,
        plan=TacticalSettings(
            formation=view.own_team.tactics.formation,
            mentality=Mentality.BALANCED,
            pressing=Level.MEDIUM,
            defensive_line=Level.MEDIUM,
            attack_focus=AttackFocus.MIDDLE,
            tempo=Tempo.NORMAL,
        ),
        opponent_prediction=OpponentPrediction(
            likely_change="no confident prediction", confidence=0.0, evidence=["metric:score"]
        ),
        primary_objective="Stay compact and balanced while the coaching system recovers.",
        expected_effects=[],
        risks=["Plan chosen without analysis"],
        success_indicators=[],
        rationale=f"Safe balanced default used: {reason}.",
        voice_script=(
            "Same shape, everyone. Stay compact, keep the distances short, "
            "and look after the ball. We go again, together."
        ),
    )


def run_tactical_coach(
    view: CoachView,
    analysis: AnalystReport,
    scouting: ScoutReport,
    styles: Sequence[StyleHit],
    experiences: Sequence[ExperienceHit],
    llm: StructuredLLM,
    persona: CoachPersona,
    effort: str = "medium",
) -> tuple[TacticalPlan, bool]:
    """Returns (plan, used_fallback)."""
    prompt = "\n\n".join(
        [
            f"Match data (JSON):\n{render_view(view)}",
            f"Your Match Analyst's report (JSON):\n{analysis.model_dump_json()}",
            f"Your Opposition Scout's report (JSON):\n{scouting.model_dump_json()}",
            f"Similar historical styles (public data):\n{render_styles(styles)}",
            f"Your own past experiences:\n{render_experiences(experiences)}",
            "Choose the second-half plan and write the briefing.",
        ]
    )
    try:
        draft = llm.complete(
            system=tactical_system(persona),
            prompt=prompt,
            output=PlanDraft,
            effort=effort,
            check=_plan_checker(allowed_evidence(view, styles, experiences)),
        )
    except LLMUnavailable as exc:
        return safe_default_plan(view, str(exc)), True
    return (
        TacticalPlan(
            match_id=view.match_id,
            team_id=view.team_id,
            based_on_state_version=view.snapshot_state_version,
            **draft.model_dump(),
        ),
        False,
    )


def _plan_checker(allowed: set[str]) -> Callable[[BaseModel], list[str]]:
    evidence = evidence_checker(allowed)

    def check(draft: BaseModel) -> list[str]:
        problems = evidence(draft)
        script = getattr(draft, "voice_script", "")
        if not script.strip():
            problems.append("voice_script must not be empty")
        elif len(script) > 900:
            problems.append(f"voice_script is {len(script)} characters; keep it under 900")
        return problems

    return check
