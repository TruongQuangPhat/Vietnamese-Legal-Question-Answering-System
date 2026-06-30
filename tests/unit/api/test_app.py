from __future__ import annotations

import httpx
import pytest

from src.api.app import create_app
from src.api.settings import AppSettings


@pytest.mark.asyncio
async def test_app_allows_cors_preflight_from_configured_origin() -> None:
    app = create_app(
        AppSettings.from_env(
            {"CORS_ALLOWED_ORIGINS": "http://localhost:3000,http://localhost:5173"}
        )
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            "/api/v1/legal-qa/ask",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_app_does_not_allow_unconfigured_cors_origin() -> None:
    app = create_app(AppSettings.from_env({"CORS_ALLOWED_ORIGINS": "http://localhost:3000"}))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            "/api/v1/legal-qa/ask",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.headers.get("access-control-allow-origin") != "http://localhost:5173"


@pytest.mark.asyncio
async def test_app_existing_routes_still_work_with_settings() -> None:
    app = create_app(AppSettings.from_env({"CORS_ALLOWED_ORIGINS": "http://localhost:3000"}))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health_response = await client.get("/health")
        version_response = await client.get("/version")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert version_response.status_code == 200
    assert version_response.json() == {"name": "VnLaw-QA API", "version": "0.1.0"}
