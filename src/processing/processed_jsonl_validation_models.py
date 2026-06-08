"""Phase 7 processed JSONL validation models.

This module defines the data contracts for the Phase 7 validation gate:
issue codes, structured issues, the validation report, and the config model.
Phase 7 validates ``data/processed/legal_chunks.jsonl`` as a safe input for
Phase 8 embedding/indexing. It does not implement embedding or indexing.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProcessedJsonlValidationIssueCode(StrEnum):
    """Stable issue and warning codes emitted by the Phase 7 validator."""

    JSONL_PARSE_ERROR = "JSONL_PARSE_ERROR"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    HASH_MISMATCH = "HASH_MISMATCH"
    CITATION_STRUCTURE_MISMATCH = "CITATION_STRUCTURE_MISMATCH"
    HARD_CONTAMINATION_FOUND = "HARD_CONTAMINATION_FOUND"
    WARNING_CONTAMINATION_FOUND = "WARNING_CONTAMINATION_FOUND"
    HIERARCHY_TRACEABILITY_FAILED = "HIERARCHY_TRACEABILITY_FAILED"
    TEXT_MISMATCH_HIERARCHY = "TEXT_MISMATCH_HIERARCHY"
    PARENT_TEXT_MISMATCH_HIERARCHY = "PARENT_TEXT_MISMATCH_HIERARCHY"
    OFFSET_MISMATCH_HIERARCHY = "OFFSET_MISMATCH_HIERARCHY"
    EMBEDDING_READINESS_ISSUE = "EMBEDDING_READINESS_ISSUE"
    PAYLOAD_FIELD_MISSING = "PAYLOAD_FIELD_MISSING"
    VERY_LONG_PARENT_TEXT = "VERY_LONG_PARENT_TEXT"
    COUNT_RECONCILIATION_FAILED = "COUNT_RECONCILIATION_FAILED"


class ProcessedJsonlIssue(BaseModel):
    """Structured Phase 7 validation issue or warning.

    Attributes:
        code: Stable Phase 7 issue code.
        message: Human-readable description of the issue.
        law_id: Law identifier associated with the issue.
        chunk_id: Affected chunk identifier, when available.
        line_number: JSONL line number (1-based), when available.
        context: Small structured payload with issue-specific facts.
    """

    model_config = ConfigDict(extra="forbid")

    code: ProcessedJsonlValidationIssueCode = Field(..., description="Stable Phase 7 issue code")
    message: str = Field(..., min_length=1, description="Human-readable issue message")
    law_id: str = Field(..., min_length=1, description="Stable law identifier")
    chunk_id: str | None = Field(None, description="Affected chunk identifier")
    line_number: int | None = Field(None, ge=1, description="JSONL line number (1-based)")
    context: dict[str, Any] = Field(default_factory=dict, description="Issue-specific context")


class ProcessedJsonlValidationReport(BaseModel):
    """Phase 7 validation gate report for processed chunk JSONL.

    Written to ``artifacts/reports/chunking/processed_jsonl_validation_report.json``.
    Confirms that ``data/processed/legal_chunks.jsonl`` is safe for Phase 8
    embedding/indexing.

    Attributes:
        schema_version: Report schema version.
        validator_version: Validator version that produced this report.
        started_at: ISO-8601 UTC start timestamp.
        finished_at: ISO-8601 UTC finish timestamp.
        duration_seconds: Total validation duration in seconds.
        input_path: Path to the validated JSONL file.
        chunking_report_path: Path to the Phase 6 chunking report.
        hierarchy_dir: Path to hierarchy JSON directory, or null if skipped.
        traceability_checks_skipped: True when hierarchy traceability was not run.
        total_lines: Total JSONL lines processed.
        valid_chunks: Chunks that passed all checks.
        invalid_chunks: Chunks that failed at least one check.
        jsonl_parse_failures: Lines that failed JSON parsing.
        schema_failures: Rows that failed LegalChunk schema validation.
        required_field_failures: Chunks missing required Phase 8 fields.
        duplicate_chunk_ids: Duplicate chunk_id values detected.
        count_reconciliation_failures: Count mismatches against chunking report.
        hash_mismatches: Chunks whose stored hash differs from recomputed hash.
        citation_failures: Chunks with structurally invalid citations.
        traceability_failures: Chunks failing hierarchy traceability checks.
        contamination_failures: Hard-fail contamination markers found.
        contamination_warnings: Warning-only contamination markers found.
        chunks_by_level: Chunk counts grouped by level.
        chunks_by_law: Chunk counts grouped by law_id.
        text_length_summary: Statistics for chunk text lengths.
        parent_text_length_summary: Statistics for parent_text lengths.
        long_parent_text_summary: Parent text length bucket distribution.
        repealed_metadata_summary: Repealed/empty flag distribution.
        payload_readiness_summary: Payload field availability summary.
        embedding_readiness: Embedding contract validation summary.
        sample_failures: Up to max_sample_failures representative error issues.
        warnings: Non-fatal warning issues.
        errors: Hard failure issues.
        status: Overall gate status: pass, pass_with_warnings, or fail.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1, description="Report schema version")
    validator_version: str = Field(..., min_length=1, description="Validator version")
    started_at: str = Field(..., min_length=1, description="ISO-8601 UTC start time")
    finished_at: str = Field(..., min_length=1, description="ISO-8601 UTC finish time")
    duration_seconds: float = Field(..., ge=0.0, description="Validation duration")
    input_path: str = Field(..., min_length=1, description="Validated JSONL path")
    chunking_report_path: str = Field(..., min_length=1, description="Phase 6 chunking report path")
    hierarchy_dir: str | None = Field(None, description="Hierarchy JSON directory path or null")
    traceability_checks_skipped: bool = Field(
        False, description="True if hierarchy traceability was not run"
    )

    total_lines: int = Field(0, ge=0, description="Total JSONL lines processed")
    valid_chunks: int = Field(0, ge=0, description="Chunks passing all checks")
    invalid_chunks: int = Field(0, ge=0, description="Chunks with at least one failure")
    jsonl_parse_failures: int = Field(0, ge=0, description="Lines that failed JSON parsing")
    schema_failures: int = Field(0, ge=0, description="Rows failing LegalChunk schema validation")
    required_field_failures: int = Field(
        0, ge=0, description="Chunks missing required Phase 8 fields"
    )
    duplicate_chunk_ids: int = Field(0, ge=0, description="Duplicate chunk_id values detected")
    count_reconciliation_failures: int = Field(
        0, ge=0, description="Count mismatches against chunking report"
    )
    hash_mismatches: int = Field(0, ge=0, description="Stored hash differs from recomputed hash")
    citation_failures: int = Field(
        0, ge=0, description="Chunks with structurally invalid citations"
    )
    traceability_failures: int = Field(0, ge=0, description="Chunks failing hierarchy traceability")
    contamination_failures: int = Field(
        0, ge=0, description="Hard-fail contamination markers found"
    )
    contamination_warnings: int = Field(
        0, ge=0, description="Warning-only contamination markers found"
    )

    chunks_by_level: dict[str, int] = Field(
        default_factory=dict, description="Chunk counts by level"
    )
    chunks_by_law: dict[str, int] = Field(
        default_factory=dict, description="Chunk counts by law_id"
    )
    text_length_summary: dict[str, Any] = Field(
        default_factory=dict, description="Text length statistics"
    )
    parent_text_length_summary: dict[str, Any] = Field(
        default_factory=dict, description="Parent text length statistics"
    )
    long_parent_text_summary: dict[str, int] = Field(
        default_factory=dict, description="Parent text bucket distribution"
    )
    repealed_metadata_summary: dict[str, int] = Field(
        default_factory=dict, description="Repealed/empty flag distribution"
    )
    payload_readiness_summary: dict[str, Any] = Field(
        default_factory=dict, description="Payload field availability summary"
    )
    embedding_readiness: dict[str, Any] = Field(
        default_factory=dict, description="Embedding contract validation summary"
    )

    sample_failures: list[ProcessedJsonlIssue] = Field(
        default_factory=list, description="Representative error issues (capped)"
    )
    warnings: list[ProcessedJsonlIssue] = Field(
        default_factory=list, description="Non-fatal warning issues"
    )
    errors: list[ProcessedJsonlIssue] = Field(
        default_factory=list, description="Hard failure issues"
    )

    status: Literal["pass", "pass_with_warnings", "fail"] = Field(
        ..., description="Overall gate status"
    )

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> ProcessedJsonlValidationReport:
        """Ensure status reflects errors and warnings."""
        if self.errors and self.status != "fail":
            self.status = "fail"
        if not self.errors and self.warnings and self.status == "pass":
            self.status = "pass_with_warnings"
        if not self.errors and not self.warnings and self.status != "pass":
            self.status = "pass"
        return self


class ProcessedJsonlValidationConfig(BaseModel):
    """Configuration for the Phase 7 processed JSONL validator.

    Loaded from ``configs/processing/processed_jsonl_validation.yml``.
    Controls thresholds, marker lists, and file paths.

    Attributes:
        schema_version: Config schema version.
        validator_version: Validator version string.
        input_path: Path to the processed JSONL file.
        chunking_report_path: Path to the Phase 6 chunking report.
        hierarchy_dir: Path to hierarchy JSON directory.
        report_path: Output path for the validation report.
        require_hierarchy_traceability: Whether hierarchy checks are mandatory.
        max_sample_failures: Max representative failures in report.
        max_sample_warnings: Max representative warnings in report.
        parent_text_short_chars: Upper bound for "short" parent_text.
        parent_text_medium_chars: Upper bound for "medium" parent_text.
        parent_text_long_chars: Upper bound for "long" parent_text.
        parent_text_very_long_chars: Upper bound for "very_long" parent_text.
        hard_contamination_markers: Markers that cause validation failure.
        warning_contamination_markers: Markers that produce warnings only.
        repealed_placeholder_patterns: Regex patterns for repealed placeholders.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1, description="Config schema version")
    validator_version: str = Field(..., min_length=1, description="Validator version")
    input_path: str = Field(
        "data/processed/legal_chunks.jsonl", min_length=1, description="JSONL input path"
    )
    chunking_report_path: str = Field(
        "artifacts/reports/chunking/chunking_report.json",
        min_length=1,
        description="Phase 6 chunking report path",
    )
    hierarchy_dir: str | None = Field(
        "data/interim", description="Hierarchy JSON directory or null"
    )
    report_path: str = Field(
        "artifacts/reports/chunking/processed_jsonl_validation_report.json",
        min_length=1,
        description="Output report path",
    )
    require_hierarchy_traceability: bool = Field(
        True, description="Whether hierarchy traceability is mandatory"
    )
    max_sample_failures: int = Field(50, ge=1, le=1000, description="Max sample failures in report")
    max_sample_warnings: int = Field(50, ge=1, le=1000, description="Max sample warnings in report")
    parent_text_short_chars: int = Field(
        4000, ge=0, description="Upper bound for short parent_text"
    )
    parent_text_medium_chars: int = Field(
        10000, ge=0, description="Upper bound for medium parent_text"
    )
    parent_text_long_chars: int = Field(15000, ge=0, description="Upper bound for long parent_text")
    parent_text_very_long_chars: int = Field(
        20000, ge=0, description="Upper bound for very_long parent_text"
    )
    hard_contamination_markers: list[str] = Field(
        default_factory=lambda: [
            "XÁC THỰC VĂN BẢN HỢP NHẤT",
            "Nơi nhận:",
            "Lưu:",
            "Văn bản này được hợp nhất",
        ],
        description="Markers that cause validation failure",
    )
    warning_contamination_markers: list[str] = Field(
        default_factory=lambda: [
            "BỘ TRƯỞNG",
            "CHỦ NHIỆM",
            "CHỦ TỊCH QUỐC HỘI",
            "TM. QUỐC HỘI",
            "KT. BỘ TRƯỞNG",
        ],
        description="Markers that produce warnings only",
    )
    repealed_placeholder_patterns: list[str] = Field(
        default_factory=lambda: [
            "(được bãi bỏ)",
            "Điều này được bãi bỏ",
            "Khoản này được bãi bỏ",
            "Điểm này được bãi bỏ",
        ],
        description="Regex patterns for repealed placeholder text",
    )
