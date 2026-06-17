"""Safe Qdrant filter construction for dense retrieval baseline dense retrieval."""

from __future__ import annotations

import importlib
from typing import Any

from src.retrieval.models import RetrievalFilters


class RetrievalFilterError(ValueError):
    """Raised when a retrieval filter cannot be translated safely."""


def build_qdrant_filter(filters: RetrievalFilters) -> Any | None:
    """Build an exact-match Qdrant filter for supported indexed payload fields.

    Args:
        filters: Validated dense retrieval baseline retrieval filters.

    Returns:
        A Qdrant ``Filter`` instance, or ``None`` when no conditions are set.

    Raises:
        RetrievalFilterError: If the optional ``qdrant-client`` dependency is
            unavailable or a condition cannot be constructed.
    """
    if not filters.has_conditions():
        return None

    models = _load_qdrant_models()
    conditions: list[Any] = []
    _append_match(conditions, models, "law_id", filters.law_id)
    _append_match(conditions, models, "chunk_kind", filters.chunk_kind)
    _append_match(conditions, models, "level", filters.level)
    _append_match(conditions, models, "article_number", filters.article_number)
    _append_match(conditions, models, "source_domain", filters.source_domain)

    if filters.exclude_repealed:
        _append_match(conditions, models, "metadata.is_empty_or_repealed", False)
        _append_match(conditions, models, "metadata.is_source_unit_repealed", False)

    return models.Filter(must=conditions)


def _append_match(
    conditions: list[Any],
    models: Any,
    field_name: str,
    value: str | bool | None,
) -> None:
    if value is None:
        return
    conditions.append(
        models.FieldCondition(
            key=field_name,
            match=models.MatchValue(value=value),
        )
    )


def _load_qdrant_models() -> Any:
    try:
        return importlib.import_module("qdrant_client.http.models")
    except ImportError as exc:
        raise RetrievalFilterError(
            "qdrant-client is required for retrieval filters; "
            "install it with `uv sync --extra qdrant`"
        ) from exc
