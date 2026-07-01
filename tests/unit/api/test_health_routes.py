from __future__ import annotations

import httpx
import pytest

from src.api.app import create_app
from src.api.dependencies import get_runtime_readiness_service
from src.services.legal_qa_workflow import LegalQAServiceMode
from src.services.runtime_readiness import RuntimeReadinessService


@pytest.mark.asyncio
async def test_health_route_returns_ok() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_version_route_returns_metadata() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/version")

    assert response.status_code == 200
    assert response.json() == {"name": "VnLaw-QA API", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_fake_mode_readiness_needs_no_external_dependencies() -> None:
    app = create_app()
    app.dependency_overrides[get_runtime_readiness_service] = lambda: RuntimeReadinessService(
        service_mode=LegalQAServiceMode.FAKE,
        configuration_issues=(),
        qdrant_collection=None,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "service_mode": "fake",
        "checks": [{"name": "configuration", "ready": True, "detail": "valid"}],
    }


@pytest.mark.asyncio
async def test_real_mode_readiness_reports_safe_configuration_failure() -> None:
    app = create_app()
    app.dependency_overrides[get_runtime_readiness_service] = lambda: RuntimeReadinessService(
        service_mode=LegalQAServiceMode.REAL,
        configuration_issues=("missing_openrouter_api_key",),
        qdrant_collection=None,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "ready": False,
        "service_mode": "real",
        "checks": [
            {
                "name": "configuration",
                "ready": False,
                "detail": "missing_openrouter_api_key",
            }
        ],
    }
    assert "api-key-value" not in response.text
