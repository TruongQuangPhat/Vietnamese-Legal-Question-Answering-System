"""Phase 7 processed JSONL validator.

This module implements the core JSONL validation pipeline for Phase 7.
It streams ``data/processed/legal_chunks.jsonl`` line-by-line, validates
each row as a ``LegalChunk``, checks required field completeness by
``chunk_kind``, enforces global ``chunk_id`` uniqueness, and accumulates
counters for the validation report. It also reconciles corpus-level counts
against the Phase 6 chunking report.

This validator is independent from Phase 6's ``LegalChunkValidator``.
It reuses ``LegalChunk`` for schema validation but has its own issue codes
and report model. Hash integrity, count reconciliation, citation structure,
hierarchy traceability, contamination checks, repealed metadata auditing, and
text-length readiness summaries are implemented; embedding-readiness checks
are added in later slices.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from src.processing.legal_chunk_models import (
    ChunkingLevel,
    LegalChunk,
    _compute_text_hash,
)
from src.processing.processed_jsonl_validation_models import (
    ProcessedJsonlIssue,
    ProcessedJsonlValidationConfig,
    ProcessedJsonlValidationIssueCode,
    ProcessedJsonlValidationReport,
)

# Required field rules by chunk_kind (used by _check_required_field_values)
_REQUIRED_BY_KIND: dict[str, dict[str, int | None]] = {
    "article_level": {"article_number": 1},
    "clause_level": {"article_number": 1, "clause_number": 1},
    "point_level": {"article_number": 1, "clause_number": 1, "point_label": 1},
}

_MIN_TEXT_CHARS = 20
_SHORT_TEXT_WARNING_CHARS = 50
_LONG_TEXT_WARNING_CHARS = 4000
_LONG_PARENT_TEXT_EXAMPLE_LIMIT = 5

_PAYLOAD_REQUIRED_FIELDS = (
    "law_id",
    "chunk_id",
    "chunk_kind",
    "level",
    "citation",
    "hierarchy_path",
    "source_node_id",
    "parent_article_node_id",
    "text_hash",
    "parent_text_hash",
    "metadata",
)
_PAYLOAD_CONDITIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "article_level": ("article_number",),
    "article_level_empty": ("article_number",),
    "clause_level": ("article_number", "clause_number"),
    "point_level": ("article_number", "clause_number", "point_label"),
}
_PAYLOAD_RECOMMENDED_METADATA_FIELDS = (
    "is_empty_or_repealed",
    "is_source_unit_repealed",
)
_PAYLOAD_RECOMMENDED_SOURCE_FIELDS = (
    "law_name",
    "source_url",
    "source_domain",
    "source_type",
    "source_file",
)


class ProcessedJsonlValidator:
    """Phase 7 core validator for the processed chunk JSONL file.

    Streams the JSONL file, validates each chunk, and produces a
    ``ProcessedJsonlValidationReport``. Checks implemented in Slice 2:

    1. JSONL parseability — every line parses as valid JSON.
    2. ``LegalChunk`` schema validation — every row validates.
    3. Required field presence — on raw dict before schema validation.
    4. Required field value validity — by ``chunk_kind`` after validation.
    5. Global ``chunk_id`` uniqueness.
    6. Basic counters and distribution summaries.

    Slice 3A adds hash integrity, Slice 3B adds count reconciliation, Slice 3C
    adds citation structure, Slice 3D adds hierarchy traceability, Slice 3E
    adds contamination auditing, Slice 3F audits repealed/empty metadata, and
    Slice 3G adds text-length readiness summaries, and Slice 3H audits payload
    readiness. Later slices add embedding-readiness.
    """

    def __init__(self, config: ProcessedJsonlValidationConfig) -> None:
        """Initialize the validator with a config.

        Args:
            config: Phase 7 validation configuration including thresholds,
            marker lists, and file paths.
        """
        self.config = config

    def validate(
        self,
        input_path: Path,
    ) -> ProcessedJsonlValidationReport:
        """Run validation checks through Slice 3H on the processed JSONL.

        Streams the file line-by-line, validates each row, and builds
        a ``ProcessedJsonlValidationReport`` with counters and capped
        sample issues.

        Args:
            input_path: Path to ``data/processed/legal_chunks.jsonl``.

        Returns:
            A ``ProcessedJsonlValidationReport`` with validation results.
            Status is ``pass`` when no errors or warnings are found,
            ``pass_with_warnings`` when only warnings exist, and ``fail``
            when any hard errors are found.
        """
        started_at = datetime.now(UTC).isoformat()
        start_time = time.perf_counter()

        # Accumulators
        total_lines: int = 0
        valid_chunks: int = 0
        invalid_chunks: int = 0
        jsonl_parse_failures: int = 0
        schema_failures: int = 0
        required_field_failures: int = 0
        duplicate_chunk_ids: int = 0
        hash_mismatches: int = 0
        citation_failures: int = 0
        traceability_failures: int = 0
        contamination_failures: int = 0
        contamination_warnings: int = 0
        repealed_metadata_mismatches: int = 0
        repealed_metadata_warnings: int = 0
        count_reconciliation_failures: int = 0
        errors_total: int = 0
        warnings_total: int = 0
        text_lengths: list[int] = []
        parent_text_lengths: list[int] = []
        empty_text_count: int = 0
        very_short_text_count: int = 0
        short_text_warning_count: int = 0
        long_text_warning_count: int = 0
        empty_parent_text_count: int = 0
        long_parent_text_warning_count: int = 0
        extreme_parent_text_warning_count: int = 0
        long_parent_text_examples: list[dict[str, Any]] = []
        payload_checked_chunks: int = 0
        payload_ready_chunks: int = 0
        payload_not_ready_chunks: int = 0
        payload_failure_chunks: int = 0
        payload_warning_chunks: int = 0
        payload_schema_unavailable_chunks: int = 0
        payload_missing_required_counts: dict[str, int] = dict.fromkeys(_PAYLOAD_REQUIRED_FIELDS, 0)
        payload_empty_required_counts: dict[str, int] = dict.fromkeys(_PAYLOAD_REQUIRED_FIELDS, 0)
        payload_missing_conditional_counts: dict[str, int] = dict.fromkeys(
            ("article_number", "clause_number", "point_label"), 0
        )
        payload_missing_recommended_metadata_counts: dict[str, int] = dict.fromkeys(
            _PAYLOAD_RECOMMENDED_METADATA_FIELDS, 0
        )
        payload_missing_recommended_source_counts: dict[str, int] = dict.fromkeys(
            _PAYLOAD_RECOMMENDED_SOURCE_FIELDS, 0
        )

        chunks_by_level: dict[str, int] = {}
        chunks_by_law: dict[str, int] = {}
        repealed_metadata_summary: dict[str, int] = {
            "metadata_empty_or_repealed_count": 0,
            "metadata_source_unit_repealed_count": 0,
            "text_repealed_pattern_count": 0,
            "parent_text_repealed_pattern_count": 0,
            "text_or_parent_repealed_pattern_count": 0,
            "text_repealed_but_metadata_not_marked_count": 0,
            "article_parent_repealed_but_metadata_not_marked_count": 0,
            "metadata_marked_but_no_text_pattern_count": 0,
        }

        sample_failures: list[ProcessedJsonlIssue] = []
        sample_warnings: list[ProcessedJsonlIssue] = []

        seen_chunk_ids: set[str] = set()
        hierarchy_index_cache: dict[str, dict[str, dict[str, Any]] | None] = {}
        hierarchy_load_failures: dict[str, str] = {}
        sampled_hierarchy_load_failures: set[str] = set()
        traceability_checks_skipped = self.config.hierarchy_dir is None

        def _add_sample_failure(issue: ProcessedJsonlIssue) -> None:
            if len(sample_failures) < self.config.max_sample_failures:
                sample_failures.append(issue)

        def _add_sample_warning(issue: ProcessedJsonlIssue) -> None:
            if len(sample_warnings) < self.config.max_sample_warnings:
                sample_warnings.append(issue)

        def _bump_level(level: ChunkingLevel) -> None:
            key = level.value
            chunks_by_level[key] = chunks_by_level.get(key, 0) + 1

        def _bump_law(law_id: str) -> None:
            chunks_by_law[law_id] = chunks_by_law.get(law_id, 0) + 1

        def _make_issue(
            code: ProcessedJsonlValidationIssueCode,
            message: str,
            law_id: str,
            chunk_id: str | None,
            line_number: int | None,
            context: dict[str, Any] | None = None,
        ) -> ProcessedJsonlIssue:
            # Sanitize: ProcessedJsonlIssue requires non-empty law_id
            safe_law_id = law_id if law_id else "unknown"
            return ProcessedJsonlIssue(
                code=code,
                message=message,
                law_id=safe_law_id,
                chunk_id=chunk_id,
                line_number=line_number,
                context=context or {},
            )

        def _get_hierarchy_index(
            law_id: str,
        ) -> dict[str, dict[str, Any]] | None:
            if law_id in hierarchy_index_cache:
                return hierarchy_index_cache[law_id]

            if self.config.hierarchy_dir is None:
                hierarchy_index_cache[law_id] = None
                return None

            hierarchy_path = Path(self.config.hierarchy_dir) / law_id / "hierarchy.json"
            try:
                hierarchy_data = json.loads(hierarchy_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                hierarchy_load_failures[law_id] = f"Hierarchy file is missing: {hierarchy_path}"
                hierarchy_index_cache[law_id] = None
                return None
            except json.JSONDecodeError as exc:
                hierarchy_load_failures[law_id] = f"Hierarchy file contains invalid JSON: {exc}"
                hierarchy_index_cache[law_id] = None
                return None
            except (OSError, UnicodeError) as exc:
                hierarchy_load_failures[law_id] = f"Hierarchy file could not be read: {exc}"
                hierarchy_index_cache[law_id] = None
                return None

            hierarchy_index = _index_hierarchy_nodes(hierarchy_data)
            if not hierarchy_index:
                hierarchy_load_failures[law_id] = (
                    f"Hierarchy file contains no indexable nodes: {hierarchy_path}"
                )
                hierarchy_index_cache[law_id] = None
                return None

            hierarchy_index_cache[law_id] = hierarchy_index
            return hierarchy_index

        def _reconcile_counts_with_chunking_report() -> tuple[int, int]:
            report_path = Path(self.config.chunking_report_path)
            issue_code = ProcessedJsonlValidationIssueCode.COUNT_RECONCILIATION_FAILED

            def _warning(message: str, context: dict[str, Any]) -> None:
                _add_sample_warning(
                    _make_issue(
                        code=issue_code,
                        message=message,
                        law_id="unknown",
                        chunk_id=None,
                        line_number=None,
                        context={"report_path": str(report_path), **context},
                    )
                )

            def _failure(message: str, context: dict[str, Any]) -> None:
                _add_sample_failure(
                    _make_issue(
                        code=issue_code,
                        message=message,
                        law_id="unknown",
                        chunk_id=None,
                        line_number=None,
                        context={"report_path": str(report_path), **context},
                    )
                )

            if not report_path.exists():
                _warning(
                    "Phase 6 chunking report is missing",
                    {"reason": "report_missing"},
                )
                return 0, 1

            try:
                chunking_report = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                _warning(
                    "Phase 6 chunking report contains invalid JSON",
                    {"reason": "invalid_json", "error": str(exc)},
                )
                return 0, 1
            except (OSError, UnicodeError) as exc:
                _warning(
                    "Phase 6 chunking report could not be read",
                    {"reason": "report_unreadable", "error": str(exc)},
                )
                return 0, 1

            if not isinstance(chunking_report, dict):
                _warning(
                    "Phase 6 chunking report root is not a JSON object",
                    {"reason": "report_root_not_object"},
                )
                return 0, 1

            if "total_chunks" not in chunking_report:
                _warning(
                    "Phase 6 chunking report is missing total_chunks",
                    {"reason": "total_chunks_missing"},
                )
                return 0, 1

            expected_total = chunking_report["total_chunks"]
            if (
                not isinstance(expected_total, int)
                or isinstance(expected_total, bool)
                or expected_total < 0
            ):
                _warning(
                    "Phase 6 chunking report has invalid total_chunks",
                    {
                        "reason": "total_chunks_invalid",
                        "raw_total_chunks": expected_total,
                    },
                )
                return 0, 1

            failure_count = 0
            warning_count = 0

            if expected_total != total_lines:
                _failure(
                    "JSONL line count does not match Phase 6 total_chunks",
                    {
                        "expected_total": expected_total,
                        "observed_total": total_lines,
                        "delta": total_lines - expected_total,
                    },
                )
                failure_count += 1

            if "chunks_by_level" in chunking_report:
                expected_by_level = chunking_report["chunks_by_level"]
                if not isinstance(expected_by_level, dict):
                    _warning(
                        "Phase 6 chunks_by_level is malformed",
                        {"reason": "chunks_by_level_malformed"},
                    )
                    warning_count += 1
                else:
                    for level, expected in expected_by_level.items():
                        observed = chunks_by_level.get(str(level), 0)
                        if expected != observed:
                            _failure(
                                "JSONL level count does not match Phase 6 report",
                                {
                                    "level": str(level),
                                    "expected": expected,
                                    "observed": observed,
                                },
                            )
                            failure_count += 1

            if "chunks_by_law" in chunking_report:
                expected_by_law = chunking_report["chunks_by_law"]
                if not isinstance(expected_by_law, dict):
                    _warning(
                        "Phase 6 chunks_by_law is malformed",
                        {"reason": "chunks_by_law_malformed"},
                    )
                    warning_count += 1
                elif len(expected_by_law) != len(chunks_by_law):
                    _warning(
                        "JSONL law count does not match Phase 6 report",
                        {
                            "expected_law_count": len(expected_by_law),
                            "observed_law_count": len(chunks_by_law),
                        },
                    )
                    warning_count += 1

            return failure_count, warning_count

        # --- Stream and validate ---
        with input_path.open("r", encoding="utf-8") as fh:
            for line_number, raw_line in enumerate(fh, start=1):
                total_lines += 1
                stripped = raw_line.strip()
                line_has_error = False

                # Blank lines are validation errors in processed JSONL
                if not stripped:
                    jsonl_parse_failures += 1
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR,
                            message="Blank line in JSONL",
                            law_id="unknown",
                            chunk_id=None,
                            line_number=line_number,
                        )
                    )
                    invalid_chunks += 1
                    continue

                # Check 1: JSONL parseability
                try:
                    parsed: dict[str, Any] = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    jsonl_parse_failures += 1
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR,
                            message=f"JSON parse error: {exc}",
                            law_id="unknown",
                            chunk_id=None,
                            line_number=line_number,
                            context={"error": str(exc)},
                        )
                    )
                    invalid_chunks += 1
                    continue

                if not isinstance(parsed, dict):
                    schema_failures += 1
                    errors_total += 1
                    line_has_error = True
                    invalid_chunks += 1
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.SCHEMA_VALIDATION_FAILED,
                            message="JSONL row is not a JSON object",
                            law_id="unknown",
                            chunk_id=None,
                            line_number=line_number,
                        )
                    )
                    continue

                payload_checked_chunks += 1
                (
                    payload_failures,
                    payload_warnings,
                    payload_details,
                ) = _check_payload_readiness(parsed)
                for field in payload_details["missing_required"]:
                    payload_missing_required_counts[field] += 1
                for field in payload_details["empty_required"]:
                    payload_empty_required_counts[field] += 1
                for field in payload_details["missing_conditional"]:
                    payload_missing_conditional_counts[field] += 1
                for field in payload_details["missing_recommended_metadata"]:
                    payload_missing_recommended_metadata_counts[field] += 1
                for field in payload_details["missing_recommended_source"]:
                    payload_missing_recommended_source_counts[field] += 1

                if payload_failures:
                    payload_failure_chunks += 1
                    payload_not_ready_chunks += 1
                else:
                    payload_ready_chunks += 1

                # Check 2a: Required field presence on raw dict
                # Catches missing fields before Pydantic defaults hide them
                presence_errors = _check_required_field_presence(parsed)
                if presence_errors:
                    required_field_failures += 1
                    errors_total += 1
                    line_has_error = True
                    for field_name, reason in presence_errors:
                        _add_sample_failure(
                            _make_issue(
                                code=ProcessedJsonlValidationIssueCode.REQUIRED_FIELD_MISSING,
                                message=reason,
                                law_id=parsed.get("law_id", "unknown") or "unknown",
                                chunk_id=parsed.get("chunk_id"),
                                line_number=line_number,
                                context={"field": field_name},
                            )
                        )
                    invalid_chunks += 1
                    continue

                # Check 2b: LegalChunk schema validation
                try:
                    chunk = LegalChunk.model_validate(parsed)
                except Exception as exc:
                    if not payload_failures:
                        payload_schema_unavailable_chunks += 1
                    schema_failures += 1
                    errors_total += 1
                    line_has_error = True
                    invalid_chunks += 1
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.SCHEMA_VALIDATION_FAILED,
                            message=f"Schema validation failed: {exc}",
                            law_id=parsed.get("law_id", "unknown") or "unknown",
                            chunk_id=parsed.get("chunk_id"),
                            line_number=line_number,
                            context={"error": str(exc)},
                        )
                    )
                    continue

                # Track distribution for valid schema rows
                _bump_level(chunk.level)
                _bump_law(chunk.law_id)

                # Check 3: Required field value validity by chunk_kind
                field_errors = _check_required_field_values(chunk, chunk.chunk_kind)
                if field_errors:
                    required_field_failures += 1
                    errors_total += 1
                    line_has_error = True
                    for field_name, reason in field_errors:
                        _add_sample_failure(
                            _make_issue(
                                code=ProcessedJsonlValidationIssueCode.REQUIRED_FIELD_MISSING,
                                message=reason,
                                law_id=chunk.law_id,
                                chunk_id=chunk.chunk_id,
                                line_number=line_number,
                                context={"field": field_name},
                            )
                        )
                    invalid_chunks += 1
                    continue

                # Check 4: Global chunk_id uniqueness
                if chunk.chunk_id in seen_chunk_ids:
                    duplicate_chunk_ids += 1
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.DUPLICATE_CHUNK_ID,
                            message=f"Duplicate chunk_id: {chunk.chunk_id}",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={"chunk_id": chunk.chunk_id},
                        )
                    )
                else:
                    seen_chunk_ids.add(chunk.chunk_id)

                # Check 5: Hash integrity
                expected_text_hash = _compute_text_hash(chunk.text)
                expected_parent_text_hash = _compute_text_hash(chunk.parent_text)
                text_hash_matches = chunk.text_hash == expected_text_hash
                parent_text_hash_matches = chunk.parent_text_hash == expected_parent_text_hash
                if not text_hash_matches or not parent_text_hash_matches:
                    hash_mismatches += 1
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.HASH_MISMATCH,
                            message="text_hash or parent_text_hash mismatch",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "text_hash_match": text_hash_matches,
                                "parent_text_hash_match": parent_text_hash_matches,
                            },
                        )
                    )

                # Check 6: Citation structural validation
                citation_errors = _check_citation_structure(chunk)
                if citation_errors:
                    citation_failures += 1
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.CITATION_STRUCTURE_MISMATCH,
                            message="Citation structure does not match chunk hierarchy metadata",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "citation": chunk.citation,
                                "chunk_kind": chunk.chunk_kind,
                                "article_number": chunk.article_number,
                                "clause_number": chunk.clause_number,
                                "point_label": chunk.point_label,
                                "missing_components": [
                                    {"label": label, "value": value}
                                    for label, value in citation_errors
                                ],
                            },
                        )
                    )

                # Check 7: Hierarchy traceability
                traceability_errors: list[tuple[str, str]] = []
                hierarchy_load_failed = False
                if not traceability_checks_skipped:
                    hierarchy_index = _get_hierarchy_index(chunk.law_id)
                    if hierarchy_index is None:
                        hierarchy_load_failed = True
                        traceability_errors.append(
                            (
                                "hierarchy_file",
                                hierarchy_load_failures.get(
                                    chunk.law_id,
                                    "Hierarchy index is unavailable",
                                ),
                            )
                        )
                    else:
                        traceability_errors = _check_hierarchy_traceability(
                            chunk,
                            hierarchy_index,
                        )

                if traceability_errors:
                    traceability_failures += 1
                    errors_total += 1
                    line_has_error = True
                    should_sample = (
                        not hierarchy_load_failed
                        or chunk.law_id not in sampled_hierarchy_load_failures
                    )
                    if should_sample:
                        _add_sample_failure(
                            _make_issue(
                                code=(
                                    ProcessedJsonlValidationIssueCode.HIERARCHY_TRACEABILITY_FAILED
                                ),
                                message="Chunk cannot be traced to its legal hierarchy",
                                law_id=chunk.law_id,
                                chunk_id=chunk.chunk_id,
                                line_number=line_number,
                                context={
                                    "chunk_kind": chunk.chunk_kind,
                                    "source_node_id": chunk.source_node_id,
                                    "parent_article_node_id": (chunk.parent_article_node_id),
                                    "article_number": chunk.article_number,
                                    "clause_number": chunk.clause_number,
                                    "point_label": chunk.point_label,
                                    "failures": [
                                        {"field": field, "reason": reason}
                                        for field, reason in traceability_errors
                                    ],
                                },
                            )
                        )
                    if hierarchy_load_failed:
                        sampled_hierarchy_load_failures.add(chunk.law_id)

                # Check 8: Processed text contamination
                hard_matches, warning_matches = _scan_contamination(
                    chunk.text,
                    chunk.parent_text,
                    self.config.hard_contamination_markers,
                    self.config.warning_contamination_markers,
                )
                if hard_matches:
                    contamination_failures += 1
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.HARD_CONTAMINATION_FOUND,
                            message="Processed chunk contains hard contamination markers",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "matches": [
                                    {"field": field, "marker": marker}
                                    for field, marker in hard_matches
                                ],
                            },
                        )
                    )

                if warning_matches:
                    contamination_warnings += 1
                    warnings_total += 1
                    _add_sample_warning(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.WARNING_CONTAMINATION_FOUND,
                            message="Processed chunk contains warning contamination markers",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "matches": [
                                    {"field": field, "marker": marker}
                                    for field, marker in warning_matches
                                ],
                            },
                        )
                    )

                # Check 9: Repealed/empty metadata consistency
                text_repealed_matches, parent_repealed_matches = _scan_repealed_patterns(
                    chunk.text,
                    chunk.parent_text,
                    self.config.repealed_placeholder_patterns,
                )
                metadata_empty_or_repealed = chunk.metadata.is_empty_or_repealed
                metadata_source_unit_repealed = chunk.metadata.is_source_unit_repealed
                metadata_marked = metadata_empty_or_repealed or metadata_source_unit_repealed
                text_has_repealed_pattern = bool(text_repealed_matches)
                parent_text_has_repealed_pattern = bool(parent_repealed_matches)
                any_text_pattern = text_has_repealed_pattern or parent_text_has_repealed_pattern

                if metadata_empty_or_repealed:
                    repealed_metadata_summary["metadata_empty_or_repealed_count"] += 1
                if metadata_source_unit_repealed:
                    repealed_metadata_summary["metadata_source_unit_repealed_count"] += 1
                if text_has_repealed_pattern:
                    repealed_metadata_summary["text_repealed_pattern_count"] += 1
                if parent_text_has_repealed_pattern:
                    repealed_metadata_summary["parent_text_repealed_pattern_count"] += 1
                if any_text_pattern:
                    repealed_metadata_summary["text_or_parent_repealed_pattern_count"] += 1

                text_metadata_mismatch = text_has_repealed_pattern and not metadata_marked
                article_parent_metadata_mismatch = (
                    chunk.chunk_kind in {"article_level", "article_level_empty"}
                    and parent_text_has_repealed_pattern
                    and not metadata_marked
                )
                if text_metadata_mismatch:
                    repealed_metadata_summary["text_repealed_but_metadata_not_marked_count"] += 1
                if article_parent_metadata_mismatch:
                    repealed_metadata_summary[
                        "article_parent_repealed_but_metadata_not_marked_count"
                    ] += 1

                if text_metadata_mismatch or article_parent_metadata_mismatch:
                    repealed_metadata_mismatches += 1
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.REPEALED_METADATA_MISMATCH,
                            message="Repealed text is not reflected in chunk metadata",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "citation": chunk.citation,
                                "metadata": {
                                    "is_empty_or_repealed": metadata_empty_or_repealed,
                                    "is_source_unit_repealed": (metadata_source_unit_repealed),
                                },
                                "matched_patterns": [
                                    {"field": field, "pattern": pattern}
                                    for field, pattern in (
                                        text_repealed_matches + parent_repealed_matches
                                    )
                                ],
                                "text_has_repealed_pattern": (text_has_repealed_pattern),
                                "parent_text_has_repealed_pattern": (
                                    parent_text_has_repealed_pattern
                                ),
                            },
                        )
                    )

                if metadata_marked and not any_text_pattern:
                    repealed_metadata_warnings += 1
                    repealed_metadata_summary["metadata_marked_but_no_text_pattern_count"] += 1
                    warnings_total += 1
                    _add_sample_warning(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.REPEALED_METADATA_MISMATCH,
                            message="Repealed metadata has no configured text pattern",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "citation": chunk.citation,
                                "metadata": {
                                    "is_empty_or_repealed": metadata_empty_or_repealed,
                                    "is_source_unit_repealed": (metadata_source_unit_repealed),
                                },
                                "text_has_repealed_pattern": False,
                                "parent_text_has_repealed_pattern": False,
                            },
                        )
                    )

                # Check 10: Text length and parent context readiness
                text_chars = len(chunk.text)
                parent_text_chars = len(chunk.parent_text)
                text_lengths.append(text_chars)
                parent_text_lengths.append(parent_text_chars)

                text_is_empty = not chunk.text.strip()
                parent_text_is_empty = not chunk.parent_text.strip()
                text_is_very_short = text_chars < _MIN_TEXT_CHARS
                text_is_short = text_chars < _SHORT_TEXT_WARNING_CHARS
                text_is_long = text_chars > _LONG_TEXT_WARNING_CHARS
                parent_text_is_long = parent_text_chars > self.config.parent_text_long_chars
                parent_text_is_extreme = parent_text_chars > self.config.parent_text_very_long_chars

                if text_is_empty:
                    empty_text_count += 1
                if text_is_very_short:
                    very_short_text_count += 1
                if text_is_short and not text_is_empty and not metadata_marked:
                    short_text_warning_count += 1
                if text_is_long:
                    long_text_warning_count += 1
                if parent_text_is_empty:
                    empty_parent_text_count += 1
                if parent_text_is_long:
                    long_parent_text_warning_count += 1
                    long_parent_text_examples.append(
                        {
                            "law_id": chunk.law_id,
                            "chunk_id": chunk.chunk_id,
                            "chunk_kind": chunk.chunk_kind,
                            "parent_text_chars": parent_text_chars,
                            "text_chars": text_chars,
                            "citation": chunk.citation,
                        }
                    )
                if parent_text_is_extreme:
                    extreme_parent_text_warning_count += 1

                if text_is_empty and not metadata_marked:
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.EMPTY_TEXT_FOUND,
                            message="Embedding text is empty or whitespace-only",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "citation": chunk.citation,
                                "text_chars": text_chars,
                                "parent_text_chars": parent_text_chars,
                            },
                        )
                    )

                length_warning_reasons: list[str] = []
                if text_is_short and not text_is_empty and not metadata_marked:
                    length_warning_reasons.append("short_text")
                if text_is_long:
                    length_warning_reasons.append("long_text")
                if parent_text_is_empty:
                    length_warning_reasons.append("empty_parent_text")
                if parent_text_is_long:
                    length_warning_reasons.append("long_parent_text")
                if parent_text_is_extreme:
                    length_warning_reasons.append("extreme_parent_text")

                if length_warning_reasons:
                    warnings_total += 1
                    issue_code = (
                        ProcessedJsonlValidationIssueCode.VERY_LONG_PARENT_TEXT
                        if parent_text_is_long
                        else ProcessedJsonlValidationIssueCode.TEXT_LENGTH_WARNING
                    )
                    _add_sample_warning(
                        _make_issue(
                            code=issue_code,
                            message="Chunk text length may reduce retrieval readiness",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "citation": chunk.citation,
                                "text_chars": text_chars,
                                "parent_text_chars": parent_text_chars,
                                "reasons": length_warning_reasons,
                                "thresholds": {
                                    "short_text_chars": _SHORT_TEXT_WARNING_CHARS,
                                    "long_text_chars": _LONG_TEXT_WARNING_CHARS,
                                    "long_parent_text_chars": (self.config.parent_text_long_chars),
                                    "extreme_parent_text_chars": (
                                        self.config.parent_text_very_long_chars
                                    ),
                                },
                            },
                        )
                    )

                # Check 11: Vector payload readiness
                if payload_failures:
                    errors_total += 1
                    line_has_error = True
                    _add_sample_failure(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.PAYLOAD_FIELD_MISSING,
                            message="Chunk payload is not ready for indexing",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "citation": chunk.citation,
                                "failures": payload_failures,
                            },
                        )
                    )

                if payload_warnings:
                    payload_warning_chunks += 1
                    warnings_total += 1
                    _add_sample_warning(
                        _make_issue(
                            code=ProcessedJsonlValidationIssueCode.PAYLOAD_FIELD_MISSING,
                            message="Chunk payload has recommended metadata warnings",
                            law_id=chunk.law_id,
                            chunk_id=chunk.chunk_id,
                            line_number=line_number,
                            context={
                                "chunk_kind": chunk.chunk_kind,
                                "citation": chunk.citation,
                                "warnings": payload_warnings,
                            },
                        )
                    )

                # Count valid/invalid per line
                if line_has_error:
                    invalid_chunks += 1
                else:
                    valid_chunks += 1

        recon_failures, recon_warnings = _reconcile_counts_with_chunking_report()
        count_reconciliation_failures += recon_failures
        errors_total += recon_failures
        warnings_total += recon_warnings
        repealed_metadata_summary["metadata_mismatch_failure_count"] = repealed_metadata_mismatches
        repealed_metadata_summary["metadata_mismatch_warning_count"] = repealed_metadata_warnings
        text_length_summary = {
            **_summarize_lengths(text_lengths),
            "empty_text_count": empty_text_count,
            "very_short_text_count": very_short_text_count,
            "short_text_warning_count": short_text_warning_count,
            "long_text_warning_count": long_text_warning_count,
            "very_short_threshold_chars": _MIN_TEXT_CHARS,
            "short_warning_threshold_chars": _SHORT_TEXT_WARNING_CHARS,
            "long_warning_threshold_chars": _LONG_TEXT_WARNING_CHARS,
        }
        parent_text_length_summary = {
            **_summarize_lengths(parent_text_lengths),
            "empty_parent_text_count": empty_parent_text_count,
            "long_parent_text_warning_count": long_parent_text_warning_count,
            "extreme_parent_text_warning_count": (extreme_parent_text_warning_count),
            "long_warning_threshold_chars": self.config.parent_text_long_chars,
            "extreme_warning_threshold_chars": (self.config.parent_text_very_long_chars),
        }
        top_parent_examples = sorted(
            long_parent_text_examples,
            key=lambda item: int(item["parent_text_chars"]),
            reverse=True,
        )[:_LONG_PARENT_TEXT_EXAMPLE_LIMIT]
        long_parent_text_summary: dict[str, Any] = {
            "threshold_chars": self.config.parent_text_long_chars,
            "extreme_threshold_chars": self.config.parent_text_very_long_chars,
            "long_count": long_parent_text_warning_count,
            "extreme_count": extreme_parent_text_warning_count,
            "max_chars": max(parent_text_lengths, default=0),
            "short_bucket_count": sum(
                length <= self.config.parent_text_short_chars for length in parent_text_lengths
            ),
            "medium_bucket_count": sum(
                self.config.parent_text_short_chars < length <= self.config.parent_text_medium_chars
                for length in parent_text_lengths
            ),
            "long_bucket_count": sum(
                self.config.parent_text_medium_chars < length <= self.config.parent_text_long_chars
                for length in parent_text_lengths
            ),
            "very_long_bucket_count": sum(
                self.config.parent_text_long_chars
                < length
                <= self.config.parent_text_very_long_chars
                for length in parent_text_lengths
            ),
            "extreme_bucket_count": sum(
                length > self.config.parent_text_very_long_chars for length in parent_text_lengths
            ),
            "top_examples": top_parent_examples,
        }
        payload_readiness_summary: dict[str, Any] = {
            "checked_chunks": payload_checked_chunks,
            "ready_chunks": payload_ready_chunks,
            "not_ready_chunks": payload_not_ready_chunks,
            "payload_failure_chunks": payload_failure_chunks,
            "payload_warning_chunks": payload_warning_chunks,
            "schema_unavailable_chunks": payload_schema_unavailable_chunks,
            "missing_required_field_counts": payload_missing_required_counts,
            "empty_required_field_counts": payload_empty_required_counts,
            "missing_conditional_field_counts": (payload_missing_conditional_counts),
            "missing_recommended_metadata_counts": (payload_missing_recommended_metadata_counts),
            "missing_recommended_source_counts": (payload_missing_recommended_source_counts),
            "ready_rate": round(
                payload_ready_chunks / payload_checked_chunks,
                4,
            )
            if payload_checked_chunks
            else 0.0,
        }
        embedding_readiness = _build_embedding_readiness_summary(
            errors_total=errors_total,
            warnings_total=warnings_total,
            valid_chunks=valid_chunks,
            invalid_chunks=invalid_chunks,
            jsonl_parse_failures=jsonl_parse_failures,
            schema_failures=schema_failures,
            required_field_failures=required_field_failures,
            duplicate_chunk_ids=duplicate_chunk_ids,
            hash_mismatches=hash_mismatches,
            count_reconciliation_failures=count_reconciliation_failures,
            citation_failures=citation_failures,
            traceability_failures=traceability_failures,
            contamination_failures=contamination_failures,
            contamination_warnings=contamination_warnings,
            text_length_summary=text_length_summary,
            payload_readiness_summary=payload_readiness_summary,
        )

        # --- Build report ---
        finished_at = datetime.now(UTC).isoformat()
        duration_seconds = round(time.perf_counter() - start_time, 3)

        report = ProcessedJsonlValidationReport(
            schema_version=self.config.schema_version,
            validator_version=self.config.validator_version,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            input_path=str(input_path),
            chunking_report_path=self.config.chunking_report_path,
            hierarchy_dir=self.config.hierarchy_dir,
            traceability_checks_skipped=traceability_checks_skipped,
            total_lines=total_lines,
            valid_chunks=valid_chunks,
            invalid_chunks=invalid_chunks,
            jsonl_parse_failures=jsonl_parse_failures,
            schema_failures=schema_failures,
            required_field_failures=required_field_failures,
            duplicate_chunk_ids=duplicate_chunk_ids,
            count_reconciliation_failures=count_reconciliation_failures,
            hash_mismatches=hash_mismatches,
            citation_failures=citation_failures,
            traceability_failures=traceability_failures,
            contamination_failures=contamination_failures,
            contamination_warnings=contamination_warnings,
            errors_total=errors_total,
            warnings_total=warnings_total,
            chunks_by_level=chunks_by_level,
            chunks_by_law=chunks_by_law,
            text_length_summary=text_length_summary,
            parent_text_length_summary=parent_text_length_summary,
            long_parent_text_summary=long_parent_text_summary,
            repealed_metadata_summary=repealed_metadata_summary,
            payload_readiness_summary=payload_readiness_summary,
            embedding_readiness=embedding_readiness,
            sample_failures=sample_failures,
            sample_warnings=sample_warnings,
            status="pass",
        )

        return report


def _summarize_lengths(lengths: list[int]) -> dict[str, int | float]:
    """Summarize character lengths with deterministic nearest percentiles.

    Args:
        lengths: Character counts collected from schema-valid chunks.

    Returns:
        Stable count, range, central tendency, and percentile statistics.
    """
    if not lengths:
        return {
            "count": 0,
            "min_chars": 0,
            "max_chars": 0,
            "mean_chars": 0.0,
            "median_chars": 0.0,
            "p90_chars": 0,
            "p95_chars": 0,
            "p99_chars": 0,
        }

    ordered = sorted(lengths)

    def _percentile(quantile: float) -> int:
        index = int(round((len(ordered) - 1) * quantile))
        return ordered[index]

    return {
        "count": len(ordered),
        "min_chars": ordered[0],
        "max_chars": ordered[-1],
        "mean_chars": round(mean(ordered), 2),
        "median_chars": median(ordered),
        "p90_chars": _percentile(0.90),
        "p95_chars": _percentile(0.95),
        "p99_chars": _percentile(0.99),
    }


def _build_embedding_readiness_summary(
    *,
    errors_total: int,
    warnings_total: int,
    valid_chunks: int,
    invalid_chunks: int,
    jsonl_parse_failures: int,
    schema_failures: int,
    required_field_failures: int,
    duplicate_chunk_ids: int,
    hash_mismatches: int,
    count_reconciliation_failures: int,
    citation_failures: int,
    traceability_failures: int,
    contamination_failures: int,
    contamination_warnings: int,
    text_length_summary: dict[str, Any],
    payload_readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build the final Phase 7 decision for proceeding to embedding."""
    payload_ready_rate = float(payload_readiness_summary.get("ready_rate", 0.0))
    payload_ready_chunks = int(payload_readiness_summary.get("ready_chunks", 0))
    payload_not_ready_chunks = int(payload_readiness_summary.get("not_ready_chunks", 0))
    payload_failure_chunks = int(payload_readiness_summary.get("payload_failure_chunks", 0))
    payload_warning_chunks = int(payload_readiness_summary.get("payload_warning_chunks", 0))
    short_text_warnings = int(text_length_summary.get("short_text_warning_count", 0))
    blocking_categories = {
        "jsonl_parse_failures": jsonl_parse_failures,
        "schema_failures": schema_failures,
        "required_field_failures": required_field_failures,
        "duplicate_chunk_ids": duplicate_chunk_ids,
        "hash_mismatches": hash_mismatches,
        "count_reconciliation_failures": count_reconciliation_failures,
        "citation_failures": citation_failures,
        "traceability_failures": traceability_failures,
        "contamination_failures": contamination_failures,
        "payload_failure_chunks": payload_failure_chunks,
    }
    warning_categories = {
        "total_warnings": warnings_total,
        "contamination_warnings": contamination_warnings,
        "short_text_warnings": short_text_warnings,
        "payload_warning_chunks": payload_warning_chunks,
    }
    blocking_reasons = [category for category, count in blocking_categories.items() if count > 0]
    if errors_total > 0:
        blocking_reasons.append("errors_total")
    if invalid_chunks > 0:
        blocking_reasons.append("invalid_chunks")
    if payload_not_ready_chunks > 0:
        blocking_reasons.append("payload_not_ready_chunks")
    if payload_ready_rate < 1.0:
        blocking_reasons.append("payload_ready_rate")

    embedding_ready = not blocking_reasons
    if not embedding_ready:
        readiness_status = "blocked"
        recommended_next_actions = [
            "Resolve all blocking validation categories before Phase 8 embedding/indexing.",
            "Re-run Phase 7 validation after correcting source pipeline outputs.",
            "Do not mutate processed chunks inside the readiness summary.",
        ]
    elif warnings_total > 0:
        readiness_status = "ready_with_warnings"
        recommended_next_actions = [
            "Proceed to Phase 8 embedding/indexing only if ready_with_warnings is acceptable.",
            "Before production indexing, review deferred warning distribution.",
            "Do not mutate processed chunks during readiness summary.",
        ]
    else:
        readiness_status = "ready"
        recommended_next_actions = [
            "Proceed to Phase 8 embedding/indexing.",
            "Preserve the validated payload, text, and hash contracts.",
            "Do not mutate processed chunks during indexing preparation.",
        ]

    deferred_warning_followups: list[dict[str, Any]] = []
    if contamination_warnings > 0:
        deferred_warning_followups.append(
            {
                "category": "contamination_warnings",
                "count": contamination_warnings,
                "source_slice": "3E",
                "recommended_action": (
                    "Run warning distribution audit by law_id, chunk_kind, field, and marker."
                ),
            }
        )
    if short_text_warnings > 0:
        deferred_warning_followups.append(
            {
                "category": "short_text_warnings",
                "count": short_text_warnings,
                "source_slice": "3G",
                "recommended_action": (
                    "Audit short chunks by law_id, chunk_kind, citation, and "
                    "repealed metadata before deciding drop/merge policy."
                ),
            }
        )

    return {
        "embedding_ready": embedding_ready,
        "readiness_status": readiness_status,
        "blocking_error_count": errors_total,
        "warning_count": warnings_total,
        "valid_chunks": valid_chunks,
        "invalid_chunks": invalid_chunks,
        "payload_ready_rate": payload_ready_rate,
        "payload_ready_chunks": payload_ready_chunks,
        "payload_not_ready_chunks": payload_not_ready_chunks,
        "blocking_categories": blocking_categories,
        "blocking_reasons": blocking_reasons,
        "warning_categories": warning_categories,
        "deferred_warning_followups": deferred_warning_followups,
        "recommended_next_actions": recommended_next_actions,
    }


def _check_payload_readiness(
    parsed: dict[str, Any],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, list[str]],
]:
    """Inspect raw chunk fields for downstream payload completeness.

    Raw JSON is used so missing metadata keys remain visible before Pydantic
    defaults are applied. This helper classifies payload gaps but does not
    decide whether an earlier schema/required-field check already owns the
    line-level error count.

    Args:
        parsed: Parsed JSON object for one processed chunk line.

    Returns:
        Hard failures, warning-only gaps, and field names grouped by summary
        category.
    """

    def _is_empty(value: Any) -> bool:
        if value is None or value == [] or value == {}:
            return True
        return isinstance(value, str) and not value.strip()

    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    details: dict[str, list[str]] = {
        "missing_required": [],
        "empty_required": [],
        "missing_conditional": [],
        "missing_recommended_metadata": [],
        "missing_recommended_source": [],
    }

    for field in _PAYLOAD_REQUIRED_FIELDS:
        if field not in parsed:
            details["missing_required"].append(field)
            failures.append({"field": field, "reason": "missing_required"})
        elif _is_empty(parsed[field]):
            details["empty_required"].append(field)
            failures.append({"field": field, "reason": "empty_required"})

    chunk_kind = parsed.get("chunk_kind")
    if isinstance(chunk_kind, str):
        for field in _PAYLOAD_CONDITIONAL_FIELDS.get(chunk_kind, ()):
            if field not in parsed or _is_empty(parsed.get(field)):
                details["missing_conditional"].append(field)
                failures.append({"field": field, "reason": "missing_conditional"})

    metadata = parsed.get("metadata")
    if isinstance(metadata, dict):
        for field in _PAYLOAD_RECOMMENDED_METADATA_FIELDS:
            if field not in metadata:
                details["missing_recommended_metadata"].append(field)
                warnings.append(
                    {
                        "field": f"metadata.{field}",
                        "reason": "missing_recommended_metadata",
                    }
                )
    else:
        for field in _PAYLOAD_RECOMMENDED_METADATA_FIELDS:
            details["missing_recommended_metadata"].append(field)
            warnings.append(
                {
                    "field": f"metadata.{field}",
                    "reason": "missing_recommended_metadata",
                }
            )

    for field in _PAYLOAD_RECOMMENDED_SOURCE_FIELDS:
        if field not in parsed or _is_empty(parsed.get(field)):
            details["missing_recommended_source"].append(field)
            warnings.append({"field": field, "reason": "missing_recommended_source"})

    return failures, warnings, details


def _check_required_field_presence(
    parsed: dict[str, Any],
) -> list[tuple[str, str]]:
    """Check that all required fields are present in the raw parsed dict.

    Runs before ``LegalChunk.model_validate`` so missing fields are
    reported as ``REQUIRED_FIELD_MISSING`` rather than
    ``SCHEMA_VALIDATION_FAILED``.

    Args:
        parsed: Raw parsed JSON dict from the JSONL line.

    Returns:
        A list of ``(field_name, reason)`` tuples for each missing field.
    """
    errors: list[tuple[str, str]] = []
    required_fields = [
        "chunk_id",
        "law_id",
        "law_name",
        "level",
        "chunk_kind",
        "citation",
        "hierarchy_path",
        "source_node_id",
        "parent_article_node_id",
        "article_number",
        "clause_number",
        "point_label",
        "text",
        "parent_text",
        "text_hash",
        "parent_text_hash",
        "metadata",
    ]
    for field_name in required_fields:
        if field_name not in parsed:
            errors.append((field_name, f"{field_name} is missing from JSONL row"))
    return errors


def _check_required_field_values(
    chunk: LegalChunk,
    chunk_kind: str,
) -> list[tuple[str, str]]:
    """Check required field value validity by chunk_kind.

    Runs after ``LegalChunk.model_validate`` on the validated chunk
    object. Checks that fields with defaults are not empty/None when
    they should have real values.

    Args:
        chunk: The validated ``LegalChunk`` to check.
        chunk_kind: The chunk's kind string (e.g. ``"article_level"``).

    Returns:
        A list of ``(field_name, reason)`` tuples for each invalid field.
    """
    errors: list[tuple[str, str]] = []

    # Universal non-empty string fields
    if not chunk.chunk_id:
        errors.append(("chunk_id", "chunk_id is empty"))
    if not chunk.law_id:
        errors.append(("law_id", "law_id is empty"))
    if not chunk.law_name:
        errors.append(("law_name", "law_name is empty"))
    if not chunk.chunk_kind:
        errors.append(("chunk_kind", "chunk_kind is empty"))
    if not chunk.citation:
        errors.append(("citation", "citation is empty"))
    if not chunk.source_node_id:
        errors.append(("source_node_id", "source_node_id is empty"))
    if not chunk.parent_article_node_id:
        errors.append(("parent_article_node_id", "parent_article_node_id is empty"))
    if not chunk.text:
        errors.append(("text", "text is empty"))
    if not chunk.parent_text:
        errors.append(("parent_text", "parent_text is empty"))
    if not chunk.text_hash:
        errors.append(("text_hash", "text_hash is empty"))
    if not chunk.parent_text_hash:
        errors.append(("parent_text_hash", "parent_text_hash is empty"))

    # Metadata booleans must be present
    if not isinstance(chunk.metadata.is_empty_or_repealed, bool):
        errors.append(("metadata.is_empty_or_repealed", "must be a boolean"))
    if not isinstance(chunk.metadata.is_source_unit_repealed, bool):
        errors.append(("metadata.is_source_unit_repealed", "must be a boolean"))

    # Kind-specific required fields
    kind_rules = _REQUIRED_BY_KIND.get(chunk_kind, {})
    if "article_number" in kind_rules and not chunk.article_number:
        errors.append(("article_number", f"required for {chunk_kind}"))
    if "clause_number" in kind_rules and not chunk.clause_number:
        errors.append(("clause_number", f"required for {chunk_kind}"))
    if "point_label" in kind_rules and not chunk.point_label:
        errors.append(("point_label", f"required for {chunk_kind}"))

    return errors


def _index_hierarchy_nodes(root: Any) -> dict[str, dict[str, Any]]:
    """Build a node ID index from a hierarchy JSON object.

    The canonical hierarchy schema stores nodes in a flat top-level list, but
    recursive traversal also supports small nested fixtures without changing
    the traceability contract.

    Args:
        root: Parsed hierarchy JSON value.

    Returns:
        Mapping from non-empty ``node_id`` values to their node dictionaries.
    """
    index: dict[str, dict[str, Any]] = {}

    def _visit(value: Any) -> None:
        if isinstance(value, dict):
            node_id = value.get("node_id")
            if isinstance(node_id, str) and node_id:
                index[node_id] = value
            for child in value.values():
                _visit(child)
        elif isinstance(value, list):
            for child in value:
                _visit(child)

    _visit(root)
    return index


def _check_hierarchy_traceability(
    chunk: LegalChunk,
    hierarchy_index: dict[str, dict[str, Any]],
) -> list[tuple[str, str]]:
    """Return structural hierarchy traceability failures for one chunk.

    Checks node existence and compares hierarchy level/number metadata only
    when those fields are clearly present in the indexed node dictionaries.
    It does not compare source text, offsets, legal semantics, or citations.

    Args:
        chunk: Validated processed legal chunk.
        hierarchy_index: Mapping of hierarchy node IDs to node dictionaries.

    Returns:
        A list of ``(field, reason)`` failures. Multiple failures still
        represent one failed chunk in the validation report.
    """
    failures: list[tuple[str, str]] = []
    source_node = hierarchy_index.get(chunk.source_node_id)
    parent_article_node = hierarchy_index.get(chunk.parent_article_node_id)

    if source_node is None:
        failures.append(
            (
                "source_node_id",
                f"source_node_id not found in hierarchy: {chunk.source_node_id}",
            )
        )
    if parent_article_node is None:
        failures.append(
            (
                "parent_article_node_id",
                (f"parent_article_node_id not found in hierarchy: {chunk.parent_article_node_id}"),
            )
        )

    if parent_article_node is not None:
        parent_level = parent_article_node.get("level")
        if parent_level is not None and str(parent_level) != "article":
            failures.append(
                (
                    "parent_article_node_id",
                    f"parent node level is {parent_level!r}, expected 'article'",
                )
            )
        parent_number = parent_article_node.get("number")
        if (
            parent_number is not None
            and chunk.article_number is not None
            and str(parent_number) != chunk.article_number
        ):
            failures.append(
                (
                    "article_number",
                    (
                        f"parent article number is {parent_number!r}, "
                        f"chunk has {chunk.article_number!r}"
                    ),
                )
            )

    if source_node is None:
        return failures

    source_level = source_node.get("level")
    source_number = source_node.get("number")

    if chunk.chunk_kind in {"article_level", "article_level_empty"}:
        if source_level is not None and str(source_level) != "article":
            failures.append(
                ("source_node_id", f"source node level is {source_level!r}, expected 'article'")
            )
        if (
            source_number is not None
            and chunk.article_number is not None
            and str(source_number) != chunk.article_number
        ):
            failures.append(
                (
                    "article_number",
                    (
                        f"source article number is {source_number!r}, "
                        f"chunk has {chunk.article_number!r}"
                    ),
                )
            )
        if chunk.source_node_id != chunk.parent_article_node_id:
            failures.append(
                (
                    "parent_article_node_id",
                    "article-level source and parent article node IDs differ",
                )
            )
    elif chunk.chunk_kind == "clause_level":
        if source_level is not None and str(source_level) != "clause":
            failures.append(
                ("source_node_id", f"source node level is {source_level!r}, expected 'clause'")
            )
        if (
            source_number is not None
            and chunk.clause_number is not None
            and str(source_number) != chunk.clause_number
        ):
            failures.append(
                (
                    "clause_number",
                    (
                        f"source clause number is {source_number!r}, "
                        f"chunk has {chunk.clause_number!r}"
                    ),
                )
            )
        source_parent_id = source_node.get("parent_id")
        if (
            isinstance(source_parent_id, str)
            and source_parent_id
            and source_parent_id != chunk.parent_article_node_id
        ):
            failures.append(
                (
                    "parent_article_node_id",
                    (
                        f"source clause parent is {source_parent_id!r}, "
                        f"chunk has {chunk.parent_article_node_id!r}"
                    ),
                )
            )
    elif chunk.chunk_kind == "point_level":
        if source_level is not None and str(source_level) != "point":
            failures.append(
                ("source_node_id", f"source node level is {source_level!r}, expected 'point'")
            )
        if (
            source_number is not None
            and chunk.point_label is not None
            and str(source_number) != chunk.point_label
        ):
            failures.append(
                (
                    "point_label",
                    (f"source point label is {source_number!r}, chunk has {chunk.point_label!r}"),
                )
            )

        clause_node_id = source_node.get("parent_id")
        if isinstance(clause_node_id, str) and clause_node_id:
            clause_node = hierarchy_index.get(clause_node_id)
            if clause_node is None:
                failures.append(
                    (
                        "clause_number",
                        f"point parent clause node not found: {clause_node_id}",
                    )
                )
            else:
                clause_level = clause_node.get("level")
                if clause_level is not None and str(clause_level) != "clause":
                    failures.append(
                        (
                            "clause_number",
                            f"point parent level is {clause_level!r}, expected 'clause'",
                        )
                    )
                clause_number = clause_node.get("number")
                if (
                    clause_number is not None
                    and chunk.clause_number is not None
                    and str(clause_number) != chunk.clause_number
                ):
                    failures.append(
                        (
                            "clause_number",
                            (
                                f"parent clause number is {clause_number!r}, "
                                f"chunk has {chunk.clause_number!r}"
                            ),
                        )
                    )
                clause_parent_id = clause_node.get("parent_id")
                if (
                    isinstance(clause_parent_id, str)
                    and clause_parent_id
                    and clause_parent_id != chunk.parent_article_node_id
                ):
                    failures.append(
                        (
                            "parent_article_node_id",
                            (
                                f"parent clause belongs to {clause_parent_id!r}, "
                                f"chunk has {chunk.parent_article_node_id!r}"
                            ),
                        )
                    )

    return failures


def _citation_contains_label(
    citation: str,
    label: str,
    value: str,
) -> bool:
    """Return whether a citation contains one exact hierarchy label and value.

    Matching is case-insensitive, allows flexible whitespace, and rejects
    identifier continuations such as ``Điều 10`` when ``Điều 1`` is expected.

    Args:
        citation: Citation text to inspect.
        label: Vietnamese hierarchy label such as ``Điều`` or ``Khoản``.
        value: Expected hierarchy identifier.

    Returns:
        True when the expected structural component appears in the citation.
    """
    pattern = rf"\b{re.escape(label)}\s+{re.escape(value)}(?!(?:\w|[.-]\w))"
    return re.search(pattern, citation, flags=re.IGNORECASE) is not None


def _scan_contamination(
    text: str,
    parent_text: str,
    hard_markers: list[str],
    warning_markers: list[str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Find configured contamination markers in child and parent text.

    Matching is Unicode-aware and case-insensitive. Runs of whitespace are
    normalized so fixed markers remain detectable across line wrapping, while
    punctuation such as the colon in ``Lưu:`` remains required.

    Args:
        text: Child chunk content used for embedding.
        parent_text: Parent Article context used for retrieval and generation.
        hard_markers: Markers that make the chunk invalid.
        warning_markers: Markers that produce warning-only diagnostics.

    Returns:
        Hard and warning matches as ``(field_name, configured_marker)`` tuples.
    """

    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    normalized_fields = {
        "text": _normalize(text),
        "parent_text": _normalize(parent_text),
    }

    def _find(markers: list[str]) -> list[tuple[str, str]]:
        matches: list[tuple[str, str]] = []
        for field_name, normalized_text in normalized_fields.items():
            for marker in markers:
                normalized_marker = _normalize(marker)
                if normalized_marker and normalized_marker in normalized_text:
                    matches.append((field_name, marker))
        return matches

    return _find(hard_markers), _find(warning_markers)


def _scan_repealed_patterns(
    text: str,
    parent_text: str,
    patterns: list[str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Find configured repealed placeholders in child and parent text.

    Patterns are treated as conservative fixed phrases rather than broad
    semantic expressions. Matching is case-insensitive and tolerates runs of
    whitespace, while preserving punctuation such as literal parentheses.

    Args:
        text: Selected Article, Clause, or Point content.
        parent_text: Parent Article context.
        patterns: Configured repealed placeholder phrases.

    Returns:
        Separate child and parent matches as ``(field_name, pattern)`` tuples.
    """

    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    def _find(field_name: str, value: str) -> list[tuple[str, str]]:
        normalized_value = _normalize(value)
        matches: list[tuple[str, str]] = []
        for pattern in patterns:
            normalized_pattern = _normalize(pattern)
            if normalized_pattern and normalized_pattern in normalized_value:
                matches.append((field_name, pattern))
        return matches

    return _find("text", text), _find("parent_text", parent_text)


def _check_citation_structure(chunk: LegalChunk) -> list[tuple[str, str]]:
    """Return required citation components missing for a supported chunk kind.

    Unknown chunk kinds are outside Slice 3C and are not failed here. Missing
    hierarchy metadata values are handled by required-field validation, so
    this helper skips checks whose expected value is absent.

    Args:
        chunk: Validated legal chunk whose citation should be checked.

    Returns:
        Missing ``(label, value)`` pairs. An empty list means the citation is
        structurally valid for the supported chunk kind.
    """
    required_components: list[tuple[str, str | None]]
    if chunk.chunk_kind in {"article_level", "article_level_empty"}:
        required_components = [("Điều", chunk.article_number)]
    elif chunk.chunk_kind == "clause_level":
        required_components = [
            ("Khoản", chunk.clause_number),
            ("Điều", chunk.article_number),
        ]
    elif chunk.chunk_kind == "point_level":
        required_components = [
            ("Điểm", chunk.point_label),
            ("Khoản", chunk.clause_number),
            ("Điều", chunk.article_number),
        ]
    else:
        return []

    return [
        (label, value)
        for label, value in required_components
        if value is not None and not _citation_contains_label(chunk.citation, label, value)
    ]
