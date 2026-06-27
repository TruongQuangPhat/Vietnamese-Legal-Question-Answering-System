"""Typed contracts for embedding and indexing.

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

    ``embedding_text`` is a separate immutable value derived by a later workflow.
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
    warnings: list[ChunkingIssue] = Field(default_factory=list)

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

    Sparse vectors are disabled by default in the indexing configuration. When a
    later workflow emits one, this contract requires aligned non-empty indices
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
    """Legal metadata payload stored beside vectors in a later workflow.

    Temporal and domain-enrichment fields are nullable or empty by default.
    Their absence must be preserved rather than inferred during embedding/indexing.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    law_id: str = Field(..., min_length=1)
    law_name: str = Field(..., min_length=1)
    level: ChunkingLevel
    chunk_kind: str = Field(..., min_length=1)
    article_number: str | None = None
    article_title: str | None = None
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
        "article_title",
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
    """Paths to validated processed JSONL input and its gate configuration."""

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
    """Complete embedding and indexing configuration contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
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


class ProcessedValidationSummary(BaseModel):
    """Validated readiness facts from the processed JSONL validation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["not_run", "pass", "pass_with_warnings", "fail"] = "not_run"
    report_path: str | None = None
    input_path: str | None = None
    errors_total: int = Field(0, ge=0)
    invalid_chunks: int = Field(0, ge=0)
    warnings_total: int = Field(0, ge=0)
    embedding_ready: bool = False
    payload_ready_rate: float = Field(0.0, ge=0.0, le=1.0)


class ProcessedCorpusValidationSummary(BaseModel):
    """Operational processed-corpus validation facts for official indexing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field("0.1.0", min_length=1)
    report_type: Literal["processed_corpus_validation_summary"] = (
        "processed_corpus_validation_summary"
    )
    run_type: Literal["official_full_indexing"] = "official_full_indexing"
    workflow_name: Literal["corpus_validation"] = "corpus_validation"
    input_path: str = Field(..., min_length=1)
    total_lines: int = Field(..., ge=0)
    valid_chunks: int = Field(..., ge=0)
    invalid_chunks: int = Field(..., ge=0)
    errors_total: int = Field(..., ge=0)
    warnings_total: int = Field(..., ge=0)
    embedding_ready: bool
    readiness_status: str = Field(..., min_length=1)
    payload_ready_rate: float = Field(..., ge=0.0, le=1.0)
    contamination_warnings: int = Field(..., ge=0)
    short_text_warnings: int = Field(..., ge=0)
    chunks_by_level: dict[str, int]
    chunks_by_law: dict[str, int]
    text_length_summary: dict[str, Any]
    parent_text_length_summary: dict[str, Any]
    repealed_metadata_summary: dict[str, Any]
    warning_distribution_summary: dict[str, Any]
    blocking_reasons: list[str] = Field(default_factory=list)


class PayloadIndexSpec(BaseModel):
    """One deterministic Qdrant payload index requested during collection setup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_name: str = Field(..., min_length=1)
    field_schema: Literal["keyword", "integer", "float", "text", "bool", "datetime", "uuid"]

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, value: str) -> str:
        """Reject whitespace-only payload field paths."""
        if not value.strip():
            raise ValueError("field_name must not be blank")
        return value


class CollectionSchemaPlan(BaseModel):
    """Validated, non-executing plan for one Qdrant collection schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection_name: str = Field(..., min_length=1)
    dense_vector_name: str = Field(..., min_length=1)
    dense_dimension: int = Field(..., gt=0)
    distance: Literal["Cosine", "Dot", "Euclid", "Manhattan"] = "Cosine"
    sparse_enabled: bool = False
    sparse_vector_name: str | None = None
    recreate: bool = False
    payload_indexes: list[PayloadIndexSpec] = Field(default_factory=list)

    @field_validator("collection_name", "dense_vector_name")
    @classmethod
    def validate_required_names(cls, value: str) -> str:
        """Reject whitespace-only collection and dense-vector names."""
        if not value.strip():
            raise ValueError("collection and dense vector names must not be blank")
        return value

    @field_validator("sparse_vector_name")
    @classmethod
    def validate_optional_sparse_name(cls, value: str | None) -> str | None:
        """Reject a blank sparse-vector name when one is provided."""
        if value is not None and not value.strip():
            raise ValueError("sparse_vector_name must be null or non-blank")
        return value

    @model_validator(mode="after")
    def validate_sparse_configuration(self) -> CollectionSchemaPlan:
        """Require a distinct sparse name only when sparse vectors are enabled."""
        if self.sparse_enabled and self.sparse_vector_name is None:
            raise ValueError("sparse_vector_name is required when sparse vectors are enabled")
        if self.sparse_enabled and self.sparse_vector_name == self.dense_vector_name:
            raise ValueError("sparse vector name must differ from dense vector name")
        return self


class CollectionSetupResult(BaseModel):
    """Outcome of validating or creating a Qdrant collection schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection_name: str = Field(..., min_length=1)
    created: bool = False
    recreated: bool = False
    already_exists: bool = False
    dense_vector_name: str = Field(..., min_length=1)
    dense_dimension: int = Field(..., gt=0)
    distance: Literal["Cosine", "Dot", "Euclid", "Manhattan"]
    sparse_enabled: bool = False
    sparse_vector_name: str | None = None
    payload_indexes_requested: list[PayloadIndexSpec] = Field(default_factory=list)
    payload_indexes_created: list[str] = Field(default_factory=list)
    status: Literal["created", "recreated", "already_exists"]
    issues: list[IndexingIssue] = Field(default_factory=list)


class IndexingReport(BaseModel):
    """Typed operational report for planned and executed indexing runs."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    report_type: Literal["indexing_report"] = "indexing_report"
    run_type: str = Field("development_indexing", min_length=1)
    workflow_name: Literal["embedding_indexing"] = "embedding_indexing"
    status: Literal[
        "planned",
        "running",
        "completed",
        "completed_with_warnings",
        "dry_run",
        "success",
        "partial_success",
        "failed",
    ] = "planned"
    processed_validation_status: Literal[
        "not_run",
        "pass",
        "pass_with_warnings",
        "fail",
    ] = "not_run"
    processed_validation_report_path: str | None = None
    processed_validation_errors_total: int = Field(0, ge=0)
    processed_validation_invalid_chunks: int = Field(0, ge=0)
    processed_validation_warnings_total: int = Field(0, ge=0)
    processed_validation_embedding_ready: bool = False
    processed_validation_payload_ready_rate: float = Field(0.0, ge=0.0, le=1.0)
    input_chunks_path: str = Field(..., min_length=1)
    input_path: str | None = None
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
    text_template: EmbeddingTextTemplate = EmbeddingTextTemplate.TEXT_ONLY
    law_id_filter: str | None = None
    limit: int | None = Field(None, ge=0)
    batch_size: int = Field(1, gt=0)
    dry_run: bool = False
    indexing_run_id: str | None = None
    total_seen: int = Field(0, ge=0)
    planned_count: int = Field(0, ge=0)
    would_embed_count: int = Field(0, ge=0)
    would_upsert_count: int = Field(0, ge=0)
    embedded_count: int = Field(0, ge=0)
    upserted_count: int = Field(0, ge=0)
    failed_count: int = Field(0, ge=0)
    skipped_count: int = Field(0, ge=0)
    failed_chunk_ids: list[str] = Field(default_factory=list)
    runtime_seconds: float = Field(0.0, ge=0.0)
    throughput_chunks_per_second: float = Field(0.0, ge=0.0)
    device: str | None = None
    allow_full_corpus: bool = False
    resume: bool = False
    checkpoint_path: str | None = None
    checkpoint_processed_count: int = Field(0, ge=0)
    skipped_due_to_checkpoint_count: int = Field(0, ge=0)
    resumed_from_indexing_run_id: str | None = None
    max_retries: int = Field(0, ge=0)
    retry_backoff_seconds: float = Field(0.0, ge=0.0)
    retry_attempts_total: int = Field(0, ge=0)
    retried_batch_count: int = Field(0, ge=0)
    permanently_failed_batch_count: int = Field(0, ge=0)
    started_at: str | None = None
    finished_at: str | None = None
    qdrant_points_count_before: int | None = Field(None, ge=0)
    qdrant_points_count_after: int | None = Field(None, ge=0)
    qdrant_indexed_vectors_count_after: int | None = Field(None, ge=0)
    expected_min_points_after: int | None = Field(None, ge=0)
    count_reconciliation_status: Literal["not_run", "pass", "warning"] = "not_run"


class IndexingCheckpoint(BaseModel):
    """Compatibility-bound progress record for a resumable indexing run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field("0.1.0", min_length=1)
    checkpoint_type: Literal["indexing_checkpoint"] = "indexing_checkpoint"
    run_type: str = Field("development_indexing", min_length=1)
    workflow_name: Literal["embedding_indexing"] = "embedding_indexing"
    indexing_run_id: str = Field(..., min_length=1)
    collection_name: str = Field(..., min_length=1)
    dense_vector_name: str = Field(..., min_length=1)
    dense_dimension: int = Field(..., gt=0)
    embedding_model: str = Field(..., min_length=1)
    embedding_revision: str | None = None
    text_template: EmbeddingTextTemplate
    input_path: str = Field(..., min_length=1)
    law_id_filter: str | None = None
    payload_schema_version: str = Field(..., min_length=1)
    processed_chunk_ids: list[str] = Field(default_factory=list)
    processed_count: int = Field(0, ge=0)
    upserted_count: int = Field(0, ge=0)
    failed_chunk_ids: list[str] = Field(default_factory=list)
    started_at: str | None = None
    updated_at: str | None = None

    @model_validator(mode="after")
    def validate_progress_consistency(self) -> IndexingCheckpoint:
        """Reject internally inconsistent or ambiguous resume progress."""
        processed_ids = set(self.processed_chunk_ids)
        failed_ids = set(self.failed_chunk_ids)
        if len(processed_ids) != len(self.processed_chunk_ids):
            raise ValueError("processed_chunk_ids must not contain duplicates")
        if len(failed_ids) != len(self.failed_chunk_ids):
            raise ValueError("failed_chunk_ids must not contain duplicates")
        if processed_ids & failed_ids:
            raise ValueError("processed and failed chunk IDs must be disjoint")
        if self.processed_count != len(self.processed_chunk_ids):
            raise ValueError("processed_count must match processed_chunk_ids length")
        if self.upserted_count != len(self.processed_chunk_ids):
            raise ValueError("upserted_count must match processed_chunk_ids length")
        return self


class CollectionValidationResult(BaseModel):
    """Read-only validation result for one Qdrant collection schema."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pass", "warning", "failed"]
    collection_status: str | None = None
    points_count: int | None = Field(None, ge=0)
    indexed_vectors_count: int | None = Field(None, ge=0)
    dense_vector_name: str = Field(..., min_length=1)
    dense_dimension: int = Field(..., gt=0)
    distance: str = Field(..., min_length=1)
    payload_indexes_present: list[str] = Field(default_factory=list)
    payload_indexes_missing: list[str] = Field(default_factory=list)
    issues: list[IndexingIssue] = Field(default_factory=list)


class SampledPointSummary(BaseModel):
    """Non-vector diagnostic summary for one sampled Qdrant point."""

    model_config = ConfigDict(extra="forbid")

    point_id: str = Field(..., min_length=1)
    chunk_id: str | None = None
    payload_complete: bool
    vector_present: bool | None = None
    vector_dimension: int | None = Field(None, ge=0)
    vector_finite: bool | None = None
    missing_payload_fields: list[str] = Field(default_factory=list)
    issues: list[IndexingIssue] = Field(default_factory=list)


class PointValidationResult(BaseModel):
    """Aggregate payload and dense-vector validation for sampled points."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pass", "warning", "failed"]
    payload_status: Literal["pass", "warning", "failed"]
    vector_status: Literal["not_run", "pass", "warning", "failed"]
    sampled_point_count: int = Field(0, ge=0)
    points: list[SampledPointSummary] = Field(default_factory=list)
    issues: list[IndexingIssue] = Field(default_factory=list)


class PayloadFilterCheck(BaseModel):
    """One exact-match payload filter to validate against Qdrant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    field_name: str = Field(..., min_length=1)
    match_value: str | bool | int | float


class PayloadFilterCheckResult(BaseModel):
    """Read-only result for one exact-match payload filter."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    field_name: str = Field(..., min_length=1)
    match_value: str | bool | int | float
    returned_count: int = Field(0, ge=0)
    status: Literal["pass", "warning", "failed"]
    sample_point_ids: list[str] = Field(default_factory=list)
    issues: list[IndexingIssue] = Field(default_factory=list)


class FilterValidationResult(BaseModel):
    """Aggregate validation result for deterministic payload filters."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pass", "warning", "failed"]
    checks: list[PayloadFilterCheckResult] = Field(default_factory=list)
    issues: list[IndexingIssue] = Field(default_factory=list)


class RetrievalSanityQuery(BaseModel):
    """One bounded dense-query sanity check and its expected hint terms."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_text: str = Field(..., min_length=1)
    expected_hint_terms: list[str] = Field(default_factory=list)

    @field_validator("query_text")
    @classmethod
    def validate_query_text(cls, value: str) -> str:
        """Reject blank query text without rewriting Vietnamese content."""
        if not value.strip():
            raise ValueError("query_text must not be blank")
        return value

    @field_validator("expected_hint_terms")
    @classmethod
    def validate_hint_terms(cls, values: list[str]) -> list[str]:
        """Reject blank expected terms while allowing an empty hint list."""
        if any(not value.strip() for value in values):
            raise ValueError("expected_hint_terms must not contain blank values")
        return values


class RetrievalHitSummary(BaseModel):
    """Compact retrieval result that excludes vector values."""

    model_config = ConfigDict(extra="forbid")

    point_id: str = Field(..., min_length=1)
    score: float
    chunk_id: str | None = None
    citation: str | None = None
    law_id: str | None = None
    level: str | None = None
    chunk_kind: str | None = None
    text_preview: str | None = None


class RetrievalSanityQueryResult(BaseModel):
    """Result of embedding and searching one bounded sanity query."""

    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(..., min_length=1)
    top_k: int = Field(..., gt=0)
    returned_count: int = Field(0, ge=0)
    query_vector_dimension: int | None = Field(None, ge=0)
    expected_hint_terms: list[str] = Field(default_factory=list)
    expected_hints_matched: bool | None = None
    status: Literal["pass", "warning", "failed"]
    results: list[RetrievalHitSummary] = Field(default_factory=list)
    issues: list[IndexingIssue] = Field(default_factory=list)


class RetrievalSanityResult(BaseModel):
    """Aggregate result for small dense retrieval sanity checks."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["not_run", "pass", "warning", "failed"]
    queries_run: int = Field(0, ge=0)
    query_results: list[RetrievalSanityQueryResult] = Field(default_factory=list)
    issues: list[IndexingIssue] = Field(default_factory=list)


class IndexValidationReport(BaseModel):
    """Typed operational report for read-only index validation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field("0.1.0", min_length=1)
    report_type: Literal["index_validation_report"] = "index_validation_report"
    run_type: str = Field("development_index_validation", min_length=1)
    workflow_name: Literal["index_validation"] = "index_validation"
    status: Literal["success", "warning", "failed"]
    collection_name: str = Field(..., min_length=1)
    dense_vector_name: str = Field(..., min_length=1)
    dense_dimension: int = Field(..., gt=0)
    expected_distance: str = Field(..., min_length=1)
    points_count: int | None = Field(None, ge=0)
    indexed_vectors_count: int | None = Field(None, ge=0)
    collection_schema_status: Literal["pass", "warning", "failed"]
    sampled_point_count: int = Field(0, ge=0)
    payload_validation_status: Literal["pass", "warning", "failed"]
    vector_validation_status: Literal["not_run", "pass", "warning", "failed"]
    filter_validation_status: Literal["pass", "warning", "failed"]
    retrieval_sanity_status: Literal["not_run", "pass", "warning", "failed"]
    retrieval_baseline_ready: bool = False
    queries_run: int = Field(0, ge=0)
    collection: CollectionValidationResult
    sampled_points: PointValidationResult
    filters: FilterValidationResult
    retrieval: RetrievalSanityResult
    issues: list[IndexingIssue] = Field(default_factory=list)
    started_at: str
    finished_at: str
    runtime_seconds: float = Field(..., ge=0)
