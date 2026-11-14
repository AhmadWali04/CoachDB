import pytest
from fastapi.testclient import TestClient

from app.main import app
from scripts.export_openapi import OUT, render

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # The test suite never depends on a real cluster.
    assert response.json()["mongodb"] in {"ok", "not_configured", "unreachable"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/matches", {}),
        ("get", "/matches/m1", None),
        ("get", "/matches/m1/frames", None),
        ("get", "/matches/m1/events", None),
        ("post", "/matches/m1/reset", None),
        ("post", "/demo/inject-crash", {"match_id": "m1"}),
    ],
)
def test_stubs_return_501(method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 501


def test_briefing_rejects_unknown_team():
    assert client.get("/matches/m1/briefings/green").status_code == 422


def test_briefing_404s_when_no_decision_is_persisted_yet():
    """Implemented (owner B); 404 for an unknown match/team rather than 501."""
    assert client.get("/matches/no-such-match/briefings/blue").status_code == 404


def test_openapi_json_is_up_to_date():
    """Fails if schemas/api changed without re-running scripts/export_openapi.py."""
    assert OUT.read_text() == render(), "run: .venv/bin/python scripts/export_openapi.py"
