"""Batch service orchestration for Phase 5 legal hierarchy parsing.

This module coordinates already-implemented deterministic Phase 5 processing
over one or more normalized legal documents. It discovers inputs, calls the
per-document parser facade, writes successful `hierarchy.json` artifacts, and
aggregates the canonical batch parsing report.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.processing.legal_hierarchy_builder import PARSER_VERSION
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalParsingReport,
    LegalParsingResult,
    LegalParsingStatus,
    ParsingIssueCode,
    StructuredParsingIssue,
    ValidationSummary,
)
from src.processing.legal_parser import LegalParser, LegalParserExecutionResult

REPORT_SCHEMA_VERSION = "1.0"


class _Clock(Protocol):
    """Clock protocol used to make service timing deterministic in tests."""

    def now(self) -> datetime:
        """Return the current time as a timezone-aware `datetime`."""


class _Parser(Protocol):
    """Protocol for the per-document parser dependency."""

    def parse_file(
        self,
        *,
        normalized_path: Path,
        cleaned_path: Path | None = None,
    ) -> LegalParserExecutionResult:
        """Parse one normalized artifact without writing output."""


class _SystemClock:
    """UTC wall-clock implementation for production service runs."""

    def now(self) -> datetime:
        """Return the current UTC instant."""
        return datetime.now(UTC)


class DiscoveredNormalizedInput(BaseModel):
    """One normalized input discovered for batch parsing.

    Attributes:
        law_id: Stable law ID derived from the parent directory.
        normalized_path: Path to `normalized.json`.
        cleaned_path: Expected sibling `cleaned.txt` path.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    law_id: str = Field(..., min_length=1)
    normalized_path: Path = Field(...)
    cleaned_path: Path = Field(...)


class LegalParsingServiceResult(BaseModel):
    """In-memory result of one batch parsing service run.

    Attributes:
        report: Canonical batch parsing report.
        written_hierarchy_paths: Hierarchy artifact paths written successfully.
        report_path: Path where the batch report was written.
        failed_law_ids: Law IDs with failed per-law results.
        skipped_law_ids: Law IDs blocked by service policy, such as existing
            outputs with `overwrite=False`.
    """

    model_config = ConfigDict(extra="forbid")

    report: LegalParsingReport = Field(...)
    written_hierarchy_paths: list[str] = Field(default_factory=list)
    report_path: str = Field(..., min_length=1)
    failed_law_ids: list[str] = Field(default_factory=list)
    skipped_law_ids: list[str] = Field(default_factory=list)


class LegalParsingServiceError(RuntimeError):
    """Raised when the batch service itself cannot complete safely."""

    def __init__(self, issue: StructuredParsingIssue) -> None:
        """Initialize a service-level failure with a structured issue."""
        super().__init__(issue.message)
        self.issue = issue


class LegalParsingService:
    """Run Phase 5 parsing over a deterministic batch of normalized artifacts.

    The service performs orchestration and artifact writing only. It does not
    implement legal heading recognition, span segmentation, hierarchy building,
    validation, CLI parsing, crawling, cleaning, chunking, or RAG behavior.
    """

    def __init__(
        self,
        *,
        parser: _Parser | None = None,
        clock: _Clock | None = None,
        hierarchy_writer: Any | None = None,
        report_writer: Any | None = None,
    ) -> None:
        """Initialize the service with injectable dependencies.

        Args:
            parser: Optional per-document parser dependency.
            clock: Optional clock used for deterministic timing.
            hierarchy_writer: Optional callable used to write hierarchy JSON.
            report_writer: Optional callable used to write report JSON.
        """
        self._parser = parser or LegalParser()
        self._clock = clock or _SystemClock()
        self._hierarchy_writer = hierarchy_writer or write_hierarchy_document
        self._report_writer = report_writer or write_parsing_report

    def run(
        self,
        *,
        input_dir: Path,
        output_dir: Path,
        report_path: Path,
        law_ids: list[str] | None = None,
        overwrite: bool = False,
    ) -> LegalParsingServiceResult:
        """Parse selected normalized legal documents and write Phase 5 outputs.

        Args:
            input_dir: Directory containing `{LAW_ID}/normalized.json` inputs.
            output_dir: Directory where `{LAW_ID}/hierarchy.json` is written.
            report_path: Path to the batch `legal_parsing_report.json`.
            law_ids: Optional selected law IDs. Missing requested IDs become
                deterministic failed per-law results.
            overwrite: Whether an existing `hierarchy.json` may be replaced.

        Returns:
            Service result containing the written report and output paths.

        Raises:
            LegalParsingServiceError: If the report cannot be written.
        """
        started = self._clock.now()
        discovered = discover_normalized_inputs(input_dir, law_ids=law_ids)
        results: list[LegalParsingResult] = []
        parser_results: list[LegalParserExecutionResult | None] = []
        written_paths: list[str] = []
        skipped_law_ids: list[str] = []

        for item in _ordered_batch_items(input_dir, discovered, law_ids):
            law_started = self._clock.now()
            hierarchy_path = output_dir / item.law_id / "hierarchy.json"

            if not item.normalized_path.exists():
                law_finished = self._clock.now()
                results.append(
                    _failed_result(
                        law_id=item.law_id,
                        input_path=item.normalized_path,
                        output_path=None,
                        duration_seconds=_duration_seconds(law_started, law_finished),
                        error=_missing_input_issue(item.law_id, item.normalized_path),
                    )
                )
                parser_results.append(None)
                continue

            if hierarchy_path.exists() and not overwrite:
                law_finished = self._clock.now()
                skipped_law_ids.append(item.law_id)
                results.append(
                    _failed_result(
                        law_id=item.law_id,
                        input_path=item.normalized_path,
                        output_path=str(hierarchy_path),
                        duration_seconds=_duration_seconds(law_started, law_finished),
                        error=_existing_output_issue(item.law_id, hierarchy_path),
                    )
                )
                parser_results.append(None)
                continue

            try:
                parser_result = self._parser.parse_file(
                    normalized_path=item.normalized_path,
                    cleaned_path=item.cleaned_path if item.cleaned_path.exists() else None,
                )
            except Exception as exc:  # noqa: BLE001 - outer batch boundary converts per-law failure
                law_finished = self._clock.now()
                results.append(
                    _failed_result(
                        law_id=item.law_id,
                        input_path=item.normalized_path,
                        output_path=None,
                        duration_seconds=_duration_seconds(law_started, law_finished),
                        error=_exception_issue(
                            law_id=item.law_id,
                            message="Legal parser failed for one law.",
                            exc=exc,
                            context={"normalized_path": str(item.normalized_path)},
                        ),
                    )
                )
                parser_results.append(None)
                continue

            parser_results.append(parser_result)
            parsing_result = parser_result.parsing_result

            if (
                parser_result.status
                in {LegalParsingStatus.SUCCESS, LegalParsingStatus.SUCCESS_WITH_WARNINGS}
                and parser_result.document is not None
            ):
                try:
                    self._hierarchy_writer(hierarchy_path, parser_result.document)
                except OSError as exc:
                    law_finished = self._clock.now()
                    results.append(
                        _failed_result(
                            law_id=item.law_id,
                            input_path=item.normalized_path,
                            output_path=None,
                            duration_seconds=_duration_seconds(law_started, law_finished),
                            error=_exception_issue(
                                law_id=item.law_id,
                                message="Hierarchy output could not be written.",
                                exc=exc,
                                context={"hierarchy_path": str(hierarchy_path)},
                            ),
                        )
                    )
                    continue
                written_paths.append(str(hierarchy_path))
                law_finished = self._clock.now()
                results.append(
                    parsing_result.model_copy(
                        update={
                            "output_path": str(hierarchy_path),
                            "duration_seconds": _duration_seconds(law_started, law_finished),
                        },
                        deep=True,
                    )
                )
                continue

            law_finished = self._clock.now()
            results.append(
                parsing_result.model_copy(
                    update={"duration_seconds": _duration_seconds(law_started, law_finished)},
                    deep=True,
                )
            )

        finished = self._clock.now()
        report = _build_report(
            input_dir=input_dir,
            output_dir=output_dir,
            started_at=_format_utc(started),
            finished_at=_format_utc(finished),
            duration_seconds=_duration_seconds(started, finished),
            results=results,
            parser_results=parser_results,
        )

        try:
            self._report_writer(report_path, report)
        except OSError as exc:
            raise LegalParsingServiceError(
                _exception_issue(
                    law_id="BATCH",
                    message="Legal parsing report could not be written.",
                    exc=exc,
                    context={"report_path": str(report_path)},
                )
            ) from exc

        return LegalParsingServiceResult(
            report=report,
            written_hierarchy_paths=written_paths,
            report_path=str(report_path),
            failed_law_ids=[
                result.law_id for result in results if result.status == LegalParsingStatus.FAILED
            ],
            skipped_law_ids=skipped_law_ids,
        )


def discover_normalized_inputs(
    input_dir: Path,
    law_ids: list[str] | None = None,
) -> list[DiscoveredNormalizedInput]:
    """Discover normalized Phase 5 inputs in deterministic law-ID order.

    Args:
        input_dir: Directory containing `{LAW_ID}/normalized.json`.
        law_ids: Optional law-ID filter.

    Returns:
        Discovered normalized input records sorted by law ID.
    """
    selected = set(law_ids or [])
    discovered: list[DiscoveredNormalizedInput] = []
    for path in input_dir.glob("*/normalized.json"):
        if not path.is_file():
            continue
        law_id = path.parent.name
        if selected and law_id not in selected:
            continue
        discovered.append(
            DiscoveredNormalizedInput(
                law_id=law_id,
                normalized_path=path,
                cleaned_path=path.with_name("cleaned.txt"),
            )
        )
    return sorted(discovered, key=lambda item: item.law_id)


def write_hierarchy_document(path: Path, document: LegalHierarchyDocument) -> None:
    """Write one successful hierarchy document as UTF-8 JSON.

    Args:
        path: Destination `hierarchy.json` path.
        document: Canonical hierarchy document to serialize.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_parsing_report(path: Path, report: LegalParsingReport) -> None:
    """Write the batch legal parsing report as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _ordered_batch_items(
    input_dir: Path,
    discovered: list[DiscoveredNormalizedInput],
    law_ids: list[str] | None,
) -> list[DiscoveredNormalizedInput]:
    """Return discovered plus requested-missing items in deterministic order."""
    by_law_id = {item.law_id: item for item in discovered}
    if law_ids is None:
        return discovered

    items: list[DiscoveredNormalizedInput] = []
    for law_id in sorted(set(law_ids)):
        existing = by_law_id.get(law_id)
        if existing is not None:
            items.append(existing)
            continue
        normalized_path = input_dir / law_id / "normalized.json"
        items.append(
            DiscoveredNormalizedInput(
                law_id=law_id,
                normalized_path=normalized_path,
                cleaned_path=normalized_path.with_name("cleaned.txt"),
            )
        )
    return items


def _build_report(
    *,
    input_dir: Path,
    output_dir: Path,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    results: list[LegalParsingResult],
    parser_results: list[LegalParserExecutionResult | None],
) -> LegalParsingReport:
    """Aggregate per-law parser results into the canonical batch report."""
    successful_statuses = {
        LegalParsingStatus.SUCCESS,
        LegalParsingStatus.SUCCESS_WITH_WARNINGS,
    }
    return LegalParsingReport(
        schema_version=REPORT_SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        total_documents=len(results),
        successful=sum(1 for result in results if result.status == LegalParsingStatus.SUCCESS),
        success_with_warnings=sum(
            1 for result in results if result.status == LegalParsingStatus.SUCCESS_WITH_WARNINGS
        ),
        failed=sum(1 for result in results if result.status == LegalParsingStatus.FAILED),
        nodes_by_level=_aggregate_nodes_by_level(results, successful_statuses),
        validation_summary=_aggregate_validation_summary(parser_results),
        results=results,
        warnings=_deduplicate_issues([issue for result in results for issue in result.warnings]),
        errors=_deduplicate_issues([issue for result in results for issue in result.errors]),
    )


def _aggregate_nodes_by_level(
    results: list[LegalParsingResult],
    successful_statuses: set[LegalParsingStatus],
) -> dict[str, int]:
    """Sum node counts by level for successful per-law results only."""
    totals: dict[str, int] = {}
    for result in results:
        if result.status not in successful_statuses:
            continue
        for level, count in result.counts_by_level.items():
            totals[level] = totals.get(level, 0) + count
    return totals


def _aggregate_validation_summary(
    parser_results: list[LegalParserExecutionResult | None],
) -> ValidationSummary:
    """Aggregate validation summaries from parser executions."""
    totals = ValidationSummary()
    for parser_result in parser_results:
        if parser_result is None:
            continue
        summary = parser_result.validation_summary
        totals.missing_article_1 += summary.missing_article_1
        totals.article_heading_mismatch += summary.article_heading_mismatch
        totals.orphan_nodes += summary.orphan_nodes
        totals.invalid_parent_chain += summary.invalid_parent_chain
        totals.invalid_offsets += summary.invalid_offsets
        totals.invalid_sibling_overlap += summary.invalid_sibling_overlap
        totals.empty_article_nodes += summary.empty_article_nodes
        totals.duplicate_node_ids += summary.duplicate_node_ids
    return totals


def _failed_result(
    *,
    law_id: str,
    input_path: Path,
    output_path: str | None,
    duration_seconds: float,
    error: StructuredParsingIssue,
) -> LegalParsingResult:
    """Build a canonical failed per-law parsing result."""
    return LegalParsingResult(
        law_id=law_id,
        status=LegalParsingStatus.FAILED,
        input_path=str(input_path),
        output_path=output_path,
        duration_seconds=duration_seconds,
        node_count=0,
        counts_by_level={},
        has_article_1=False,
        max_article_number=0,
        expected_article_heading_count=0,
        article_heading_count_matches=False,
        expected_max_heading_article_number=0,
        max_article_number_matches=False,
        warnings=[],
        errors=[error],
    )


def _missing_input_issue(law_id: str, normalized_path: Path) -> StructuredParsingIssue:
    """Create a structured issue for a requested missing input file."""
    return StructuredParsingIssue(
        code=ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE,
        message="Requested normalized.json input was not found.",
        law_id=law_id,
        context={"normalized_path": str(normalized_path)},
    )


def _existing_output_issue(law_id: str, hierarchy_path: Path) -> StructuredParsingIssue:
    """Create a structured issue for protected existing hierarchy output."""
    return StructuredParsingIssue(
        code=ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE,
        message="Hierarchy output already exists and overwrite is disabled.",
        law_id=law_id,
        context={"hierarchy_path": str(hierarchy_path), "overwrite": False},
    )


def _exception_issue(
    *,
    law_id: str,
    message: str,
    exc: Exception,
    context: dict[str, Any],
) -> StructuredParsingIssue:
    """Convert an expected service boundary failure into a structured issue."""
    return StructuredParsingIssue(
        code=ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE,
        message=message,
        law_id=law_id,
        context={
            **context,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
    )


def _deduplicate_issues(
    issues: list[StructuredParsingIssue],
) -> list[StructuredParsingIssue]:
    """Deduplicate issues while preserving deterministic first-seen order."""
    deduped: list[StructuredParsingIssue] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        key = _issue_key(issue)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _issue_key(issue: StructuredParsingIssue) -> tuple[Any, ...]:
    """Build the service-level issue deduplication key.

    Service reports aggregate across laws, so the law ID is included to avoid
    collapsing equivalent defects from distinct legal documents.
    """
    context = json.dumps(issue.context, ensure_ascii=False, sort_keys=True, default=str)
    return (
        issue.code.value,
        issue.law_id,
        issue.node_id,
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
