"""Per-document parser facade for legal hierarchy parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.processing.legal_heading_recognizer import HeadingRecognitionResult, LegalHeadingRecognizer
from src.processing.legal_hierarchy_builder import (
    HierarchyBuildResult,
    LegalHierarchyBuilder,
    LegalHierarchyBuildError,
)
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
    LegalParsingResult,
    LegalParsingStatus,
    ParsingIssueCode,
    StructuredParsingIssue,
    ValidationSummary,
)
from src.processing.legal_span_segmenter import (
    LegalSpanSegmenter,
    SpanSegmentationResult,
)
from src.processing.legal_tree_validator import LegalTreeValidationResult, LegalTreeValidator
from src.processing.normalized_input import (
    NormalizedInputLoadResult,
    NormalizedLegalArtifact,
    load_normalized_input,
)


class _HeadingRecognizer(Protocol):
    """Protocol for parser-recognizer dependency injection."""

    def recognize(self, normalized_text: str, *, law_id: str = "") -> HeadingRecognitionResult:
        """Recognize legal heading candidates from immutable source text."""


class _SpanSegmenter(Protocol):
    """Protocol for parser-segmenter dependency injection."""

    def segment(
        self,
        normalized_text: str,
        recognition_result: HeadingRecognitionResult,
    ) -> SpanSegmentationResult:
        """Convert recognized certain headings into segmented source spans."""


class _HierarchyBuilder(Protocol):
    """Protocol for parser-builder dependency injection."""

    def build(
        self,
        *,
        law_id: str,
        law_name: str,
        normalized_text: str,
        source_file: str,
        cleaner_version: str,
        metadata: LegalHierarchyMetadata,
        segmented_units: list[Any],
        inherited_warnings: list[StructuredParsingIssue] | None = None,
    ) -> HierarchyBuildResult:
        """Build a canonical hierarchy document from segmented legal units."""


class _TreeValidator(Protocol):
    """Protocol for parser-validator dependency injection."""

    def validate(
        self,
        *,
        document: LegalHierarchyDocument,
        normalized_text: str,
    ) -> LegalTreeValidationResult:
        """Validate a canonical hierarchy document."""


class LegalParserRecognitionSummary(BaseModel):
    """Recognition and segmentation counts for one parser facade execution."""

    model_config = ConfigDict(extra="forbid")

    certain_heading_count: int = Field(0, ge=0)
    ambiguous_candidate_count: int = Field(0, ge=0)
    rejected_candidate_count: int = Field(0, ge=0)
    boundary_count: int = Field(0, ge=0)
    segmented_unit_count: int = Field(0, ge=0)
    counts_by_level: dict[str, int] = Field(default_factory=dict)


class LegalParserExecutionResult(BaseModel):
    """In-memory result of parsing one normalized legal document.

    Attributes:
        law_id: Stable law identifier, or a deterministic fallback on input
            load failures.
        status: Per-document parser status.
        document: Valid hierarchy document, present only for successful parses.
        validation_summary: Structural validation counters.
        warnings: Deduplicated non-fatal structured issues.
        errors: Deduplicated hard structured issues.
        recognition_summary: Recognition and segmentation counts.
        parsing_result: Canonical per-law result model for future reports.

    Legal assumptions:
        This facade never writes `hierarchy.json` or batch reports. Failed
        executions do not expose invalid hierarchy documents as outputs.
    """

    model_config = ConfigDict(extra="forbid")

    law_id: str = Field(..., min_length=1)
    status: LegalParsingStatus = Field(...)
    document: LegalHierarchyDocument | None = Field(None)
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    warnings: list[StructuredParsingIssue] = Field(default_factory=list)
    errors: list[StructuredParsingIssue] = Field(default_factory=list)
    recognition_summary: LegalParserRecognitionSummary = Field(
        default_factory=LegalParserRecognitionSummary
    )
    parsing_result: LegalParsingResult = Field(...)


class LegalParser:
    """Compose legal hierarchy parsing components for exactly one document.

    The parser facade orchestrates normalized input, deterministic heading
    recognition, span segmentation, hierarchy building, and read-only tree
    validation. It does not duplicate component internals, process batches, or
    write generated artifacts.
    """

    def __init__(
        self,
        *,
        recognizer: _HeadingRecognizer | None = None,
        segmenter: _SpanSegmenter | None = None,
        builder: _HierarchyBuilder | None = None,
        validator: _TreeValidator | None = None,
    ) -> None:
        """Initialize the parser with injectable deterministic components.

        Args:
            recognizer: Optional heading recognizer dependency.
            segmenter: Optional span segmenter dependency.
            builder: Optional hierarchy builder dependency.
            validator: Optional tree validator dependency.
        """
        self._recognizer = recognizer or LegalHeadingRecognizer()
        self._segmenter = segmenter or LegalSpanSegmenter()
        self._builder = builder or LegalHierarchyBuilder()
        self._validator = validator or LegalTreeValidator()

    def parse_file(
        self,
        *,
        normalized_path: Path,
        cleaned_path: Path | None = None,
    ) -> LegalParserExecutionResult:
        """Load and parse one normalized artifact path without writing output.

        Args:
            normalized_path: Path to one `normalized.json` artifact.
            cleaned_path: Optional diagnostic `cleaned.txt` path.

        Returns:
            In-memory parser execution result.
        """
        source_file = str(normalized_path)
        fallback_law_id = _fallback_law_id(normalized_path)
        try:
            input_result = load_normalized_input(normalized_path, cleaned_path=cleaned_path)
        except FileNotFoundError as exc:
            return self._failure_result(
                law_id=fallback_law_id,
                source_file=source_file,
                error=_exception_issue(
                    code=ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE,
                    message="Normalized input file could not be loaded.",
                    law_id=fallback_law_id,
                    exc=exc,
                    source_file=source_file,
                ),
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            return self._failure_result(
                law_id=fallback_law_id,
                source_file=source_file,
                error=_exception_issue(
                    code=ParsingIssueCode.SCHEMA_VALIDATION_FAILED,
                    message="Normalized input failed legal hierarchy parsing schema validation.",
                    law_id=fallback_law_id,
                    exc=exc,
                    source_file=source_file,
                ),
            )

        return self.parse_loaded(input_result=input_result, source_file=source_file)

    def parse_loaded(
        self,
        *,
        input_result: NormalizedInputLoadResult,
        source_file: str,
    ) -> LegalParserExecutionResult:
        """Parse one already-loaded normalized artifact without file I/O.

        Args:
            input_result: Typed normalized input plus input-level warnings.
            source_file: Exact normalized input path to store in the hierarchy
                document and parsing result.

        Returns:
            In-memory parser execution result.
        """
        artifact = input_result.artifact
        inherited_warnings = _deduplicate_issues(input_result.warnings)
        recognition_summary = LegalParserRecognitionSummary()

        try:
            recognition_result = self._recognizer.recognize(
                artifact.normalized_text,
                law_id=artifact.law_id,
            )
            recognition_summary = _recognition_summary(recognition_result)
            inherited_warnings = _deduplicate_issues(
                [*inherited_warnings, *recognition_result.warnings]
            )

            segmentation_result = self._segmenter.segment(
                artifact.normalized_text,
                recognition_result,
            )
            recognition_summary = recognition_summary.model_copy(
                update={"segmented_unit_count": len(segmentation_result.units)}
            )

            metadata = _metadata_from_artifact(artifact)
            build_result = self._builder.build(
                law_id=artifact.law_id,
                law_name=artifact.law_name,
                normalized_text=artifact.normalized_text,
                source_file=source_file,
                cleaner_version=artifact.metadata.cleaner_version,
                metadata=metadata,
                segmented_units=segmentation_result.units,
                inherited_warnings=inherited_warnings,
            )
            validation_result = self._validator.validate(
                document=build_result.document,
                normalized_text=artifact.normalized_text,
            )
        except LegalHierarchyBuildError as exc:
            return self._failure_result(
                law_id=artifact.law_id,
                source_file=source_file,
                artifact=artifact,
                recognition_summary=recognition_summary,
                warnings=inherited_warnings,
                error=_exception_issue(
                    code=ParsingIssueCode.INVALID_TREE,
                    message="Legal hierarchy building failed.",
                    law_id=artifact.law_id,
                    exc=exc,
                    source_file=source_file,
                ),
            )
        except ValueError as exc:
            return self._failure_result(
                law_id=artifact.law_id,
                source_file=source_file,
                artifact=artifact,
                recognition_summary=recognition_summary,
                warnings=inherited_warnings,
                error=_exception_issue(
                    code=ParsingIssueCode.INVALID_OFFSET,
                    message="Legal span segmentation failed.",
                    law_id=artifact.law_id,
                    exc=exc,
                    source_file=source_file,
                ),
            )
        except ValidationError as exc:
            return self._failure_result(
                law_id=artifact.law_id,
                source_file=source_file,
                artifact=artifact,
                recognition_summary=recognition_summary,
                warnings=inherited_warnings,
                error=_exception_issue(
                    code=ParsingIssueCode.SCHEMA_VALIDATION_FAILED,
                    message="legal hierarchy parsing schema construction failed.",
                    law_id=artifact.law_id,
                    exc=exc,
                    source_file=source_file,
                ),
            )

        warnings = _deduplicate_issues(validation_result.warnings)
        errors = _deduplicate_issues(validation_result.errors)
        if not validation_result.is_valid and not errors:
            errors = [
                StructuredParsingIssue(
                    code=ParsingIssueCode.INVALID_TREE,
                    message="Tree validator returned invalid without structured errors.",
                    law_id=artifact.law_id,
                    context={"source_file": source_file},
                )
            ]

        if errors:
            return self._execution_result(
                law_id=artifact.law_id,
                source_file=source_file,
                status=LegalParsingStatus.FAILED,
                artifact=artifact,
                document=None,
                stats_document=build_result.document,
                validation_summary=validation_result.validation_summary,
                recognition_summary=recognition_summary,
                warnings=warnings,
                errors=errors,
            )

        status = (
            LegalParsingStatus.SUCCESS_WITH_WARNINGS if warnings else LegalParsingStatus.SUCCESS
        )
        return self._execution_result(
            law_id=artifact.law_id,
            source_file=source_file,
            status=status,
            artifact=artifact,
            document=build_result.document,
            stats_document=build_result.document,
            validation_summary=validation_result.validation_summary,
            recognition_summary=recognition_summary,
            warnings=warnings,
            errors=[],
        )

    def _failure_result(
        self,
        *,
        law_id: str,
        source_file: str,
        error: StructuredParsingIssue,
        artifact: NormalizedLegalArtifact | None = None,
        recognition_summary: LegalParserRecognitionSummary | None = None,
        warnings: list[StructuredParsingIssue] | None = None,
    ) -> LegalParserExecutionResult:
        """Build a deterministic failed parser result."""
        return self._execution_result(
            law_id=law_id,
            source_file=source_file,
            status=LegalParsingStatus.FAILED,
            artifact=artifact,
            document=None,
            stats_document=None,
            validation_summary=ValidationSummary(),
            recognition_summary=recognition_summary or LegalParserRecognitionSummary(),
            warnings=_deduplicate_issues(warnings or []),
            errors=[error],
        )

    def _execution_result(
        self,
        *,
        law_id: str,
        source_file: str,
        status: LegalParsingStatus,
        artifact: NormalizedLegalArtifact | None,
        document: LegalHierarchyDocument | None,
        stats_document: LegalHierarchyDocument | None,
        validation_summary: ValidationSummary,
        recognition_summary: LegalParserRecognitionSummary,
        warnings: list[StructuredParsingIssue],
        errors: list[StructuredParsingIssue],
    ) -> LegalParserExecutionResult:
        """Build the facade result plus canonical per-law parsing result."""
        deduped_warnings = _deduplicate_issues(warnings)
        deduped_errors = _deduplicate_issues(errors)
        parsing_result = _parsing_result(
            law_id=law_id,
            status=status,
            source_file=source_file,
            artifact=artifact,
            document=stats_document,
            warnings=deduped_warnings,
            errors=deduped_errors,
        )
        return LegalParserExecutionResult(
            law_id=law_id,
            status=status,
            document=document,
            validation_summary=validation_summary,
            warnings=deduped_warnings,
            errors=deduped_errors,
            recognition_summary=recognition_summary,
            parsing_result=parsing_result,
        )


def _metadata_from_artifact(artifact: NormalizedLegalArtifact) -> LegalHierarchyMetadata:
    """Map normalized input metadata into the canonical hierarchy metadata."""
    return LegalHierarchyMetadata(
        law_name=artifact.law_name,
        source_url=artifact.source_url,
        source_domain=artifact.source_domain,
        source_type=artifact.source_type,
        raw_artifact_path=artifact.raw_artifact_path,
        article_heading_count=artifact.markers.article_heading_count,
        max_heading_article_number=artifact.markers.max_heading_article_number,
        has_heading_article_1=artifact.markers.has_heading_article_1,
        heading_sequence_score=artifact.markers.heading_sequence_score,
    )


def _recognition_summary(
    recognition_result: HeadingRecognitionResult,
) -> LegalParserRecognitionSummary:
    """Summarize recognizer output without changing recognition data."""
    counts_by_level: dict[str, int] = {}
    for heading in recognition_result.headings:
        counts_by_level[heading.level.value] = counts_by_level.get(heading.level.value, 0) + 1
    return LegalParserRecognitionSummary(
        certain_heading_count=len(recognition_result.headings),
        ambiguous_candidate_count=len(recognition_result.ambiguous_candidates),
        rejected_candidate_count=len(recognition_result.rejected_candidates),
        boundary_count=len(recognition_result.boundaries),
        segmented_unit_count=0,
        counts_by_level=counts_by_level,
    )


def _parsing_result(
    *,
    law_id: str,
    status: LegalParsingStatus,
    source_file: str,
    artifact: NormalizedLegalArtifact | None,
    document: LegalHierarchyDocument | None,
    warnings: list[StructuredParsingIssue],
    errors: list[StructuredParsingIssue],
) -> LegalParsingResult:
    """Build the canonical per-law parsing-result model."""
    counts_by_level = _counts_by_level(document)
    articles = _article_nodes(document)
    max_article_number = _max_article_number(articles)
    expected_article_count = (
        artifact.markers.article_heading_count
        if artifact is not None
        else document.metadata.article_heading_count
        if document is not None
        else 0
    )
    expected_max_article = (
        artifact.markers.max_heading_article_number
        if artifact is not None
        else document.metadata.max_heading_article_number
        if document is not None
        else 0
    )

    return LegalParsingResult(
        law_id=law_id,
        status=status,
        input_path=source_file,
        output_path=None,
        duration_seconds=0.0,
        node_count=len(document.nodes) if document is not None else 0,
        counts_by_level=counts_by_level,
        has_article_1=any(node.number == "1" for node in articles),
        max_article_number=max_article_number,
        expected_article_heading_count=expected_article_count,
        article_heading_count_matches=len(articles) == expected_article_count,
        expected_max_heading_article_number=expected_max_article,
        max_article_number_matches=max_article_number == expected_max_article,
        warnings=warnings,
        errors=errors,
    )


def _counts_by_level(document: LegalHierarchyDocument | None) -> dict[str, int]:
    """Count hierarchy nodes by level in deterministic document order."""
    if document is None:
        return {}
    counts: dict[str, int] = {}
    for node in document.nodes:
        counts[node.level.value] = counts.get(node.level.value, 0) + 1
    return counts


def _article_nodes(document: LegalHierarchyDocument | None) -> list[LegalNode]:
    """Return Article nodes from a document, or an empty list."""
    if document is None:
        return []
    return [node for node in document.nodes if node.level == LegalNodeLevel.ARTICLE]


def _max_article_number(articles: list[LegalNode]) -> int:
    """Return comparable maximum Article number using numeric prefixes."""
    return max(
        (
            prefix
            for prefix in (_article_number_prefix(article.number) for article in articles)
            if prefix
        ),
        default=0,
    )


def _article_number_prefix(number: str | None) -> int | None:
    """Return comparable numeric Article prefix, e.g. `217a` contributes `217`."""
    if number is None:
        return None
    digits = ""
    for character in number:
        if not character.isdigit():
            break
        digits += character
    return int(digits) if digits else None


def _deduplicate_issues(
    issues: list[StructuredParsingIssue],
) -> list[StructuredParsingIssue]:
    """Deduplicate issues by stable identity while preserving first-seen order."""
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
    """Build the parser warning/error deduplication key."""
    context = json.dumps(issue.context, ensure_ascii=False, sort_keys=True, default=str)
    return (
        issue.code.value,
        issue.node_id,
        issue.start_offset,
        issue.end_offset,
        context,
    )


def _exception_issue(
    *,
    code: ParsingIssueCode,
    message: str,
    law_id: str,
    exc: Exception,
    source_file: str,
) -> StructuredParsingIssue:
    """Convert an expected parser facade failure into a structured issue."""
    return StructuredParsingIssue(
        code=code,
        message=message,
        law_id=law_id,
        node_id=None,
        start_offset=None,
        end_offset=None,
        context={
            "source_file": source_file,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
    )


def _fallback_law_id(normalized_path: Path) -> str:
    """Derive a deterministic fallback law ID before input schema validation."""
    if normalized_path.parent.name:
        return normalized_path.parent.name
    if normalized_path.stem:
        return normalized_path.stem
    return "UNKNOWN"
