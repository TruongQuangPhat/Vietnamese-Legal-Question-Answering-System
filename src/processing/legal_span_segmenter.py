"""Deterministic span segmentation for recognized Vietnamese legal headings."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.processing.legal_heading_recognizer import (
    CandidateClassification,
    HeadingRecognitionResult,
    RecognitionBoundaryKind,
    RecognizedBoundary,
    RecognizedHeading,
)
from src.processing.legal_hierarchy_models import LegalNodeLevel

LEGAL_LEVEL_ORDER: dict[LegalNodeLevel, int] = {
    LegalNodeLevel.LAW: 0,
    LegalNodeLevel.PART: 1,
    LegalNodeLevel.CHAPTER: 2,
    LegalNodeLevel.SECTION: 3,
    LegalNodeLevel.ARTICLE: 4,
    LegalNodeLevel.CLAUSE: 5,
    LegalNodeLevel.POINT: 6,
}


class SegmentedLegalUnit(BaseModel):
    """A recognized legal heading with an exact parent-inclusive source span.

    Attributes:
        level: Legal hierarchy level.
        number: Legal number or label.
        title: Semantic title produced by the recognizer.
        heading_text: Exact heading text recognized in the source.
        heading_start_offset: Inclusive heading offset.
        heading_end_offset: Exclusive heading offset.
        start_offset: Inclusive legal-unit span offset.
        end_offset: Exclusive legal-unit span offset.
        text: Exact source slice for this legal unit.
        line_number: One-based source line number.
        footnote: Optional heading footnote marker.
        classification: Recognition classification, always `certain`.
        active_article_number: Article context from recognition.
        active_clause_number: Clause context from recognition.
        metadata: Small recognition metadata carried forward.

    Legal assumptions:
        This is an intermediate Step 5 representation only. It intentionally
        has no node ID, parent ID, children, collision suffix, or hierarchy path.
    """

    model_config = ConfigDict(extra="forbid")

    level: LegalNodeLevel = Field(...)
    number: str | None = Field(None)
    title: str | None = Field(None)
    heading_text: str = Field(..., min_length=1)
    heading_start_offset: int = Field(..., ge=0)
    heading_end_offset: int = Field(..., ge=0)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    text: str = Field(...)
    line_number: int = Field(..., ge=1)
    footnote: str | None = Field(None)
    classification: CandidateClassification = Field(default=CandidateClassification.CERTAIN)
    active_article_number: str | None = Field(None)
    active_clause_number: str | None = Field(None)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_segment_invariants(self) -> SegmentedLegalUnit:
        """Validate local span invariants that do not require source text."""
        if self.classification != CandidateClassification.CERTAIN:
            raise ValueError("segmented legal units must be certain candidates")
        if self.start_offset != self.heading_start_offset:
            raise ValueError("start_offset must equal heading_start_offset")
        if self.heading_end_offset <= self.heading_start_offset:
            raise ValueError("heading_end_offset must be greater than heading_start_offset")
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class SpanSegmentationResult(BaseModel):
    """Result of converting certain recognized headings into source spans."""

    model_config = ConfigDict(extra="forbid")

    units: list[SegmentedLegalUnit] = Field(default_factory=list)


class LegalSpanSegmenter:
    """Convert certain heading candidates into exact parent-inclusive spans.

    The segmenter consumes `HeadingRecognitionResult` output and does not repeat
    heading recognition. Ambiguous and rejected candidates are intentionally
    ignored for span boundaries so they remain inside the containing accepted
    legal unit when applicable.
    """

    _TRAILING_BOUNDARY_KINDS = {
        RecognitionBoundaryKind.SOURCE_NOTE,
        RecognitionBoundaryKind.APPENDIX,
    }

    def segment(
        self,
        normalized_text: str,
        recognition_result: HeadingRecognitionResult,
    ) -> SpanSegmentationResult:
        """Segment recognized legal headings into exact source slices.

        Args:
            normalized_text: The immutable authoritative normalized source text.
            recognition_result: Output from `LegalHeadingRecognizer`.

        Returns:
            Source-ordered certain legal units with parent-inclusive spans.

        Raises:
            ValueError: If recognized offsets do not match the original source.

        Legal assumptions:
            Only candidates classified as `certain` may become segmented legal
            units. Root Law construction and parent-child relationships are
            deferred to later Phase 5 steps.
        """
        headings = sorted(
            [
                heading
                for heading in recognition_result.headings
                if heading.classification == CandidateClassification.CERTAIN
            ],
            key=lambda heading: (heading.start_offset, heading.end_offset),
        )
        boundaries = sorted(
            recognition_result.boundaries,
            key=lambda boundary: (boundary.start_offset, boundary.end_offset),
        )

        units: list[SegmentedLegalUnit] = []
        for index, heading in enumerate(headings):
            end_offset = self._end_offset_for_heading(
                heading=heading,
                heading_index=index,
                headings=headings,
                boundaries=boundaries,
                document_length=len(normalized_text),
            )
            units.append(self._build_unit(normalized_text, heading, end_offset))

        return SpanSegmentationResult(units=units)

    def _end_offset_for_heading(
        self,
        *,
        heading: RecognizedHeading,
        heading_index: int,
        headings: list[RecognizedHeading],
        boundaries: list[RecognizedBoundary],
        document_length: int,
    ) -> int:
        """Find the first same-or-higher-level heading or trailing boundary."""
        natural_end = self._next_same_or_higher_heading_start(
            heading=heading,
            heading_index=heading_index,
            headings=headings,
            document_length=document_length,
        )
        boundary_end = self._first_applicable_boundary_start(
            heading=heading,
            headings=headings,
            boundaries=boundaries,
            natural_end=natural_end,
        )
        return min(natural_end, boundary_end)

    def _next_same_or_higher_heading_start(
        self,
        *,
        heading: RecognizedHeading,
        heading_index: int,
        headings: list[RecognizedHeading],
        document_length: int,
    ) -> int:
        """Return the next legal heading that closes the current unit."""
        current_order = LEGAL_LEVEL_ORDER[heading.level]
        for candidate in headings[heading_index + 1 :]:
            if candidate.start_offset <= heading.start_offset:
                continue
            if LEGAL_LEVEL_ORDER[candidate.level] <= current_order:
                return candidate.start_offset
        return document_length

    def _first_applicable_boundary_start(
        self,
        *,
        heading: RecognizedHeading,
        headings: list[RecognizedHeading],
        boundaries: list[RecognizedBoundary],
        natural_end: int,
    ) -> int:
        """Return the first exclusion boundary that safely closes a unit."""
        boundary_offsets: list[int] = []
        for boundary in boundaries:
            if not (heading.start_offset < boundary.start_offset < natural_end):
                continue

            if boundary.kind in self._TRAILING_BOUNDARY_KINDS:
                boundary_offsets.append(boundary.start_offset)
                continue

            if (
                boundary.kind == RecognitionBoundaryKind.SIGNATURE_FOOTER
                and self._is_trailing_boundary(
                    boundary,
                    headings,
                )
            ):
                boundary_offsets.append(boundary.start_offset)

        if not boundary_offsets:
            return natural_end
        return min(boundary_offsets)

    @staticmethod
    def _is_trailing_boundary(
        boundary: RecognizedBoundary,
        headings: list[RecognizedHeading],
    ) -> bool:
        """Treat signature/footer boundaries as span-ending only at document tail."""
        return not any(heading.start_offset > boundary.start_offset for heading in headings)

    def _build_unit(
        self,
        normalized_text: str,
        heading: RecognizedHeading,
        end_offset: int,
    ) -> SegmentedLegalUnit:
        """Build a segmented unit and verify exact source slicing."""
        if not (0 <= heading.start_offset < end_offset <= len(normalized_text)):
            raise ValueError("segmented unit offsets must be inside normalized_text")

        heading_text = normalized_text[heading.start_offset : heading.end_offset]
        if heading_text != heading.heading_text:
            raise ValueError("heading_text does not match normalized_text slice")

        unit_text = normalized_text[heading.start_offset : end_offset]
        return SegmentedLegalUnit(
            level=heading.level,
            number=heading.number,
            title=heading.title,
            heading_text=heading.heading_text,
            heading_start_offset=heading.start_offset,
            heading_end_offset=heading.end_offset,
            start_offset=heading.start_offset,
            end_offset=end_offset,
            text=unit_text,
            line_number=heading.line_number,
            footnote=heading.footnote,
            classification=heading.classification,
            active_article_number=heading.active_article_number,
            active_clause_number=heading.active_clause_number,
            metadata=heading.metadata,
        )
