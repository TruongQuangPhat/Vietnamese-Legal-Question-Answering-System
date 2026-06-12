"""LLM client abstractions and OpenRouter implementation for Phase 9B.

This module is provider-facing only. It does not perform retrieval, select
evidence, validate legal sufficiency, or know about Qdrant. API keys are read
from environment variables or constructor arguments and are never serialized
into request/response models.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.retrieval.openrouter_config import (
    FALLBACK_OPENROUTER_BASE_URL,
    FALLBACK_OPENROUTER_MODEL,
)


class LLMClientError(RuntimeError):
    """Raised when a provider cannot return a usable LLM response."""


class LLMMessage(BaseModel):
    """One OpenAI-compatible chat message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)

    @field_validator("role", "content")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        """Trim and reject blank chat message fields."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("message fields must not be blank")
        return stripped


class LLMUsage(BaseModel):
    """Token usage reported by an LLM provider when available."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int | None = Field(None, ge=0)
    completion_tokens: int | None = Field(None, ge=0)
    total_tokens: int | None = Field(None, ge=0)


class LLMRequest(BaseModel):
    """Provider-neutral generation request.

    Legal assumptions:
        The caller is responsible for rendering a prompt from selected,
        citation-safe evidence only. The LLM client must not add legal facts or
        retrieve context on its own.
    """

    model_config = ConfigDict(extra="forbid")

    messages: list[LLMMessage] = Field(..., min_length=1)
    model: str = Field(FALLBACK_OPENROUTER_MODEL, min_length=1)
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, gt=0)
    timeout_s: float = Field(30.0, gt=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Provider-neutral generation response."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    latency_ms: float = Field(..., ge=0.0)
    usage: LLMUsage | None = None
    raw_response: dict[str, Any] | None = None
    finish_reason: str | None = None


class LLMClientProtocol(Protocol):
    """Minimal async provider interface used by the Naive RAG pipeline."""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response for a fully rendered legal QA prompt."""
        ...


class OpenRouterLLMClient:
    """OpenRouter chat-completions client using the OpenAI-compatible API."""

    provider = "openrouter"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the OpenRouter client without exposing credentials.

        Args:
            base_url: Optional base URL. Defaults to ``OPENROUTER_BASE_URL`` or
                the emergency OpenRouter API fallback.
            default_model: Optional default model. Defaults to
                ``OPENROUTER_MODEL`` or the emergency model fallback.
            http_client: Optional injected async HTTP client for tests.
        """
        self._base_url = (
            base_url or os.getenv("OPENROUTER_BASE_URL") or FALLBACK_OPENROUTER_BASE_URL
        ).rstrip("/")
        self._default_model = (
            default_model or os.getenv("OPENROUTER_MODEL") or FALLBACK_OPENROUTER_MODEL
        )
        self._http_client = http_client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Call OpenRouter and return the first assistant message text.

        Raises:
            LLMClientError: If the API key is missing, HTTP fails, JSON is
                malformed, or no assistant text is returned.
        """
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise LLMClientError("OPENROUTER_API_KEY is not set")

        payload = {
            "model": request.model or self._default_model,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=request.timeout_s,
                )
            else:
                async with httpx.AsyncClient(timeout=request.timeout_s) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise LLMClientError(
                f"OpenRouter request failed with status {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMClientError(f"OpenRouter request failed: {exc}") from exc

        text, finish_reason = _extract_openai_compatible_text(data)
        if not text.strip():
            raise LLMClientError("OpenRouter response did not include assistant text")
        return LLMResponse(
            text=text.strip(),
            model=str(data.get("model") or payload["model"]),
            provider=self.provider,
            latency_ms=(time.perf_counter() - started) * 1000,
            usage=_usage_from_payload(data.get("usage")),
            raw_response=data,
            finish_reason=finish_reason,
        )


class MockLLMClient:
    """Test double that returns preconfigured LLM responses without network I/O."""

    provider = "mock"

    def __init__(self, responses: Sequence[LLMResponse | Exception]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Return the next configured response or raise the next exception."""
        self.requests.append(request)
        if not self._responses:
            raise LLMClientError("MockLLMClient has no queued response")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _extract_openai_compatible_text(payload: dict[str, Any]) -> tuple[str, str | None]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMClientError("provider response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise LLMClientError("provider response choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise LLMClientError("provider response choice missing message")
    content = message.get("content")
    if not isinstance(content, str):
        raise LLMClientError("provider response message content is not text")
    finish_reason = first.get("finish_reason")
    return content, finish_reason if isinstance(finish_reason, str) else None


def _usage_from_payload(payload: Any) -> LLMUsage | None:
    if not isinstance(payload, dict):
        return None
    return LLMUsage(
        prompt_tokens=_int_or_none(payload.get("prompt_tokens")),
        completion_tokens=_int_or_none(payload.get("completion_tokens")),
        total_tokens=_int_or_none(payload.get("total_tokens")),
    )


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None
