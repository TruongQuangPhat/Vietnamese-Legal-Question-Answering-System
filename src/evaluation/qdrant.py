"""Qdrant client construction helpers for evaluation workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.indexing.qdrant_collection import build_qdrant_client, resolve_qdrant_api_key


def build_evaluation_qdrant_client(
    *,
    url: str,
    timeout_seconds: float,
    explicit_api_key: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Any:
    """Build an evaluation Qdrant client with optional environment auth.

    Evaluation CLIs support local unauthenticated Qdrant by default. When
    ``QDRANT_API_KEY`` is present, the key is passed directly to the shared
    Qdrant client factory without logging or serializing it.

    Args:
        url: Qdrant HTTP endpoint.
        timeout_seconds: Positive request timeout.
        explicit_api_key: Optional explicit key, primarily for tests.
        environ: Optional environment mapping for deterministic tests.

    Returns:
        A Qdrant client from the shared indexing client factory.
    """
    return build_qdrant_client(
        url=url,
        timeout_seconds=timeout_seconds,
        api_key=resolve_qdrant_api_key(explicit_api_key, environ=environ),
    )
