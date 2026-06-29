from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import create_app


def test_health_route_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_route_returns_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {"name": "VnLaw-QA API", "version": "0.1.0"}
