"""Unit tests for safe backend runtime readiness."""

from __future__ import annotations

from typing import Any

import pytest

from src.services.legal_qa_workflow import LegalQAServiceMode
from src.services.runtime_readiness import (
    QdrantCollectionReadinessProbe,
    RuntimeReadinessService,
)


class StubQdrantProbe:
    """Read-only probe stub with deterministic success or failure."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.collections: list[str] = []

    async def check_collection(self, collection_name: str) -> None:
        self.collections.append(collection_name)
        if self.error is not None:
            raise self.error


@pytest.mark.asyncio
async def test_fake_readiness_does_not_call_qdrant() -> None:
    probe = StubQdrantProbe(AssertionError("fake mode must not call Qdrant"))
    service = RuntimeReadinessService(
        service_mode=LegalQAServiceMode.FAKE,
        configuration_issues=(),
        qdrant_collection=None,
        qdrant_probe=probe,
    )

    result = await service.check()

    assert result.ready is True
    assert probe.collections == []


@pytest.mark.asyncio
async def test_real_readiness_checks_collection_metadata_only() -> None:
    probe = StubQdrantProbe()
    service = RuntimeReadinessService(
        service_mode=LegalQAServiceMode.REAL,
        configuration_issues=(),
        qdrant_collection="legal_chunks",
        qdrant_probe=probe,
    )

    result = await service.check()

    assert result.ready is True
    assert probe.collections == ["legal_chunks"]
    assert result.checks[-1].detail == "collection_available"


@pytest.mark.asyncio
async def test_real_readiness_with_invalid_config_does_not_call_qdrant() -> None:
    probe = StubQdrantProbe(AssertionError("invalid config must skip Qdrant"))
    service = RuntimeReadinessService(
        service_mode=LegalQAServiceMode.REAL,
        configuration_issues=("missing_openrouter_api_key",),
        qdrant_collection="legal_chunks",
        qdrant_probe=probe,
    )

    result = await service.check()

    assert result.ready is False
    assert probe.collections == []
    assert result.checks[0].detail == "missing_openrouter_api_key"


@pytest.mark.asyncio
async def test_real_readiness_sanitizes_qdrant_failure() -> None:
    probe = StubQdrantProbe(RuntimeError("credential=qdrant-secret-value"))
    service = RuntimeReadinessService(
        service_mode=LegalQAServiceMode.REAL,
        configuration_issues=(),
        qdrant_collection="legal_chunks",
        qdrant_probe=probe,
    )

    result = await service.check()

    assert result.ready is False
    assert result.checks[-1].detail == "unavailable"
    assert "qdrant-secret-value" not in repr(result)


@pytest.mark.asyncio
async def test_qdrant_readiness_probe_reads_metadata_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class FakeClient:
        async def get_collection(self, collection_name: str) -> object:
            calls["collection_name"] = collection_name
            return object()

        async def close(self) -> None:
            calls["closed"] = True

    def fake_builder(**kwargs: Any) -> FakeClient:
        calls["builder"] = kwargs
        return FakeClient()

    monkeypatch.setattr(
        "src.services.runtime_readiness.build_qdrant_client",
        fake_builder,
    )
    probe = QdrantCollectionReadinessProbe(
        url="https://qdrant.example.invalid",
        api_key="qdrant-test-key",
        timeout_seconds=2.0,
    )

    await probe.check_collection("legal_chunks")

    assert calls == {
        "builder": {
            "url": "https://qdrant.example.invalid",
            "timeout_seconds": 2.0,
            "api_key": "qdrant-test-key",
        },
        "collection_name": "legal_chunks",
        "closed": True,
    }
