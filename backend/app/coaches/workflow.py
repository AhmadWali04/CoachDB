"""Independent, durable analyst → scout → tactical-coach subgraphs."""

import asyncio
import json
from datetime import datetime
from typing import TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from app.data import search_experiences, search_styles
from app.data.tactical_style import DIMENSIONS, EMBEDDING_MODEL, style_query_vector
from app.guardrails import require_own_namespace
from app.schemas import (
    AnalystReport,
    CoachDecision,
    Observation,
    ObservedTactics,
    OpponentPrediction,
    ScoutReport,
    TacticalPlan,
    TacticalSettings,
    TeamId,
)
from app.schemas.coach_view import CoachView


class Context(TypedDict, total=False):
    view: dict
    before: str
    analysis: dict
    scouting: dict
    memories: list[dict]
    decision: dict


class AsyncCollection:
    """Bounded adapter for the shared synchronous Mongo client."""

    def __init__(self, collection):
        self.collection = collection

    async def aggregate(self, pipeline):
        rows = await asyncio.to_thread(
            lambda: list(self.collection.aggregate(pipeline, maxTimeMS=1500))
        )

        async def cursor():
            for row in rows:
                yield row

        return cursor()


def balanced() -> TacticalSettings:
    return TacticalSettings(
        formation="4-3-3",
        mentality="balanced",
        pressing="medium",
        defensive_line="medium",
        attack_focus="middle",
        tempo="normal",
    )


def validate_plan(plan: TacticalPlan, view: CoachView, profiles=()):
    if (
        plan.match_id != view.match_id
        or plan.team_id != view.team_id
        or plan.based_on_state_version != view.snapshot_state_version
    ):
        raise ValueError("plan identity or snapshot mismatch")
    evidence = {e.event_id for e in view.public_events} | {
        "metric:shots",
        "metric:turnovers",
        "metric:pressing_successes",
        "metric:possession_pct",
        "metric:score",
        *[f"profile:{p}" for p in profiles],
    }
    if any(ref not in evidence for ref in plan.opponent_prediction.evidence):
        raise ValueError("prediction cites unknown evidence")
    return plan


class CoachWorkflow:
    def __init__(self, team_id: TeamId, checkpointer, database, settings):
        self.team_id, self.db, self.settings = TeamId(team_id), database, settings
        builder = StateGraph(Context)
        builder.add_node("analyst", self.analyze)
        builder.add_node("scout", self.scout)
        builder.add_node("coach", self.coach)
        builder.add_edge(START, "analyst")
        builder.add_edge("analyst", "scout")
        builder.add_edge("scout", "coach")
        builder.add_edge("coach", END)
        self.graph = builder.compile(checkpointer=checkpointer)

    def view(self, state):
        view = CoachView.model_validate(state["view"])
        if view.team_id != self.team_id:
            raise ValueError("cross-team graph invocation")
        require_own_namespace(self.team_id, view.memory_namespace)
        return view

    def run(self, view: CoachView, before: datetime) -> CoachDecision:
        require_own_namespace(self.team_id, view.memory_namespace)
        config = {"configurable": {"thread_id": f"{view.match_id}:{self.team_id.value}"}}
        prior = self.graph.get_state(config)
        if prior.values:
            if prior.values.get("decision"):
                return CoachDecision.model_validate(prior.values["decision"])
            result = self.graph.invoke(None, config)
        else:
            result = self.graph.invoke(
                {"view": view.model_dump(mode="json"), "before": before.isoformat()}, config
            )
        return CoachDecision.model_validate(result["decision"])

    def analyze(self, state):
        view = self.view(state)
        stats = view.stats[view.team_id]
        rival = view.stats[view.rival_team_id]
        report = AnalystReport(
            match_id=view.match_id,
            team_id=view.team_id,
            state_version=view.snapshot_state_version,
            summary=f"Created {stats.shots} shots; rival created {rival.shots}. "
            f"Possession {stats.possession_pct:.1f}% (metric:shots, metric:possession_pct).",
            own_strengths=[
                Observation(observation=f"Created {stats.shots} shots.", evidence=["metric:shots"])
            ],
            own_weaknesses=[
                Observation(
                    observation=f"Lost possession {stats.turnovers} times.",
                    evidence=["metric:turnovers"],
                )
            ],
            fatigue_concerns=[
                Observation(
                    observation=f"{p.name} stamina is {p.stamina:.2f}.",
                    evidence=[f"metric:stamina:{p.player_id}"],
                )
                for p in view.own_team.players
                if p.stamina < 0.8
            ],
            uncertainties=["Small first-half sample; tactical effects are estimates."],
        )
        return {"analysis": report.model_dump(mode="json")}

    def scout(self, state):
        view = self.view(state)
        observed = ObservedTactics(formation=view.rival_team.kickoff_formation)
        stats = view.stats[view.rival_team_id]
        if stats.pressing_successes >= 2:
            observed = ObservedTactics(formation=view.rival_team.kickoff_formation, pressing="high")
        vector = style_query_vector(observed)

        async def retrieve():
            styles = await search_styles(
                AsyncCollection(self.db.style_profiles),
                vector,
                embedding_model=EMBEDDING_MODEL,
                dimensions=DIMENSIONS,
                limit=3,
            )
            own_vector = style_query_vector(ObservedTactics(**view.own_team.tactics.model_dump()))
            memories = await search_experiences(
                view.team_id,
                AsyncCollection(self.db.coach_experiences),
                own_vector,
                namespace=view.memory_namespace,
                before=datetime.fromisoformat(state["before"]),
                embedding_model=EMBEDDING_MODEL,
                dimensions=DIMENSIONS,
                limit=3,
            )
            return styles, memories

        styles, memories = asyncio.run(retrieve())
        report = ScoutReport(
            match_id=view.match_id,
            team_id=view.team_id,
            rival_team_id=view.rival_team_id,
            state_version=view.snapshot_state_version,
            observed_tactics=observed,
            patterns=[
                Observation(
                    observation=f"Rival recorded {stats.pressing_successes} pressing successes.",
                    evidence=["metric:pressing_successes"],
                )
            ],
            closest_style_profile_ids=[f"profile:{hit.profile_id}" for hit in styles],
            uncertainties=[
                "Rival tactics other than kickoff formation are inferred, not observed."
            ],
        )
        return {
            "scouting": report.model_dump(mode="json"),
            "memories": [hit.model_dump(mode="json") for hit in memories],
        }

    def coach(self, state):
        view = self.view(state)
        # Deterministic evidence-based baseline is also the bounded failure fallback.
        behind = getattr(view.score, view.team_id.value) < getattr(
            view.score, view.rival_team_id.value
        )
        chosen = balanced().model_dump(mode="json")
        if behind or view.stats[view.team_id].shots < 2:
            chosen["mentality"], chosen["tempo"] = "attacking", "fast"
        if self.team_id == TeamId.RED:
            chosen["formation"], chosen["attack_focus"] = "4-2-3-1", "left"
        plan = TacticalPlan(
            match_id=view.match_id,
            team_id=view.team_id,
            based_on_state_version=view.snapshot_state_version,
            plan=TacticalSettings.model_validate(chosen),
            opponent_prediction=OpponentPrediction(
                likely_change="attacking"
                if view.stats[view.rival_team_id].shots < 2
                else "balanced",
                confidence=0.35,
                evidence=["metric:shots"],
            ),
            primary_objective="Improve chance creation while controlling turnovers.",
            expected_effects=["Tactical probability changes in the second half."],
            risks=["Faster tempo and pressing can increase fatigue."],
            success_indicators=["Second-half shot count versus first-half shot count."],
            rationale="Based on observed shots and score; rival response remains uncertain.",
            voice_script=f"We created {view.stats[view.team_id].shots} shots in the first half. "
            "We will improve our shape and look for better chances. Keep the team compact.",
        )
        fallback = (self.settings.llm_provider or "deterministic").lower() != "deterministic"
        if not fallback:
            plan.rationale = "Deterministic coach (no LLM call). " + plan.rationale
        if (
            self.settings.llm_api_key
            and self.settings.llm_model
            and (self.settings.llm_provider or "").lower() == "openai"
        ):
            error = ""
            for _ in range(2):  # initial attempt plus one bounded correction
                try:
                    candidate = self.generate(view, state, error)
                    validate_plan(
                        candidate,
                        view,
                        [
                            p.removeprefix("profile:")
                            for p in state["scouting"]["closest_style_profile_ids"]
                        ],
                    )
                    plan = candidate
                    fallback = False
                    break
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    error = (
                        "Previous output was invalid. Match identity, snapshot, enums "
                        "and evidence IDs must match input."
                    )
        if fallback:
            # Safe balanced fallback after failed/missing provider, never label it an LLM result.
            plan.plan = balanced()
            plan.rationale = (
                "Deterministic balanced fallback: provider unavailable or invalid output. "
                + plan.rationale
            )
        decision = CoachDecision(
            decision_id=f"{view.match_id}:{view.team_id}:decision",
            match_id=view.match_id,
            team_id=view.team_id,
            coach_id=view.own_team.coach_id,
            analysis=AnalystReport.model_validate(state["analysis"]),
            scouting=ScoutReport.model_validate(state["scouting"]),
            plan=plan,
            used_fallback=fallback,
            created_at=datetime.fromisoformat(state["before"]),
        )
        return {"decision": decision.model_dump(mode="json")}

    def generate(self, view, state, correction):
        schema = TacticalPlan.model_json_schema()

        def strict(node):
            if isinstance(node, dict):
                if "properties" in node:
                    node["required"] = list(node["properties"])
                    node["additionalProperties"] = False
                for value in node.values():
                    strict(value)
            elif isinstance(node, list):
                for value in node:
                    strict(value)

        strict(schema)
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}"},
                json={
                    "model": self.settings.llm_model,
                    "instructions": "You are an independent tactical coach. "
                    "Use only this CoachView. "
                    "Cite only supplied event IDs or "
                    "metric:shots/turnovers/score/pressing_successes/possession_pct. "
                    "Historical memories are hints, not truth. Give a short factual voice_script. "
                    + correction,
                    "input": json.dumps(
                        {
                            "view": view.model_dump(mode="json"),
                            "analysis": state["analysis"],
                            "scouting": state["scouting"],
                            "own_memories": state["memories"],
                        }
                    ),
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "tactical_plan",
                            "strict": True,
                            "schema": schema,
                        }
                    },
                },
            )
            response.raise_for_status()
            text = "".join(
                part["text"]
                for item in response.json().get("output", [])
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            return TacticalPlan.model_validate_json(text)
