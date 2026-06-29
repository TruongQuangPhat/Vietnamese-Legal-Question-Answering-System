from __future__ import annotations

import httpx
import pytest

from src.api.app import create_app


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
