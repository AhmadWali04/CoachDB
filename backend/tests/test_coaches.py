import json
from types import SimpleNamespace

import pytest

from app.coaches import ClaudeStructuredLLM, Coach, LLMUnavailable
from app.coaches.agents import AnalystDraft, PlanDraft, ScoutDraft, evidence_checker
from app.coaches.llm import _UNSUPPORTED, wire_schema
from app.data import StyleHit
from app.guardrails import GuardrailViolation, build_coach_view
from app.orchestration import InMemoryMatchRepository, MatchService
from app.orchestration.halftime import CoachingHalftime
from app.schemas import Level, MatchPhase, Mentality, TeamId
from app.simulator import MatchSimulator, new_match_state


def halftime_view(team=TeamId.BLUE, seed=4):
    sim = MatchSimulator(new_match_state("m1", seed, steps_per_half=6))
    events = []
    while sim.state.phase is not MatchPhase.HALFTIME:
        events += sim.step().events
    return build_coach_view(sim.state, events, team), events


class FakeLLM:
    """Scripted drafts per output type; records every call."""

    def __init__(self, view, plan_overrides=None, fail=()):
        self.view = view
        self.calls = []
        self.plan_overrides = plan_overrides or {}
        self.fail = set(fail)

    def complete(self, *, system, prompt, output, effort, check=None):
        self.calls.append((output.__name__, system, prompt, effort))
        if output.__name__ in self.fail:
            raise LLMUnavailable("scripted failure")
        event_id = self.view.public_events[0].event_id
        obs = {"observation": "Strong left side", "evidence": [event_id]}
        if output is AnalystDraft:
            draft = AnalystDraft(
                summary="Solid half.",
                own_strengths=[obs],
                own_weaknesses=[],
                fatigue_concerns=[],
                uncertainties=[],
            )
        elif output is ScoutDraft:
            draft = ScoutDraft.model_validate(
                {
                    "observed_tactics": {"pressing": "high", "defensive_line": "high"},
                    "patterns": [obs],
                    "likely_adjustments": [
                        {"change": "drop deeper", "confidence": 0.6, "evidence": [event_id]}
                    ],
                    "uncertainties": [],
                }
            )
        else:
            plan = {
                "formation": "4-2-3-1",
                "mentality": "attacking",
                "pressing": "medium",
                "defensive_line": "medium",
                "attack_focus": "left",
                "tempo": "fast",
                **self.plan_overrides,
            }
            draft = PlanDraft.model_validate(
                {
                    "plan": plan,
                    "opponent_prediction": {
                        "likely_change": "drop deeper",
                        "confidence": 0.6,
                        "evidence": [event_id],
                    },
                    "primary_objective": "Attack the left.",
                    "expected_effects": ["More left entries"],
                    "risks": ["Counters"],
                    "success_indicators": ["Shots"],
                    "rationale": "Left side worked.",
                    "voice_script": "We found space on the left. Keep moving it quickly.",
                }
            )
        problems = check(draft) if check else []
        assert not problems, problems
        return draft


# --- schema --------------------------------------------------------------------


def test_wire_schema_uses_only_supported_keywords():
    def walk(node):
        if isinstance(node, dict):
            assert not set(node) & _UNSUPPORTED
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for model in (AnalystDraft, ScoutDraft, PlanDraft):
        walk(wire_schema(model))


# --- evidence -----------------------------------------------------------------


def test_unknown_evidence_ids_are_reported():
    view, _ = halftime_view()
    check = evidence_checker({"metric:shots"})
    draft = AnalystDraft(
        summary="x",
        own_strengths=[{"observation": "y", "evidence": ["metric:shots", "made-up:1"]}],
        own_weaknesses=[],
        fatigue_concerns=[],
        uncertainties=[],
    )
    assert check(draft) == ["Unknown evidence ID: made-up:1"]


# --- coach pipeline -------------------------------------------------------------


def test_coach_builds_a_decision_from_its_own_view():
    view, _ = halftime_view()
    llm = FakeLLM(view)
    hits = [
        StyleHit(
            profile_id="sb:1", summary="Spain", source="statsbomb", source_match_id="1", score=0.8
        )
    ]
    coach = Coach(TeamId.BLUE, "coach_blue", llm, style_search=lambda observed: hits)
    result = coach.decide(view)
    d = result.decision
    assert d.team_id is TeamId.BLUE and not d.used_fallback
    assert d.plan.based_on_state_version == view.snapshot_state_version
    assert d.scouting.rival_team_id is TeamId.RED
    assert d.scouting.observed_tactics.formation == view.rival_team.kickoff_formation
    assert d.scouting.closest_style_profile_ids == ["profile:sb:1"]
    assert [c[0] for c in llm.calls][-1] == "PlanDraft"
    assert "profile:sb:1" in llm.calls[-1][2]  # styles reach the tactical coach


def test_coach_refuses_the_rival_view():
    red_view, _ = halftime_view(TeamId.RED)
    with pytest.raises(ValueError):
        Coach(TeamId.BLUE, "coach_blue", FakeLLM(red_view)).decide(red_view)


def test_coach_view_namespace_is_checked():
    view, _ = halftime_view()
    tampered = view.model_copy(update={"memory_namespace": "coach:red"})
    with pytest.raises(GuardrailViolation):
        Coach(TeamId.BLUE, "coach_blue", FakeLLM(view)).decide(tampered)


def test_prompts_never_contain_rival_tactics():
    view, _ = halftime_view()
    llm = FakeLLM(view)
    Coach(TeamId.BLUE, "coach_blue", llm).decide(view)
    rival = halftime_view(TeamId.RED)[0].own_team.tactics
    for _, _, prompt, _ in llm.calls:
        data = json.loads(prompt.split("Match data (JSON):\n", 1)[1].split("\n\n", 1)[0])
        assert "first_half_tactics" not in data["rival_team"]
        assert data["rival_team"]["kickoff_formation"] == rival.formation.value


def test_tactical_failure_falls_back_to_a_balanced_plan():
    view, _ = halftime_view()
    result = Coach(TeamId.BLUE, "coach_blue", FakeLLM(view, fail={"PlanDraft"})).decide(view)
    plan = result.decision.plan
    assert result.decision.used_fallback
    assert plan.plan.mentality is Mentality.BALANCED and plan.plan.pressing is Level.MEDIUM
    assert plan.plan.formation == view.own_team.tactics.formation
    assert plan.voice_script


def test_analyst_and_scout_failures_still_produce_a_plan():
    view, _ = halftime_view()
    llm = FakeLLM(view, fail={"AnalystDraft", "ScoutDraft"})
    result = Coach(TeamId.BLUE, "coach_blue", llm).decide(view)
    assert result.fallbacks == {"analyst": True, "scout": True, "tactical": False}


# --- halftime flow ----------------------------------------------------------------


class ViewAwareCoach(Coach):
    """Hands the fake LLM the view it is deciding on, so its evidence is real."""

    def decide(self, view):
        self.llm.view = view
        return super().decide(view)


def test_halftime_saves_both_decisions_and_applies_both_plans():
    repo = InMemoryMatchRepository()
    coaches = {
        team: ViewAwareCoach(team, f"coach_{team.value}", FakeLLM(None, {"attack_focus": focus}))
        for team, focus in ((TeamId.BLUE, "left"), (TeamId.RED, "right"))
    }
    service = MatchService(repo, step_seconds=0, halftime=CoachingHalftime(coaches))
    match_id = service.create_match(8, 5, start=False).match_id
    final = service.run_to_completion(match_id)

    assert final.phase is MatchPhase.FULL_TIME
    blue, red = (repo.get_latest_decision(match_id, t) for t in TeamId)
    assert blue.plan.plan.attack_focus.value == "left"
    assert red.plan.plan.attack_focus.value == "right"
    sim = service.run(match_id).simulator
    assert sim.team(TeamId.BLUE).tactics.attack_focus.value == "left"
    assert sim.team(TeamId.RED).tactics.attack_focus.value == "right"
    changes = [e for e in repo.get_events(match_id) if e.type.value == "tactical_change"]
    assert {e.team_id for e in changes} == {TeamId.BLUE, TeamId.RED}
    # Both coaches decided on the same snapshot.
    assert blue.plan.based_on_state_version == red.plan.based_on_state_version


def test_halftime_with_no_model_still_finishes_the_match():
    repo = InMemoryMatchRepository()
    coaches = {
        team: ViewAwareCoach(
            team,
            f"coach_{team.value}",
            FakeLLM(None, fail={"AnalystDraft", "ScoutDraft", "PlanDraft"}),
        )
        for team in TeamId
    }
    service = MatchService(repo, step_seconds=0, halftime=CoachingHalftime(coaches))
    match_id = service.create_match(8, 5, start=False).match_id
    assert service.run_to_completion(match_id).phase is MatchPhase.FULL_TIME
    assert all(repo.get_latest_decision(match_id, t).used_fallback for t in TeamId)


# --- Claude adapter (fake client, no network) ------------------------------------------


def response(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


def analyst_json(evidence):
    return json.dumps(
        {
            "summary": "ok",
            "own_strengths": [{"observation": "x", "evidence": [evidence]}],
            "own_weaknesses": [],
            "fatigue_concerns": [],
            "uncertainties": [],
        }
    )


def test_claude_adapter_sends_one_correction_then_succeeds():
    client = FakeClient([response(analyst_json("bogus")), response(analyst_json("metric:shots"))])
    llm = ClaudeStructuredLLM(client=client)
    draft = llm.complete(
        system="s",
        prompt="p",
        output=AnalystDraft,
        effort="low",
        check=evidence_checker({"metric:shots"}),
    )
    assert draft.own_strengths[0].evidence == ["metric:shots"]
    first, second = client.requests
    assert first["model"] == "claude-opus-5-5"
    assert first["output_config"]["format"]["type"] == "json_schema"
    assert first["output_config"]["effort"] == "low"
    assert first["fallbacks"] == "default" and first["thinking"] == {"type": "adaptive"}
    assert "Unknown evidence ID: bogus" in second["messages"][-1]["content"]


def test_claude_adapter_gives_up_after_one_correction():
    client = FakeClient([response("not json"), response("still not json")])
    with pytest.raises(LLMUnavailable):
        ClaudeStructuredLLM(client=client).complete(
            system="s", prompt="p", output=AnalystDraft, effort="low"
        )
    assert len(client.requests) == 2


def test_claude_adapter_treats_refusal_as_unavailable():
    client = FakeClient([response("", stop="refusal")])
    with pytest.raises(LLMUnavailable, match="declined"):
        ClaudeStructuredLLM(client=client).complete(
            system="s", prompt="p", output=AnalystDraft, effort="low"
        )
