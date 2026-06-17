"""Unit tests for fallback-aware Naive RAG LLM client contracts."""

from __future__ import annotations

import pytest

from src.retrieval.llm_client import (
    LLMClientError,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MockLLMClient,
    OpenRouterLLMClient,
)


@pytest.mark.asyncio
async def test_openrouter_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenRouter should fail cleanly before any network call when no key exists."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = OpenRouterLLMClient()

    with pytest.raises(LLMClientError, match="OPENROUTER_API_KEY"):
        await client.generate(LLMRequest(messages=[LLMMessage(role="user", content="Xin chào")]))


@pytest.mark.asyncio
async def test_mock_llm_client_records_requests() -> None:
    """MockLLMClient returns queued responses and records request payloads."""
    response = LLMResponse(
        text="Câu trả lời [E1]",
        model="mock-model",
        provider="mock",
        latency_ms=1.0,
    )
    client = MockLLMClient([response])
    request = LLMRequest(messages=[LLMMessage(role="user", content="Câu hỏi")])

    result = await client.generate(request)

    assert result.text == "Câu trả lời [E1]"
    assert client.requests == [request]


@pytest.mark.asyncio
async def test_mock_llm_client_raises_queued_exception() -> None:
    """MockLLMClient can simulate provider failures without network I/O."""
    client = MockLLMClient([LLMClientError("provider unavailable")])

    with pytest.raises(LLMClientError, match="provider unavailable"):
        await client.generate(LLMRequest(messages=[LLMMessage(role="user", content="Câu hỏi")]))
