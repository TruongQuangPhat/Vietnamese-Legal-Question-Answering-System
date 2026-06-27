"""Batch service orchestration for parent-child chunking."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.processing.legal_chunk_models import (
    ChunkingIssue,
    ChunkingIssueCode,
    ChunkingReport,
    ChunkingStatus,
    ChunkingSummary,
    ChunkValidationSummary,
    LegalChunk,
)
from src.processing.legal_chunk_validator import LegalChunkValidationResult, LegalChunkValidator
from src.processing.legal_chunker import CHUNKER_VERSION, LegalChunker
from src.processing.legal_hierarchy_models import LegalHierarchyDocument
from src.processing.legal_tree_validator import LegalTreeValidationResult, LegalTreeValidator

REPORT_SCHEMA_VERSION = "1.0"
LONG_PARENT_TEXT_CHARS = 20_000


class _Clock(Protocol):
    """Clock protocol used to make service timing deterministic in tests."""

    def now(self) -> datetime:
        """Return the current time as a timezone-aware `datetime`."""


class _Chunker(Protocol):
    """Protocol for chunker dependency injection."""

    def chunk_document(
        self,
        document: LegalHierarchyDocument,
        *,
        source_file: str | None = None,
    ) -> list[LegalChunk]:
        """Chunk one hierarchy document without file I/O."""


class _TreeValidator(Protocol):
    """Protocol for hierarchy validation dependency injection."""

    def validate(
        self,
        *,
        document: LegalHierarchyDocument,
        normalized_text: str,
    ) -> LegalTreeValidationResult:
        """Validate a hierarchy document before chunking."""


class _ChunkValidator(Protocol):
    """Protocol for chunk validation dependency injection."""

    def validate(
        self,
        *,
        document: LegalHierarchyDocument,
        chunks: list[LegalChunk],
    ) -> LegalChunkValidationResult:
        """Validate chunks produced for one hierarchy document."""


class _SystemClock:
    """UTC wall-clock implementation for production service runs."""

    def now(self) -> datetime:
        """Return the current UTC instant."""
        return datetime.now(UTC)


class DiscoveredHierarchyInput(BaseModel):
    """One hierarchy input discovered for batch chunking.

    Attributes:
        law_id: Stable law ID derived from the parent directory.
        hierarchy_path: Path to `hierarchy.json`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    law_id: str = Field(..., min_length=1)
    hierarchy_path: Path = Field(...)


class ChunkingServiceResult(BaseModel):
    """In-memory result of one batch chunking service run.

    Attributes:
        report: Canonical parent-child chunking report.
        output_path: Path where JSONL chunks were written.
        report_path: Path where the report was written.
        failed_law_ids: Law IDs with failed per-law results.
        written_chunk_count: Number of chunk rows written to JSONL.
    """

    model_config = ConfigDict(extra="forbid")

    report: ChunkingReport = Field(...)
    output_path: str = Field(..., min_length=1)
    report_path: str = Field(..., min_length=1)
    failed_law_ids: list[str] = Field(default_factory=list)
    written_chunk_count: int = Field(0, ge=0)


class ChunkingServiceError(RuntimeError):
    """Raised when the batch chunking service itself cannot complete safely."""

    def __init__(self, issue: ChunkingIssue) -> None:
        """Initialize a service-level failure with a structured issue."""
        super().__init__(issue.message)
        self.issue = issue


class ChunkingService:
    """Run parent-child chunking over a deterministic batch of hierarchy artifacts.

    The service coordinates discovery, hierarchy loading, pre-chunk tree
    validation, chunk creation, chunk validation, JSONL writing, and report
    writing. It does not implement CLI parsing, crawling, cleaning, parsing,
    embedding, retrieval, RAG, or API behavior.
    """

    def __init__(
        self,
        *,
        chunker: _Chunker | None = None,
        tree_validator: _TreeValidator | None = None,
        chunk_validator: _ChunkValidator | None = None,
        clock: _Clock | None = None,
        chunk_writer: Any | None = None,
        report_writer: Any | None = None,
    ) -> None:
        """Initialize the service with injectable dependencies."""
        self._chunker = chunker or LegalChunker()
        self._tree_validator = tree_validator or LegalTreeValidator()
        self._chunk_validator = chunk_validator or LegalChunkValidator()
        self._clock = clock or _SystemClock()
        self._chunk_writer = chunk_writer or write_legal_chunks_jsonl
        self._report_writer = report_writer or write_chunking_report

    def run(
        self,
        *,
        input_dir: Path,
        output_path: Path,
        report_path: Path,
        law_ids: list[str] | None = None,
        overwrite: bool = False,
    ) -> ChunkingServiceResult:
        """Chunk selected hierarchy documents and write parent-child chunking outputs.

        Args:
            input_dir: Directory containing `{LAW_ID}/hierarchy.json` inputs.
            output_path: Destination corpus JSONL path.
            report_path: Destination chunking report path.
            law_ids: Optional selected law IDs. Missing requested IDs become
                deterministic failed per-law results.
            overwrite: Whether existing output/report files may be replaced.

        Returns:
            Service result containing report metadata and written row count.

        Raises:
            ChunkingServiceError: If output/report overwrite policy or writers
                prevent the batch from completing safely.
        """
        self._ensure_writable_outputs(
            output_path=output_path,
            report_path=report_path,
            overwrite=overwrite,
        )

        started = self._clock.now()
        discovered = discover_hierarchy_inputs(input_dir, law_ids=law_ids)
        summaries: list[ChunkingSummary] = []
        all_chunks: list[LegalChunk] = []
        all_warnings: list[ChunkingIssue] = []
        all_errors: list[ChunkingIssue] = []
        validation_results: list[LegalChunkValidationResult] = []

        for item in _ordered_batch_items(input_dir, discovered, law_ids):
            if not item.hierarchy_path.exists():
                issue = _missing_input_issue(item.law_id, item.hierarchy_path)
                summaries.append(_failed_summary(item, issue))
                all_errors.append(issue)
                continue

            try:
                document = load_hierarchy_document(item.hierarchy_path)
                tree_result = self._tree_validator.validate(
                    document=document,
                    normalized_text=_root_text(document),
                )
                if not tree_result.is_valid:
                    issue = _tree_validation_issue(item, tree_result)
                    summaries.append(_failed_summary(item, issue))
                    all_errors.append(issue)
                    continue

                chunks = self._chunker.chunk_document(
                    document,
                    source_file=str(item.hierarchy_path),
                )
                chunk_validation = self._chunk_validator.validate(
                    document=document,
                    chunks=chunks,
                )
                validation_results.append(chunk_validation)
                if not chunk_validation.is_valid:
                    summaries.append(_failed_summary(item, *chunk_validation.errors))
                    all_warnings.extend(chunk_validation.warnings)
                    all_errors.extend(chunk_validation.errors)
                    continue

                summaries.append(_success_summary(item, chunks, chunk_validation))
                all_chunks.extend(chunks)
                all_warnings.extend(chunk_validation.warnings)
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                issue = _exception_issue(
                    law_id=item.law_id,
                    code=ChunkingIssueCode.SCHEMA_VALIDATION_FAILED,
                    message="Hierarchy input failed parent-child chunking schema validation.",
                    exc=exc,
                    context={"hierarchy_path": str(item.hierarchy_path)},
                )
                summaries.append(_failed_summary(item, issue))
                all_errors.append(issue)
            except Exception as exc:  # noqa: BLE001 - batch boundary isolates per-law failures
                issue = _exception_issue(
                    law_id=item.law_id,
                    code=ChunkingIssueCode.JSONL_VALIDATION_FAILED,
                    message="Chunking failed for one law.",
                    exc=exc,
                    context={"hierarchy_path": str(item.hierarchy_path)},
                )
                summaries.append(_failed_summary(item, issue))
                all_errors.append(issue)

        finished = self._clock.now()
        report = _build_report(
            input_dir=input_dir,
            output_path=output_path,
            started_at=_format_utc(started),
            finished_at=_format_utc(finished),
            duration_seconds=_duration_seconds(started, finished),
            summaries=summaries,
            chunks=all_chunks,
            warnings=_deduplicate_issues(all_warnings),
            errors=_deduplicate_issues(all_errors),
            validation_results=validation_results,
        )

        try:
            self._chunk_writer(output_path, all_chunks)
            self._report_writer(report_path, report)
        except OSError as exc:
            raise ChunkingServiceError(
                _exception_issue(
                    law_id="BATCH",
                    code=ChunkingIssueCode.OUTPUT_WRITE_FAILED,
                    message="Chunking output or report could not be written.",
                    exc=exc,
                    context={"output_path": str(output_path), "report_path": str(report_path)},
                )
            ) from exc

        return ChunkingServiceResult(
            report=report,
            output_path=str(output_path),
            report_path=str(report_path),
            failed_law_ids=[
                summary.law_id for summary in summaries if summary.status == ChunkingStatus.FAILED
            ],
            written_chunk_count=len(all_chunks),
        )

    @staticmethod
    def _ensure_writable_outputs(
        *,
        output_path: Path,
        report_path: Path,
        overwrite: bool,
    ) -> None:
        """Enforce overwrite policy for global generated outputs."""
        if overwrite:
            return
        existing = [str(path) for path in (output_path, report_path) if path.exists()]
        if not existing:
            return
        raise ChunkingServiceError(
            ChunkingIssue(
                code=ChunkingIssueCode.EXISTING_OUTPUT_BLOCKED,
                message="Chunking output already exists and overwrite is disabled.",
                law_id="BATCH",
                context={"existing_paths": existing, "overwrite": False},
            )
        )


def discover_hierarchy_inputs(
    input_dir: Path,
    law_ids: list[str] | None = None,
) -> list[DiscoveredHierarchyInput]:
    """Discover hierarchy inputs in deterministic law-ID order."""
    selected = set(law_ids or [])
    discovered: list[DiscoveredHierarchyInput] = []
    for path in input_dir.glob("*/hierarchy.json"):
        if not path.is_file():
            continue
        law_id = path.parent.name
        if selected and law_id not in selected:
            continue
        discovered.append(DiscoveredHierarchyInput(law_id=law_id, hierarchy_path=path))
    return sorted(discovered, key=lambda item: item.law_id)


def load_hierarchy_document(path: Path) -> LegalHierarchyDocument:
    """Load and validate one legal hierarchy parsing `hierarchy.json` artifact."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return LegalHierarchyDocument.model_validate(payload)


def write_legal_chunks_jsonl(path: Path, chunks: list[LegalChunk]) -> None:
    """Write legal chunks as UTF-8 JSONL with deterministic row order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) for chunk in chunks]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_chunking_report(path: Path, report: ChunkingReport) -> None:
    """Write the batch chunking report as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _ordered_batch_items(
    input_dir: Path,
    discovered: list[DiscoveredHierarchyInput],
    law_ids: list[str] | None,
) -> list[DiscoveredHierarchyInput]:
    """Return discovered plus requested-missing items in deterministic order."""
    by_law_id = {item.law_id: item for item in discovered}
    if law_ids is None:
        return discovered

    items: list[DiscoveredHierarchyInput] = []
    for law_id in sorted(set(law_ids)):
        existing = by_law_id.get(law_id)
        if existing is not None:
            items.append(existing)
            continue
        items.append(
            DiscoveredHierarchyInput(
                law_id=law_id,
                hierarchy_path=input_dir / law_id / "hierarchy.json",
            )
        )
    return items


def _build_report(
    *,
    input_dir: Path,
    output_path: Path,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    summaries: list[ChunkingSummary],
    chunks: list[LegalChunk],
    warnings: list[ChunkingIssue],
    errors: list[ChunkingIssue],
    validation_results: list[LegalChunkValidationResult],
) -> ChunkingReport:
    """Aggregate per-law chunking outputs into the canonical report."""
    chunks_by_level: dict[str, int] = {}
    chunks_by_law: dict[str, int] = {}
    for chunk in chunks:
        chunks_by_level[chunk.level.value] = chunks_by_level.get(chunk.level.value, 0) + 1
        chunks_by_law[chunk.law_id] = chunks_by_law.get(chunk.law_id, 0) + 1

    return ChunkingReport(
        schema_version=REPORT_SCHEMA_VERSION,
        chunker_version=CHUNKER_VERSION,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        input_dir=str(input_dir),
        output_path=str(output_path),
        total_laws=len(summaries),
        successful=sum(1 for summary in summaries if summary.status == ChunkingStatus.SUCCESS),
        success_with_warnings=sum(
            1 for summary in summaries if summary.status == ChunkingStatus.SUCCESS_WITH_WARNINGS
        ),
        failed=sum(1 for summary in summaries if summary.status == ChunkingStatus.FAILED),
        total_chunks=len(chunks),
        chunks_by_level=chunks_by_level,
        chunks_by_law=chunks_by_law,
        empty_or_repealed_article_chunks=sum(
            1 for chunk in chunks if chunk.metadata.is_empty_or_repealed
        ),
        warnings=warnings,
        errors=errors,
        validation_summary=_aggregate_validation_summary(validation_results),
        law_summaries=summaries,
    )


def _success_summary(
    item: DiscoveredHierarchyInput,
    chunks: list[LegalChunk],
    validation: LegalChunkValidationResult,
) -> ChunkingSummary:
    """Build a successful or warning-bearing per-law summary."""
    chunks_by_level: dict[str, int] = {}
    for chunk in chunks:
        chunks_by_level[chunk.level.value] = chunks_by_level.get(chunk.level.value, 0) + 1
    return ChunkingSummary(
        law_id=item.law_id,
        status=(
            ChunkingStatus.SUCCESS_WITH_WARNINGS if validation.warnings else ChunkingStatus.SUCCESS
        ),
        input_path=str(item.hierarchy_path),
        total_chunks=len(chunks),
        chunks_by_level=chunks_by_level,
        article_level_chunks=chunks_by_level.get("article", 0),
        clause_level_chunks=chunks_by_level.get("clause", 0),
        point_level_chunks=chunks_by_level.get("point", 0),
        empty_or_repealed_chunks=sum(1 for chunk in chunks if chunk.metadata.is_empty_or_repealed),
        long_parent_text_chunks=sum(
            1 for chunk in chunks if len(chunk.parent_text) > LONG_PARENT_TEXT_CHARS
        ),
        warning_count=len(validation.warnings),
        error_count=0,
    )


def _failed_summary(
    item: DiscoveredHierarchyInput,
    *issues: ChunkingIssue,
) -> ChunkingSummary:
    """Build a failed per-law summary."""
    return ChunkingSummary(
        law_id=item.law_id,
        status=ChunkingStatus.FAILED,
        input_path=str(item.hierarchy_path),
        error_count=len(issues),
    )


def _aggregate_validation_summary(
    validation_results: list[LegalChunkValidationResult],
) -> ChunkValidationSummary:
    """Aggregate validation summaries from per-law chunk validation results."""
    total = ChunkValidationSummary()
    for result in validation_results:
        summary = result.validation_summary
        total.total_chunks_checked += summary.total_chunks_checked
        total.duplicate_chunk_ids += summary.duplicate_chunk_ids
        total.missing_source_nodes += summary.missing_source_nodes
        total.invalid_parent_articles += summary.invalid_parent_articles
        total.invalid_offsets += summary.invalid_offsets
        total.text_mismatches += summary.text_mismatches
        total.parent_text_mismatches += summary.parent_text_mismatches
        total.invalid_chunk_levels += summary.invalid_chunk_levels
        total.jsonl_lines_checked += summary.jsonl_lines_checked
        total.jsonl_parse_errors += summary.jsonl_parse_errors
        total.report_count_mismatches += summary.report_count_mismatches
    return total


def _root_text(document: LegalHierarchyDocument) -> str:
    """Return the root Law text used as the normalized-text validation source."""
    root = next(node for node in document.nodes if node.node_id == document.root_node_id)
    return root.text


def _missing_input_issue(law_id: str, hierarchy_path: Path) -> ChunkingIssue:
    """Create a structured issue for a requested missing hierarchy input."""
    return ChunkingIssue(
        code=ChunkingIssueCode.MISSING_HIERARCHY_INPUT,
        message="Requested hierarchy.json input was not found.",
        law_id=law_id,
        context={"hierarchy_path": str(hierarchy_path)},
    )


def _tree_validation_issue(
    item: DiscoveredHierarchyInput,
    tree_result: LegalTreeValidationResult,
) -> ChunkingIssue:
    """Create a structured issue for hierarchy pre-check failure."""
    return ChunkingIssue(
        code=ChunkingIssueCode.TREE_VALIDATION_FAILED,
        message="Legal hierarchy failed pre-chunk tree validation.",
        law_id=item.law_id,
        context={
            "hierarchy_path": str(item.hierarchy_path),
            "error_count": len(tree_result.errors),
        },
    )


def _exception_issue(
    *,
    law_id: str,
    code: ChunkingIssueCode,
    message: str,
    exc: Exception,
    context: dict[str, Any],
) -> ChunkingIssue:
    """Convert a service boundary exception into a structured issue."""
    return ChunkingIssue(
        code=code,
        message=message,
        law_id=law_id,
        context={
            **context,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
    )


def _deduplicate_issues(issues: list[ChunkingIssue]) -> list[ChunkingIssue]:
    """Deduplicate issues while preserving first-seen order."""
    deduped: list[ChunkingIssue] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        key = _issue_key(issue)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _issue_key(issue: ChunkingIssue) -> tuple[Any, ...]:
    """Build the service-level issue deduplication key."""
    context = json.dumps(issue.context, ensure_ascii=False, sort_keys=True, default=str)
    return (
        issue.code.value,
        issue.law_id,
        issue.chunk_id,
        issue.source_node_id,
        issue.start_offset,
        issue.end_offset,
        context,
    )


def _duration_seconds(started: datetime, finished: datetime) -> float:
    """Return a non-negative elapsed duration in seconds."""
    return max((finished - started).total_seconds(), 0.0)


def _format_utc(value: datetime) -> str:
    """Format a datetime as a UTC ISO-8601 string with `Z` suffix."""
    utc_value = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return utc_value.isoformat().replace("+00:00", "Z")
