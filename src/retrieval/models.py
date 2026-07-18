"""Typed contracts for dense retrieval baseline dense retrieval.

The models in this module represent query input, safe payload filters, retrieved
legal evidence, and retrieval-level diagnostics. They preserve embedding/indexing payload
fields without exposing raw Qdrant payload dictionaries to downstream
generation code.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_COLLECTION_NAME = "vnlaw_chunks_bgem3_v1_full"
DEFAULT_DENSE_VECTOR_NAME = "dense"
DEFAULT_DENSE_DIMENSION = 1024
DEFAULT_TOP_K = 10


class RetrievalIssueSeverity(StrEnum):
    """Severity values for retrieval diagnostics."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RetrievalIssue(BaseModel):
    """Structured issue emitted while validating retrieval inputs or payloads.

    Attributes:
        code: Stable machine-readable issue code.
        severity: Issue severity.
        message: Human-readable diagnostic message.
        rank: One-based result rank when the issue is tied to a hit.
        chunk_id: Retrieved chunk identifier when available.
        details: Small structured context for logs or reports.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(..., min_length=1)
    severity: RetrievalIssueSeverity
    message: str = Field(..., min_length=1)
    rank: int | None = Field(None, ge=1)
    chunk_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        """Reject blank issue codes and messages."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("chunk_id")
    @classmethod
    def validate_optional_chunk_id(cls, value: str | None) -> str | None:
        """Reject a blank chunk identifier while allowing unknown IDs."""
        if value is not None and not value.strip():
            raise ValueError("chunk_id must be null or non-blank")
        return value


class RetrievalFilters(BaseModel):
    """Safe exact-match filters supported by the embedding/indexing payload schema.

    Legal assumptions:
        These filters do not implement temporal validity. dense retrieval baseline must not
        claim point-in-time legal answering because the current indexed
        temporal metadata is intentionally nullable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    law_id: str | None = None
    chunk_kind: str | None = None
    level: Literal["article", "clause", "point"] | None = None
    article_number: str | None = None
    source_domain: str | None = None
    exclude_repealed: bool = False

    @field_validator("law_id", "chunk_kind", "article_number", "source_domain")
    @classmethod
    def validate_optional_filter_strings(cls, value: str | None) -> str | None:
        """Trim and reject blank optional filter values."""
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("filter values must be null or non-blank")
        return trimmed

    def has_conditions(self) -> bool:
        """Return whether this filter set should produce a Qdrant filter."""
        return any(
            (
                self.law_id,
                self.chunk_kind,
                self.level,
                self.article_number,
                self.source_domain,
                self.exclude_repealed,
            )
        )


class RetrievalQuery(BaseModel):
    """Validated dense retrieval request.

    Attributes:
        query: Vietnamese legal question or search phrase.
        top_k: Number of dense Qdrant results requested.
        collection_name: Existing Qdrant collection to query.
        filters: Optional exact-match payload filters.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(..., min_length=1)
    top_k: int = Field(DEFAULT_TOP_K, gt=0)
    collection_name: str = Field(DEFAULT_COLLECTION_NAME, min_length=1)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)

    @field_validator("query", "collection_name")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        """Trim and reject blank query or collection strings."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("value must not be blank")
        return trimmed


class RetrievedChunk(BaseModel):
    """One payload-backed legal retrieval candidate.

    Missing optional payload fields remain ``None`` or empty. Missing critical
    fields are recorded in ``issues`` so retrieval can complete without hiding
    traceability gaps.
    """

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(..., ge=1)
    score: float
    point_id: str | None = None
    chunk_id: str | None = None
    law_id: str | None = None
    law_name: str | None = None
    level: str | None = None
    chunk_kind: str | None = None
    article_number: str | None = None
    article_title: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    citation: str | None = None
    hierarchy_path: str | None = None
    source_node_id: str | None = None
    parent_article_node_id: str | None = None
    parent_chunk_id: str | None = None
    text: str | None = None
    parent_text: str | None = None
    text_hash: str | None = None
    parent_text_hash: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    source_type: str | None = None
    source_file: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    is_empty_or_repealed: bool | None = None
    is_source_unit_repealed: bool | None = None
    embedding_model: str | None = None
    embedding_revision: str | None = None
    indexing_run_id: str | None = None
    payload_schema_version: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    status: str | None = None
    domain_tags: list[str] = Field(default_factory=list)
    issues: list[RetrievalIssue] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        """Require Qdrant scores to be numeric and finite."""
        if not math.isfinite(value):
            raise ValueError("score must be finite")
        return value

    @field_validator(
        "point_id",
        "chunk_id",
        "law_id",
        "law_name",
        "level",
        "chunk_kind",
        "article_number",
        "article_title",
        "clause_number",
        "point_label",
        "citation",
        "hierarchy_path",
        "source_node_id",
        "parent_article_node_id",
        "parent_chunk_id",
        "text",
        "parent_text",
        "text_hash",
        "parent_text_hash",
        "source_url",
        "source_domain",
        "source_type",
        "source_file",
        "embedding_model",
        "embedding_revision",
        "indexing_run_id",
        "payload_schema_version",
        "effective_date",
        "expiry_date",
        "status",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        """Normalize blank optional strings to ``None``."""
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("domain_tags")
    @classmethod
    def validate_domain_tags(cls, values: list[str]) -> list[str]:
        """Preserve domain tags while dropping blank values."""
        return [value for value in values if value.strip()]


class RetrievalResult(BaseModel):
    """Dense retrieval response for one query.

    Attributes:
        query: Original normalized query text.
        collection_name: Qdrant collection queried.
        vector_name: Named vector used for dense search.
        top_k: Requested top-k result count.
        elapsed_ms: Wall-clock retrieval time in milliseconds.
        query_vector_dimension: Dimension of the validated dense query vector,
            or 0 for retrieval methods that do not use dense vectors.
        results: Ranked retrieval candidates.
        issues: Retrieval-level issues not tied to a specific chunk.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    collection_name: str = Field(..., min_length=1)
    vector_name: str = Field(DEFAULT_DENSE_VECTOR_NAME, min_length=1)
    top_k: int = Field(..., gt=0)
    elapsed_ms: float = Field(..., ge=0.0)
    query_vector_dimension: int = Field(..., ge=0)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    results: list[RetrievedChunk] = Field(default_factory=list)
    issues: list[RetrievalIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalEmbeddingConfig(BaseModel):
    """Embedding settings used by the dense retrieval baseline query embedder."""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field("BAAI/bge-m3", min_length=1)
    model_revision: str | None = None
    device: Literal["auto", "cpu", "cuda"] = "cpu"
    batch_size: int = Field(1, gt=0)
    max_length: int = Field(8192, gt=0)
    normalize_embeddings: bool = True


class RetrievalQdrantConfig(BaseModel):
    """Read-only Qdrant settings for dense retrieval."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field("http://localhost:6333", min_length=1)
    collection_name: str = Field(DEFAULT_COLLECTION_NAME, min_length=1)
    timeout_seconds: float = Field(60, gt=0)


class DenseRetrievalConfig(BaseModel):
    """Dense retriever defaults for dense retrieval baseline."""

    model_config = ConfigDict(extra="forbid")

    vector_name: str = Field(DEFAULT_DENSE_VECTOR_NAME, min_length=1)
    expected_vector_dim: int = Field(DEFAULT_DENSE_DIMENSION, gt=0)
    top_k: int = Field(DEFAULT_TOP_K, gt=0)


class RetrievalConfig(BaseModel):
    """Complete dense retrieval baseline retrieval configuration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    embedding: RetrievalEmbeddingConfig = Field(default_factory=RetrievalEmbeddingConfig)
    qdrant: RetrievalQdrantConfig = Field(default_factory=RetrievalQdrantConfig)
    dense_retrieval: DenseRetrievalConfig = Field(default_factory=DenseRetrievalConfig)

    @model_validator(mode="after")
    def validate_query_embedding_contract(self) -> RetrievalConfig:
        """Require the configured dense vector dimension to match BGE-M3 v1."""
        if self.dense_retrieval.expected_vector_dim != DEFAULT_DENSE_DIMENSION:
            raise ValueError(
                "dense retrieval baseline expects 1024-dimensional BGE-M3 dense vectors"
            )
        return self
