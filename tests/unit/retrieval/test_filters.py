"""Unit tests for retrieval filter construction."""

from __future__ import annotations

from typing import Any

import pytest

from src.retrieval.filters import build_qdrant_filter
from src.retrieval.models import RetrievalFilters


class FakeMatchValue:
    """Qdrant-shaped exact match."""

    def __init__(self, *, value: Any) -> None:
        self.value = value


class FakeFieldCondition:
    """Qdrant-shaped field condition."""

    def __init__(self, *, key: str, match: FakeMatchValue) -> None:
        self.key = key
        self.match = match


class FakeFilter:
    """Qdrant-shaped filter conjunction."""

    def __init__(self, *, must: list[FakeFieldCondition]) -> None:
        self.must = must


class FakeQdrantModels:
    """Subset of Qdrant models needed by the filter builder."""

    Filter = FakeFilter
    FieldCondition = FakeFieldCondition
    MatchValue = FakeMatchValue


@pytest.fixture(autouse=True)
def fake_qdrant_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent from qdrant-client internals."""
    monkeypatch.setattr("src.retrieval.filters._load_qdrant_models", lambda: FakeQdrantModels)


def test_empty_filters_return_none() -> None:
    """No filter conditions should omit Qdrant query_filter."""
    assert build_qdrant_filter(RetrievalFilters()) is None


def test_builds_supported_exact_match_filters() -> None:
    """Filters are limited to actual indexed payload fields."""
    query_filter = build_qdrant_filter(
        RetrievalFilters(
            law_id="BLDS_2015",
            chunk_kind="clause_level",
            level="clause",
            article_number="1",
            source_domain="thuvienphapluat.vn",
        )
    )

    conditions = {condition.key: condition.match.value for condition in query_filter.must}
    assert conditions == {
        "law_id": "BLDS_2015",
        "chunk_kind": "clause_level",
        "level": "clause",
        "article_number": "1",
        "source_domain": "thuvienphapluat.vn",
    }


def test_exclude_repealed_adds_nested_metadata_filters() -> None:
    """The repealed exclusion uses indexed nested metadata booleans only."""
    query_filter = build_qdrant_filter(RetrievalFilters(exclude_repealed=True))

    conditions = {condition.key: condition.match.value for condition in query_filter.must}
    assert conditions == {
        "metadata.is_empty_or_repealed": False,
        "metadata.is_source_unit_repealed": False,
    }
