"""Unit tests for dense retrieval baseline retrieval contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.retrieval.models import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DENSE_DIMENSION,
    RetrievalConfig,
    RetrievalFilters,
    RetrievalQuery,
)


def test_retrieval_query_trims_query_and_defaults() -> None:
    """Retrieval queries normalize whitespace and use dense-baseline defaults."""
    query = RetrievalQuery(query="  Quyền sử dụng đất là gì?  ")

    assert query.query == "Quyền sử dụng đất là gì?"
    assert query.top_k == 10
    assert query.collection_name == DEFAULT_COLLECTION_NAME


def test_retrieval_query_rejects_blank_query() -> None:
    """Blank queries fail before embedding or Qdrant access."""
    with pytest.raises(ValidationError):
        RetrievalQuery(query="   ")


def test_retrieval_query_rejects_non_positive_top_k() -> None:
    """top_k must be positive."""
    with pytest.raises(ValidationError):
        RetrievalQuery(query="test", top_k=0)


def test_retrieval_filters_trim_optional_strings() -> None:
    """Supported exact-match filter values are trimmed."""
    filters = RetrievalFilters(law_id=" BLDS_2015 ", source_domain=" thuvienphapluat.vn ")

    assert filters.law_id == "BLDS_2015"
    assert filters.source_domain == "thuvienphapluat.vn"
    assert filters.has_conditions() is True


def test_retrieval_filters_reject_blank_optional_strings() -> None:
    """Blank filter strings are ambiguous and rejected."""
    with pytest.raises(ValidationError):
        RetrievalFilters(law_id=" ")


def test_default_retrieval_config_loads() -> None:
    """The repository retrieval config matches the completed Phase 8 index."""
    payload = yaml.safe_load(Path("configs/retrieval/retrieval.yml").read_text())
    config = RetrievalConfig.model_validate(payload)

    assert config.embedding.model_name == "BAAI/bge-m3"
    assert config.qdrant.collection_name == DEFAULT_COLLECTION_NAME
    assert config.dense_retrieval.vector_name == "dense"
    assert config.dense_retrieval.expected_vector_dim == DEFAULT_DENSE_DIMENSION


def test_retrieval_config_rejects_non_bge_m3_dimension() -> None:
    """dense retrieval baseline is pinned to the existing 1024-dimensional dense index."""
    payload = yaml.safe_load(Path("configs/retrieval/retrieval.yml").read_text())
    payload["dense_retrieval"]["expected_vector_dim"] = 768

    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(payload)
