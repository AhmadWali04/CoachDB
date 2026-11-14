from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.evaluation import EvaluationRunner
from app.evaluation.evaluator import changed_dimensions, prediction_correct
from app.schemas import EventType, MatchEvent, TeamId

from .test_recovery import service_with_workflow


def batch(seeds=(1, 2)):
    service, _ = service_with_workflow()
    runner = EvaluationRunner(service)
    return runner.get(runner.start(list(seeds), 4, background=False))


def test_batch_runs_each_seed_twice_with_sides_swapped():
    b = batch()
    assert b.status == "done"
    assert [(r.seed, r.sides_swapped) for r in b.results] == [
        (1, False),
        (1, True),
        (2, False),
        (2, True),
    ]
    for team in TeamId:
        m = b.metrics[team]
        assert m.decision_validity == 1.0
        assert m.execution_reliability == 1.0
        assert m.recovery_correctness == 1.0
        assert m.evidence_grounding == 1.0
        assert m.wins + m.draws + m.losses == 4


def test_metrics_are_reproducible_for_the_same_seeds():
    a, b = batch(), batch()
    assert [r.score for r in a.results] == [r.score for r in b.results]

    # Latency is a wall-clock measurement; every outcome-based metric must match.
    def outcome(metrics):
        return {t: m.model_dump(exclude={"avg_decision_latency_ms"}) for t, m in metrics.items()}

    assert outcome(a.metrics) == outcome(b.metrics)


def test_swapped_sides_put_red_on_top_and_change_the_match():
    service, _ = service_with_workflow()
    normal = service.create_match(5, 4, start=False)
    swapped = service.create_match(5, 4, start=False, swap_sides=True)
    sides = {t.team_id: t.side.value for t in swapped.teams}
    assert sides == {TeamId.BLUE: "bottom", TeamId.RED: "top"}
    a = service.run_to_completion(normal.match_id)
    b = service.run_to_completion(swapped.match_id)
    assert (a.stats, a.score) != (b.stats, b.score)


def change(team, before, after):
    return MatchEvent(
        event_id="e",
        match_id="m",
        half=2,
        step=0,
        clock_minute=45,
        team_id=team,
        type=EventType.TACTICAL_CHANGE,
        details={"from": before, "to": after},
        created_at=datetime.now(UTC),
    )


def test_prediction_heuristic():
    events = [
        change(
            TeamId.RED, {"pressing": "low", "tempo": "slow"}, {"pressing": "high", "tempo": "slow"}
        )
    ]
    assert changed_dimensions(events, TeamId.RED) == {"pressing"}

    class D:
        def __init__(self, text):
            self.plan = type(
                "P", (), {"opponent_prediction": type("O", (), {"likely_change": text})}
            )

    assert prediction_correct(D("They will press higher"), {"pressing"})
    assert not prediction_correct(D("They will play faster"), {"pressing"})
    assert prediction_correct(D("No change expected"), set())
    assert not prediction_correct(None, {"pressing"})


def test_evaluation_api_returns_the_batch():
    from app.api.evaluations import get_evaluation_runner
    from app.main import app

    service, _ = service_with_workflow()
    runner = EvaluationRunner(service)
    app.dependency_overrides[get_evaluation_runner] = lambda: runner
    try:
        client = TestClient(app)
        started = client.post("/evaluations", json={"seeds": [3], "steps_per_half": 4})
        assert started.status_code == 202
        batch_id = started.json()["batch_id"]
        import time

        for _ in range(100):
            body = client.get(f"/evaluations/{batch_id}").json()
            if body["status"] != "running":
                break
            time.sleep(0.05)
        assert body["status"] == "done" and len(body["results"]) == 2
        assert set(body["metrics"]) == {"blue", "red"}
        assert client.get("/evaluations/nope").status_code == 404
    finally:
        app.dependency_overrides.clear()
