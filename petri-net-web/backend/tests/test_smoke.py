"""Smoke tests for the bootstrap scaffolding."""

from fastapi.testclient import TestClient

from petrinet.api.app import app


def test_healthz() -> None:
    """GET /healthz returns ok."""
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_index_served() -> None:
    """The frontend index.html is mounted at /."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
