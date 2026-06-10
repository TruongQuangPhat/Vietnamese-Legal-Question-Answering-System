"""Typed contracts for Phase 8 embedding and indexing.

This module defines configuration, embedding output, vector payload, and
report schemas only. It does not load models, connect to Qdrant, embed text,
index points, retrieve results, or mutate the processed legal corpus.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.processing.legal_chunk_models import ChunkingIssue, ChunkingLevel, ChunkingMetadata


class EmbeddingTextTemplate(StrEnum):
    """Supported deterministic templates for future embedding input assembly."""

    TEXT_ONLY = "text_only"
    CITATION_PLUS_TEXT = "citation_plus_text"
    LAW_CITATION_PLUS_TEXT = "law_citation_plus_text"


class IndexingIssueSeverity(StrEnum):
    """Severity values for structured indexing issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EmbeddingInput(BaseModel):
    """One validated legal chunk prepared for future embedding.

    ``embedding_text`` is a separate immutable value derived by a later slice.
    This contract does not rewrite or mutate the canonical ``LegalChunk.text``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(..., min_length=1)
    law_id: str = Field(..., min_length=1)
    chunk_kind: str = Field(..., min_length=1)
    level: ChunkingLevel
    embedding_text: str = Field(..., min_length=1)
    text_hash: str = Field(..., min_length=1)
    parent_text_hash: str = Field(..., min_length=1)
    citation: str = Field(..., min_length=1)
    hierarchy_path: str = Field(..., min_length=1)
    metadata: ChunkingMetadata | None = None

    @field_validator(
        "chunk_id",
        "law_id",
        "chunk_kind",
        "embedding_text",
        "text_hash",
        "parent_text_hash",
        "citation",
        "hierarchy_path",
    )
    @classmethod
    def validate_non_blank_strings(cls, value: str) -> str:
        """Reject whitespace-only identifiers, hashes, citations, and text."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class DenseEmbedding(BaseModel):
    """Dense vector output for one legal chunk.

    The dimension is measured from actual model output in a later pilot and
    must match the number of finite vector values represented here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(..., min_length=1)
    vector_name: str = Field("dense", min_length=1)
    values: list[float] = Field(..., min_length=1)
    dimension: int = Field(..., gt=0)
    model_name: str = Field(..., min_length=1)
    model_revision: str | None = None

    @field_validator("chunk_id", "vector_name", "model_name")
    @classmethod
    def validate_non_blank_strings(cls, value: str) -> str:
        """Reject whitespace-only dense embedding identifiers."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("model_revision")
    @classmethod
    def validate_optional_revision(cls, value: str | None) -> str | None:
        """Reject a blank model revision while allowing an unspecified revision."""
        if value is not None and not value.strip():
            raise ValueError("model_revision must be null or non-blank")
        return value

    @field_validator("values")
    @classmethod
    def validate_finite_values(cls, values: list[float]) -> list[float]:
        """Require every dense vector value to be finite."""
        if not all(math.isfinite(value) for value in values):
            raise ValueError("dense vector values must be finite")
        return values

    @model_validator(mode="after")
    def validate_dimension(self) -> DenseEmbedding:
        """Require the declared dimension to match the vector length."""
        if self.dimension != len(self.values):
            raise ValueError("dimension must match the number of dense vector values")
        return self


class SparseEmbedding(BaseModel):
    """Optional sparse vector output for one legal chunk.

    Sparse vectors are disabled by default in Slice 8A configuration. When a
    later slice emits one, this contract requires aligned non-empty indices
    and finite values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(..., min_length=1)
    vector_name: str = Field("sparse", min_length=1)
    indices: list[int] = Field(..., min_length=1)
    values: list[float] = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    model_revision: str | None = None

    @field_validator("chunk_id", "vector_name", "model_name")
    @classmethod
    def validate_non_blank_strings(cls, value: str) -> str:
        """Reject whitespace-only sparse embedding identifiers."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("model_revision")
    @classmethod
    def validate_optional_revision(cls, value: str | None) -> str | None:
        """Reject a blank model revision while allowing an unspecified revision."""
        if value is not None and not value.strip():
            raise ValueError("model_revision must be null or non-blank")
        return value

    @field_validator("indices")
    @classmethod
    def validate_indices(cls, indices: list[int]) -> list[int]:
        """Require non-negative sparse vector indices."""
        if any(index < 0 for index in indices):
            raise ValueError("sparse vector indices must be non-negative")
        return indices

    @field_validator("values")
    @classmethod
    def validate_finite_values(cls, values: list[float]) -> list[float]:
        """Require every sparse vector value to be finite."""
        if not all(math.isfinite(value) for value in values):
            raise ValueError("sparse vector values must be finite")
        return values

    @model_validator(mode="after")
    def validate_lengths(self) -> SparseEmbedding:
        """Require one sparse value for every sparse index."""
        if len(self.indices) != len(self.values):
            raise ValueError("sparse indices and values must have equal lengths")
        return self


class VectorPayload(BaseModel):
    """Legal metadata payload stored beside vectors in a later slice.

    Temporal and domain-enrichment fields are nullable or empty by default.
    Their absence must be preserved rather than inferred during Phase 8.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    law_id: str = Field(..., min_length=1)
    law_name: str = Field(..., min_length=1)
    level: ChunkingLevel
    chunk_kind: str = Field(..., min_length=1)
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    citation: str = Field(..., min_length=1)
    hierarchy_path: str = Field(..., min_length=1)
    source_node_id: str = Field(..., min_length=1)
    parent_article_node_id: str = Field(..., min_length=1)
    parent_chunk_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    parent_text: str = Field(..., min_length=1)
    text_hash: str = Field(..., min_length=1)
    parent_text_hash: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=1)
    source_domain: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    source_file: str = Field(..., min_length=1)
    metadata: ChunkingMetadata = Field(default_factory=ChunkingMetadata)
    warnings: list[ChunkingIssue] = Field(default_factory=list)
    embedding_model: str = Field(..., min_length=1)
    embedding_revision: str | None = None
    indexing_run_id: str = Field(..., min_length=1)
    effective_date: str | None = None
    expiry_date: str | None = None
    status: str | None = None
    domain_tags: list[str] = Field(default_factory=list)

    @field_validator(
        "schema_version",
        "chunk_id",
        "law_id",
        "law_name",
        "chunk_kind",
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
        "indexing_run_id",
    )
    @classmethod
    def validate_non_blank_strings(cls, value: str) -> str:
        """Reject whitespace-only required payload fields."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator(
        "article_number",
        "clause_number",
        "point_label",
        "embedding_revision",
        "effective_date",
        "expiry_date",
        "status",
    )
    @classmethod
    def validate_nullable_strings(cls, value: str | None) -> str | None:
        """Allow missing enrichment while rejecting ambiguous blank values."""
        if value is not None and not value.strip():
            raise ValueError("nullable string fields must be null or non-blank")
        return value

    @field_validator("domain_tags")
    @classmethod
    def validate_domain_tags(cls, values: list[str]) -> list[str]:
        """Reject blank domain tags without inventing or normalizing tags."""
        if any(not value.strip() for value in values):
            raise ValueError("domain_tags must not contain blank values")
        return values


class IndexingInputConfig(BaseModel):
    """Paths to validated Phase 7 input and its gate configuration."""

    model_config = ConfigDict(extra="forbid")

    chunks_path: str = Field("data/processed/legal_chunks.jsonl", min_length=1)
    validation_config_path: str = Field(
        "configs/processing/processed_jsonl_validation.yml",
        min_length=1,
    )


class EmbeddingModelConfig(BaseModel):
    """Configuration for a future embedding-model adapter."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field("flagembedding", min_length=1)
    model_name: str = Field(..., min_length=1)
    model_revision: str | None = None
    device: str = Field("auto", min_length=1)
    batch_size: int = Field(8, gt=0)
    max_length: int = Field(8192, gt=0)
    normalize_embeddings: bool = True
    dense_vector_name: str = Field("dense", min_length=1)
    dense_dimension: int | None = Field(None, gt=0)
    dense_dimension_policy: Literal["measure_from_model_output"] = "measure_from_model_output"
    text_template: EmbeddingTextTemplate = EmbeddingTextTemplate.TEXT_ONLY

    @field_validator("provider", "model_name", "device", "dense_vector_name")
    @classmethod
    def validate_non_blank_strings(cls, value: str) -> str:
        """Reject whitespace-only embedding configuration values."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class SparseVectorConfig(BaseModel):
    """Optional sparse-vector configuration, disabled for the dense baseline."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    vector_name: str = Field("sparse", min_length=1)
    provider: str | None = None


class QdrantIndexConfig(BaseModel):
    """Non-executing configuration contract for a future Qdrant adapter."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field("http://localhost:6333", min_length=1)
    collection_name: str = Field(..., min_length=1)
    timeout_seconds: float = Field(60, gt=0)
    distance: Literal["Cosine", "Dot", "Euclid", "Manhattan"] = "Cosine"
    recreate: bool = False
    resume: bool = True
    use_deterministic_uuid: bool = True
    point_id_namespace: str = Field("vnlaw-qa-legal-chunks", min_length=1)

    @field_validator("url", "collection_name", "point_id_namespace")
    @classmethod
    def validate_non_blank_strings(cls, value: str) -> str:
        """Reject whitespace-only Qdrant configuration values."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class PayloadConfig(BaseModel):
    """Controls which traceability fields a later payload builder preserves."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field("0.1.0", min_length=1)
    include_text: bool = True
    include_parent_text: bool = True
    include_warnings: bool = True
    include_hashes: bool = True
    unknown_temporal_metadata_policy: Literal["store_null_do_not_infer"] = "store_null_do_not_infer"


class IndexingRuntimeConfig(BaseModel):
    """Batch, retry, checkpoint, and report settings for future indexing."""

    model_config = ConfigDict(extra="forbid")

    batch_size: int = Field(64, gt=0)
    checkpoint_path: str | None = None
    max_retries: int = Field(3, ge=0)
    retry_backoff_seconds: float = Field(2, ge=0)
    report_path: str = Field(
        "artifacts/reports/indexing/indexing_report.json",
        min_length=1,
    )


class IndexingConfig(BaseModel):
    """Complete Phase 8 embedding and indexing configuration contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    phase: Literal["8"] = "8"
    slice: Literal["8A"] = "8A"
    input: IndexingInputConfig = Field(default_factory=IndexingInputConfig)
    embedding: EmbeddingModelConfig
    sparse: SparseVectorConfig = Field(default_factory=SparseVectorConfig)
    qdrant: QdrantIndexConfig
    payload: PayloadConfig = Field(default_factory=PayloadConfig)
    indexing: IndexingRuntimeConfig = Field(default_factory=IndexingRuntimeConfig)

    @model_validator(mode="after")
    def validate_named_vectors(self) -> IndexingConfig:
        """Prevent dense and enabled sparse vectors from sharing one name."""
        if self.sparse.enabled and self.sparse.vector_name == self.embedding.dense_vector_name:
            raise ValueError("enabled sparse vector name must differ from dense vector name")
        return self


class IndexingIssue(BaseModel):
    """Structured informational, warning, or error issue for an indexing run."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1)
    severity: IndexingIssueSeverity
    message: str = Field(..., min_length=1)
    chunk_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class IndexingReport(BaseModel):
    """Typed report contract for planned and future Phase 8 indexing runs.

    Slice 8A defines this schema only and does not write an official report.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    phase: Literal["8"] = "8"
    slice: str = Field(..., min_length=1)
    status: Literal[
        "planned",
        "running",
        "completed",
        "completed_with_warnings",
        "failed",
    ] = "planned"
    phase7_gate_status: Literal["not_run", "pass", "pass_with_warnings", "fail"] = "not_run"
    input_chunks_path: str = Field(..., min_length=1)
    input_chunk_count: int = Field(0, ge=0)
    expected_chunk_count: int = Field(0, ge=0)
    model_name: str = Field(..., min_length=1)
    model_revision: str | None = None
    dense_vector_name: str = Field("dense", min_length=1)
    dense_dimension: int | None = Field(None, gt=0)
    sparse_enabled: bool = False
    collection_name: str = Field(..., min_length=1)
    indexed_points: int = Field(0, ge=0)
    failed_chunks: int = Field(0, ge=0)
    issues: list[IndexingIssue] = Field(default_factory=list)
    payload_completeness_rate: float = Field(0.0, ge=0.0, le=1.0)
    readiness_for_phase9: bool = False
