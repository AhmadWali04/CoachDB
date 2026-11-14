import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration import InMemoryMatchRepository, MatchService
from app.orchestration.dependencies import get_match_service
from app.schemas import FramesPage, MatchPhase, MatchState
from app.simulator import FRAMES_PER_STEP


@pytest.fixture
def service():
    svc = MatchService(InMemoryMatchRepository(), step_seconds=0.0)
    app.dependency_overrides[get_match_service] = lambda: svc
    yield svc
    svc.stop_all()
    app.dependency_overrides.clear()


@pytest.fixture
def client(service):
    return TestClient(app)


def test_create_match_runs_to_full_time_in_the_background(client, service):
    response = client.post("/matches", json={"seed": 42, "steps_per_half": 4})
    assert response.status_code == 201
    match = MatchState.model_validate(response.json())
    final = service.wait_for(match.match_id, MatchPhase.FULL_TIME)
    assert final.clock_minute == 90
    assert client.get(f"/matches/{match.match_id}").json()["phase"] == "full_time"


def test_frames_page_through_the_whole_match_without_duplicates(client, service):
    match_id = client.post("/matches", json={"seed": 7, "steps_per_half": 4}).json()["match_id"]
    service.wait_for(match_id, MatchPhase.FULL_TIME)
    seqs, next_seq = [], 0
    while next_seq is not None:
        page = FramesPage.model_validate(
            client.get(
                f"/matches/{match_id}/frames", params={"from_seq": next_seq, "limit": 5}
            ).json()
        )
        seqs += [f.seq for f in page.frames]
        if not page.frames:
            break
        next_seq = page.next_seq
    assert seqs == list(range(8 * FRAMES_PER_STEP))
    last = client.get(f"/matches/{match_id}/frames", params={"from_seq": len(seqs)}).json()
    assert last["frames"] == [] and last["next_seq"] is None


def test_frames_page_keeps_next_seq_while_the_match_is_live(client, service):
    match_id = service.create_match(1, 4, start=False).match_id
    page = client.get(f"/matches/{match_id}/frames").json()
    assert page["frames"] == [] and page["next_seq"] == 0


def test_events_match_the_score(client, service):
    match_id = client.post("/matches", json={"seed": 3, "steps_per_half": 6}).json()["match_id"]
    final = service.wait_for(match_id, MatchPhase.FULL_TIME)
    events = client.get(f"/matches/{match_id}/events").json()
    goals = [e for e in events if e["type"] == "goal"]
    assert len(goals) == final.score.blue + final.score.red
    assert events[-1]["type"] == "full_time"


def test_same_seed_gives_the_same_persisted_match(service):
    a = service.create_match(99, 4, start=False)
    b = service.create_match(99, 4, start=False)
    fa, fb = service.run_to_completion(a.match_id), service.run_to_completion(b.match_id)
    assert (fa.score, fa.stats) == (fb.score, fb.stats)
    pa = service.repository.get_frames(a.match_id, limit=200)
    pb = service.repository.get_frames(b.match_id, limit=200)
    assert [(f.ball.x, f.ball.y) for f in pa] == [(f.ball.x, f.ball.y) for f in pb]


def test_reset_starts_a_fresh_match_with_the_same_seed(client, service):
    old = client.post("/matches", json={"seed": 5, "steps_per_half": 4}).json()
    new = client.post(f"/matches/{old['match_id']}/reset").json()
    assert new["match_id"] != old["match_id"] and new["seed"] == 5


def test_unknown_match_is_404(client):
    for path in ("/matches/nope", "/matches/nope/frames", "/matches/nope/events"):
        assert client.get(path).status_code == 404


def test_halftime_handler_runs_once_between_halves(service):
    calls = []
    service.halftime = lambda run: calls.append(run.simulator.state.phase)
    match_id = service.create_match(2, 3, start=False).match_id
    service.run_to_completion(match_id)
    assert calls == [MatchPhase.HALFTIME]
