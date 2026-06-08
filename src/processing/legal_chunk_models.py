"""Canonical schemas for Phase 6 parent-child legal chunking.

The models in this module describe the chunk-level data contracts produced by
the Phase 6 chunker. Each chunk preserves citation traceability to the
original legal hierarchy and carries deterministic identifiers, offsets, and
hashes suitable for embedding and retrieval pipelines.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChunkingIssueCode(StrEnum):
    """Stable warning and error codes emitted by the Phase 6 chunker."""

    MISSING_HIERARCHY_INPUT = "MISSING_HIERARCHY_INPUT"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    EXISTING_OUTPUT_BLOCKED = "EXISTING_OUTPUT_BLOCKED"
    OUTPUT_WRITE_FAILED = "OUTPUT_WRITE_FAILED"
    EMPTY_ARTICLE_CHUNK = "EMPTY_ARTICLE_CHUNK"
    MISSING_ARTICLE_PARENT = "MISSING_ARTICLE_PARENT"
    OFFSET_MISMATCH = "OFFSET_MISMATCH"
    TEXT_MISMATCH = "TEXT_MISMATCH"
    PARENT_TEXT_MISMATCH = "PARENT_TEXT_MISMATCH"
    SOURCE_NODE_NOT_FOUND = "SOURCE_NODE_NOT_FOUND"
    INVALID_PARENT_ARTICLE = "INVALID_PARENT_ARTICLE"
    DUPLICATE_CHUNK_ID = "DUPLICATE_CHUNK_ID"
    CHILD_OUTSIDE_ARTICLE = "CHILD_OUTSIDE_ARTICLE"
    EMPTY_CHUNK_TEXT = "EMPTY_CHUNK_TEXT"
    INVALID_CHUNK_LEVEL = "INVALID_CHUNK_LEVEL"
    TREE_VALIDATION_FAILED = "TREE_VALIDATION_FAILED"
    JSONL_VALIDATION_FAILED = "JSONL_VALIDATION_FAILED"


class ChunkingLevel(StrEnum):
    """Allowed chunk hierarchy levels produced by the Phase 6 chunker."""

    ARTICLE = "article"
    CLAUSE = "clause"
    POINT = "point"


class ChunkingStatus(StrEnum):
    """Per-law batch chunking result statuses."""

    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    FAILED = "failed"


class ChunkingMetadata(BaseModel):
    """Deterministic metadata attached to each legal chunk.

    Attributes:
        is_empty_or_repealed: Whether the source Article is empty, repealed,
            or a placeholder. Non-blocking for chunking; preserves citation
            traceability.
        is_source_unit_repealed: Whether the selected source unit itself
            contains a repealed placeholder, including Clause and Point chunks.
        source_warnings: Phase 5 warning codes that affect this chunk's
            source node (e.g., EMPTY_ARTICLE_NODE, NODE_ID_COLLISION_RESOLVED).
        caveat_references: Phase 5 caveat reference strings for this chunk's
            source node, if any.
    """

    model_config = ConfigDict(extra="forbid")

    is_empty_or_repealed: bool = Field(
        False,
        description="Article is empty, repealed, or placeholder-like",
    )
    is_source_unit_repealed: bool = Field(
        False,
        description="Selected Article, Clause, or Point unit is repealed or placeholder-like",
    )
    source_warnings: list[str] = Field(
        default_factory=list,
        description="Phase 5 warning codes affecting this chunk's source node",
    )
    caveat_references: list[str] = Field(
        default_factory=list,
        description="Phase 5 caveat references for this chunk's source node",
    )


class ChunkingIssue(BaseModel):
    """Structured chunk-level issue or warning.

    Attributes:
        code: Stable chunking issue code.
        message: Human-readable description of the issue.
        law_id: Law identifier associated with the issue.
        chunk_id: Affected chunk identifier, when available.
        source_node_id: Affected source node identifier, when available.
        start_offset: Optional inclusive source offset for the issue.
        end_offset: Optional exclusive source offset for the issue.
        context: Small structured payload with issue-specific facts.
    """

    model_config = ConfigDict(extra="forbid")

    code: ChunkingIssueCode = Field(..., description="Stable chunking issue code")
    message: str = Field(..., min_length=1, description="Human-readable issue message")
    law_id: str = Field(..., min_length=1, description="Stable law identifier")
    chunk_id: str | None = Field(None, description="Affected chunk ID")
    source_node_id: str | None = Field(None, description="Affected source node ID")
    start_offset: int | None = Field(None, ge=0, description="Inclusive source offset")
    end_offset: int | None = Field(None, ge=0, description="Exclusive source offset")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Issue-specific context"
    )

    @model_validator(mode="after")
    def validate_offsets(self) -> ChunkingIssue:
        """Ensure nullable issue offsets are valid when both are present."""
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must be greater than or equal to start_offset")
        return self


class ChunkValidationSummary(BaseModel):
    """Aggregated validation counters for Phase 6 chunk and JSONL checks.

    Attributes:
        total_chunks_checked: Number of chunks inspected by the validator.
        duplicate_chunk_ids: Duplicate chunk identifiers detected.
        missing_source_nodes: Chunks whose source node is absent from hierarchy.
        invalid_parent_articles: Chunks with missing or non-Article parents.
        invalid_offsets: Offset-order or containment violations.
        text_mismatches: Chunks whose text differs from source node text.
        parent_text_mismatches: Chunks whose parent text differs from Article text.
        invalid_chunk_levels: Non Article/Clause/Point chunk rows.
        jsonl_lines_checked: JSONL rows parsed and validated.
        jsonl_parse_errors: JSONL rows that failed JSON parsing or schema validation.
        report_count_mismatches: Report totals that do not match chunk rows.
    """

    model_config = ConfigDict(extra="forbid")

    total_chunks_checked: int = Field(0, ge=0)
    duplicate_chunk_ids: int = Field(0, ge=0)
    missing_source_nodes: int = Field(0, ge=0)
    invalid_parent_articles: int = Field(0, ge=0)
    invalid_offsets: int = Field(0, ge=0)
    text_mismatches: int = Field(0, ge=0)
    parent_text_mismatches: int = Field(0, ge=0)
    invalid_chunk_levels: int = Field(0, ge=0)
    jsonl_lines_checked: int = Field(0, ge=0)
    jsonl_parse_errors: int = Field(0, ge=0)
    report_count_mismatches: int = Field(0, ge=0)


def _compute_text_hash(text: str) -> str:
    """Return the SHA-256 hex digest of the UTF-8 encoded text.

    Args:
        text: Input text to hash.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LegalChunk(BaseModel):
    """One deterministic parent-child chunk from a legal hierarchy document.

    Attributes:
        schema_version: Chunk schema version for downstream compatibility.
        chunker_version: Version of the chunking algorithm that produced
            this chunk.
        chunk_id: Deterministic unique identifier across the full corpus.
            Format: ``{source_node_id}__chunk``.
        law_id: Stable law identifier.
        law_name: Official legal document name from hierarchy metadata.
        source_url: Trusted source URL from hierarchy metadata.
        source_domain: Trusted source domain from hierarchy metadata.
        source_type: Source content type from hierarchy metadata.
        source_file: Path to the source ``hierarchy.json`` file.
        level: Chunk hierarchy level — article, clause, or point.
        chunk_kind: Descriptive kind string: ``article_level``,
            ``article_level_empty``, ``clause_level``, or ``point_level``.
        source_node_id: ``LegalNode.node_id`` of the source node.
        parent_article_node_id: ``LegalNode.node_id`` of the parent Article.
        parent_chunk_id: Logical key for the parent Article context chunk.
            Format: ``{article_node_id}__parent``.
        article_number: Displayed article number from the source node,
            or from the parent Article node for clause/point chunks.
        article_title: Article title from the parent Article node.
        clause_number: Displayed clause number from the source node,
            ``None`` for article-level or point-only chunks.
        point_label: Displayed point label from the source node,
            ``None`` for article-level or clause-level chunks.
        citation: Vietnamese legal citation string.
        hierarchy_path: Display path from Law to this chunk's level,
            using real existing hierarchy segments only.
        text: Embedding unit — exact Article, Clause, or Point text.
        parent_text: Full Article text for LLM context.
        start_offset: Inclusive source offset of ``text`` within the
            normalized legal document.
        end_offset: Exclusive source offset of ``text``.
        article_start_offset: Inclusive offset of the parent Article node.
        article_end_offset: Exclusive offset of the parent Article node.
        text_hash: SHA-256 hex digest of ``text``.
        parent_text_hash: SHA-256 hex digest of ``parent_text``.
        metadata: Deterministic chunk metadata including empty/repealed
            flags and Phase 5 warning references.
        warnings: Structured chunk-level issues or warnings.

    Legal assumptions:
        Chunks are produced deterministically from ``LegalHierarchyDocument``
        nodes only. No LLM-based text cutting, rewriting, or repair is
        applied. Citation format follows Vietnamese legal convention.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1, description="Chunk schema version")
    chunker_version: str = Field(..., min_length=1, description="Chunker version")
    chunk_id: str = Field(..., min_length=1, description="Deterministic chunk ID")
    law_id: str = Field(..., min_length=1, description="Stable law identifier")
    law_name: str = Field(..., min_length=1, description="Official legal document name")
    source_url: str = Field(..., min_length=1, description="Trusted source URL")
    source_domain: str = Field(..., min_length=1, description="Trusted source domain")
    source_type: str = Field(..., min_length=1, description="Source content type")
    source_file: str = Field(..., min_length=1, description="Source hierarchy.json path")
    level: ChunkingLevel = Field(..., description="Chunk hierarchy level")
    chunk_kind: str = Field(..., min_length=1, description="Descriptive chunk kind")
    source_node_id: str = Field(..., min_length=1, description="Source LegalNode ID")
    parent_article_node_id: str = Field(
        ..., min_length=1, description="Parent Article LegalNode ID"
    )
    parent_chunk_id: str = Field(
        ..., min_length=1, description="Parent Article context chunk ID"
    )
    article_number: str | None = Field(None, description="Displayed article number")
    article_title: str | None = Field(None, description="Article title")
    clause_number: str | None = Field(None, description="Displayed clause number")
    point_label: str | None = Field(None, description="Displayed point label")
    citation: str = Field(..., min_length=1, description="Vietnamese legal citation")
    hierarchy_path: str = Field(
        "", min_length=0, description="Display hierarchy path"
    )
    text: str = Field(..., min_length=1, description="Chunk embedding text")
    parent_text: str = Field(
        ..., min_length=1, description="Full Article text for LLM context"
    )
    start_offset: int = Field(..., ge=0, description="Inclusive source offset")
    end_offset: int = Field(..., ge=0, description="Exclusive source offset")
    article_start_offset: int = Field(
        ..., ge=0, description="Inclusive parent Article offset"
    )
    article_end_offset: int = Field(
        ..., ge=0, description="Exclusive parent Article offset"
    )
    text_hash: str = Field("", min_length=0, description="SHA-256 of text")
    parent_text_hash: str = Field(
        "", min_length=0, description="SHA-256 of parent_text"
    )
    metadata: ChunkingMetadata = Field(
        default_factory=ChunkingMetadata, description="Typed chunk metadata"
    )
    warnings: list[ChunkingIssue] = Field(
        default_factory=list, description="Chunk-level issues"
    )

    @model_validator(mode="after")
    def validate_offset_order(self) -> LegalChunk:
        """Validate that chunk offsets represent a non-empty slice."""
        if self.end_offset <= self.start_offset:
            raise ValueError(
                "end_offset must be greater than start_offset"
            )
        return self

    @model_validator(mode="after")
    def validate_article_offsets(self) -> LegalChunk:
        """Validate that chunk offsets fit inside parent Article offsets."""
        if self.start_offset < self.article_start_offset:
            raise ValueError(
                "start_offset must be >= article_start_offset"
            )
        if self.end_offset > self.article_end_offset:
            raise ValueError(
                "end_offset must be <= article_end_offset"
            )
        return self

    def compute_hashes(self) -> LegalChunk:
        """Return a copy with text_hash and parent_text_hash populated.

        Returns:
            A new LegalChunk with deterministic SHA-256 hashes computed
            from text and parent_text.
        """
        return self.model_copy(
            update={
                "text_hash": _compute_text_hash(self.text),
                "parent_text_hash": _compute_text_hash(self.parent_text),
            },
            deep=True,
        )


class ChunkingSummary(BaseModel):
    """Aggregated counts for a single law's chunking result.

    Attributes:
        law_id: Stable law identifier.
        status: Per-law chunking status.
        input_path: Source `hierarchy.json` path for this law, when known.
        total_chunks: Total number of chunks produced for this law.
        chunks_by_level: Count of chunks grouped by level string.
        article_level_chunks: Count of article-level chunks.
        clause_level_chunks: Count of clause-level chunks.
        point_level_chunks: Count of point-level chunks.
        empty_or_repealed_chunks: Count of empty/repealed article chunks.
        long_parent_text_chunks: Count of chunks whose Article context may be
            too long for later retrieval context packing.
        warning_count: Number of chunking warnings for this law.
        error_count: Number of chunking errors for this law.
    """

    model_config = ConfigDict(extra="forbid")

    law_id: str = Field(..., min_length=1)
    status: ChunkingStatus = Field(ChunkingStatus.SUCCESS)
    input_path: str | None = Field(None)
    total_chunks: int = Field(0, ge=0)
    chunks_by_level: dict[str, int] = Field(default_factory=dict)
    article_level_chunks: int = Field(0, ge=0)
    clause_level_chunks: int = Field(0, ge=0)
    point_level_chunks: int = Field(0, ge=0)
    empty_or_repealed_chunks: int = Field(0, ge=0)
    long_parent_text_chunks: int = Field(0, ge=0)
    warning_count: int = Field(0, ge=0)
    error_count: int = Field(0, ge=0)


class ChunkingReport(BaseModel):
    """Canonical Phase 6 batch chunking report.

    Written to ``artifacts/reports/chunking/chunking_report.json``.
    Helps decide whether Phase 7 embedding/indexing is safe.

    Attributes:
        schema_version: Report schema version.
        chunker_version: Chunker version that produced this report.
        started_at: ISO-8601 UTC start timestamp.
        finished_at: ISO-8601 UTC finish timestamp.
        duration_seconds: Total batch duration in seconds.
        input_dir: Directory containing ``{LAW_ID}/hierarchy.json`` inputs.
        output_path: Path to the written ``legal_chunks.jsonl``.
        total_laws: Total number of laws processed.
        successful: Laws that chunked without warnings.
        success_with_warnings: Laws that chunked with non-fatal warnings.
        failed: Laws that failed to chunk.
        total_chunks: Total chunks across all successful laws.
        chunks_by_level: Count of chunks grouped by level string.
        chunks_by_law: Count of chunks per law ID.
        empty_or_repealed_article_chunks: Total empty/repealed article chunks.
        warnings: Batch-level chunking warnings.
        errors: Batch-level chunking errors.
        validation_summary: Chunk validator and JSONL validation counters.
        law_summaries: Per-law chunking summaries.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    chunker_version: str = Field(..., min_length=1)
    started_at: str = Field(..., min_length=1)
    finished_at: str = Field(..., min_length=1)
    duration_seconds: float = Field(..., ge=0.0)
    input_dir: str = Field(..., min_length=1)
    output_path: str = Field(..., min_length=1)
    total_laws: int = Field(..., ge=0)
    successful: int = Field(..., ge=0)
    success_with_warnings: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    total_chunks: int = Field(..., ge=0)
    chunks_by_level: dict[str, int] = Field(default_factory=dict)
    chunks_by_law: dict[str, int] = Field(default_factory=dict)
    empty_or_repealed_article_chunks: int = Field(0, ge=0)
    warnings: list[ChunkingIssue] = Field(default_factory=list)
    errors: list[ChunkingIssue] = Field(default_factory=list)
    validation_summary: ChunkValidationSummary = Field(default_factory=ChunkValidationSummary)
    law_summaries: list[ChunkingSummary] = Field(default_factory=list)
