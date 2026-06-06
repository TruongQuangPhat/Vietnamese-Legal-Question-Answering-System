"""Initial line-anchored recognizer for Vietnamese legal hierarchy headings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.processing.legal_hierarchy_models import (
    LegalNodeLevel,
    ParsingIssueCode,
    StructuredParsingIssue,
)


@dataclass(frozen=True)
class _LineInfo:
    """Internal source line with exact offsets into normalized_text."""

    text: str
    start_offset: int
    end_offset: int
    line_number: int


@dataclass
class _RecognitionState:
    """Recognition-only scan state for Clause and Point context."""

    active_article_number: str | None = None
    active_clause_number: str | None = None
    source_note_exclusion: bool = False
    source_note_quote_open: bool = False
    appendix_exclusion: bool = False
    table_exclusion: bool = False


class CandidateClassification(StrEnum):
    """Recognition classification for hierarchy candidates."""

    CERTAIN = "certain"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


class RecognitionBoundaryKind(StrEnum):
    """Boundary hints detected during recognition for later segmentation."""

    SOURCE_NOTE = "source_note"
    APPENDIX = "appendix"
    TABLE = "table"
    SIGNATURE_FOOTER = "signature_footer"


class RecognizedBoundary(BaseModel):
    """Structured non-heading boundary detected during recognition.

    Attributes:
        kind: Boundary category.
        start_offset: Inclusive offset of the boundary line text.
        end_offset: Exclusive offset of the boundary line text.
        line_number: One-based source line number.
        text: Exact detected boundary-line text.
        metadata: Small boundary-specific context.

    Legal assumptions:
        Boundaries are hints for span segmentation. They are not hierarchy
        nodes, and the recognizer does not decide parent-child relationships.
    """

    model_config = ConfigDict(extra="forbid")

    kind: RecognitionBoundaryKind = Field(...)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    line_number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)


class RecognizedHeading(BaseModel):
    """Recognized Part, Chapter, Section, or Article heading.

    Attributes:
        level: Legal hierarchy level identified for this heading.
        number: Legal heading number or label.
        title: Semantic title text, excluding the legal marker.
        heading_text: Exact heading-line text matched from the source string.
        start_offset: Inclusive offset of `heading_text`.
        end_offset: Exclusive offset of `heading_text`.
        line_number: One-based line number in the source string.
        title_start_offset: Optional inclusive semantic-title offset.
        title_end_offset: Optional exclusive semantic-title offset.
        title_source: `same_line`, `next_line`, or null.
        footnote: Optional numeric footnote marker from Article headings.
        classification: Candidate certainty classification.
        active_article_number: Article context observed during recognition.
        active_clause_number: Clause context observed during recognition.
        metadata: Small recognition-only context, such as rejection reason.

    Legal assumptions:
        This recognizer only finds deterministic heading candidates. It does
        not build spans, assign parents, or validate trees.
    """

    model_config = ConfigDict(extra="forbid")

    level: LegalNodeLevel = Field(...)
    number: str | None = Field(None)
    title: str | None = Field(None)
    heading_text: str = Field(..., min_length=1)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    line_number: int = Field(..., ge=1)
    title_start_offset: int | None = Field(None, ge=0)
    title_end_offset: int | None = Field(None, ge=0)
    title_source: str | None = Field(None)
    footnote: str | None = Field(None)
    classification: CandidateClassification = Field(default=CandidateClassification.CERTAIN)
    active_article_number: str | None = Field(None)
    active_clause_number: str | None = Field(None)
    metadata: dict[str, str] = Field(default_factory=dict)


class HeadingRecognitionResult(BaseModel):
    """Headings and structured warnings produced by a recognizer run."""

    model_config = ConfigDict(extra="forbid")

    headings: list[RecognizedHeading] = Field(default_factory=list)
    ambiguous_candidates: list[RecognizedHeading] = Field(default_factory=list)
    rejected_candidates: list[RecognizedHeading] = Field(default_factory=list)
    boundaries: list[RecognizedBoundary] = Field(default_factory=list)
    warnings: list[StructuredParsingIssue] = Field(default_factory=list)


class LegalHeadingRecognizer:
    """Recognize observed Vietnamese legal heading patterns without mutation.

    The recognizer is intentionally narrow for the first Phase 5 slice. It
    supports the approved Part, Chapter, Section, and Article baseline patterns
    while rejecting inline cross-references and emitting source-note exclusion
    hints for future segmentation.
    """

    _PART_RE = re.compile(
        r"^\s*(?P<heading>Phần\s+(?P<number>thứ\s+\S+))\s*$",
        re.IGNORECASE,
    )
    _CHAPTER_RE = re.compile(
        r"^\s*(?P<heading>Chương\s+(?P<number>[IVXLC]+)\.?"
        r"(?:\[(?P<footnote>\d+)\])?(?:\s+\([^)]+\))?)\s*$",
        re.IGNORECASE,
    )
    _SECTION_RE = re.compile(
        r"^\s*(?P<heading>Mục\s+(?P<number>\d+)\.\s+(?P<title>.+?))\s*$",
        re.IGNORECASE,
    )
    _ARTICLE_RE = re.compile(
        r"^\s*(?P<heading>Điều\s+(?P<number>\d+[a-z]?)\."
        r"(?:\[(?P<footnote>\d+)\])?\s+(?P<title>.+?))\s*$",
    )
    _CLAUSE_RE = re.compile(
        r"^\s*(?P<heading>(?P<number>\d+)\.(?:\[(?P<footnote>\d+)\])?\s+\S.*)\s*$"
    )
    _MALFORMED_DOT_CLAUSE_RE = re.compile(
        r"^\s*(?P<heading>(?P<number>\d+)\.(?!\[\d+\]\s|\s)\S.*)\s*$"
    )
    _MALFORMED_SPACE_CLAUSE_RE = re.compile(
        r"^\s*(?P<heading>(?P<number>\d+)\s+\S.*)\s*$"
    )
    _POINT_RE = re.compile(
        r"^\s*(?P<heading>(?P<number>[a-zđ])\)(?:\[(?P<footnote>\d+)\])?\s+\S.*)\s*$"
    )
    _SOURCE_NOTE_RE = re.compile(
        r"^\s*Điều\s+\d+[a-z]?(?:\s+và\s+Điều\s+\d+[a-z]?)*"
        r"\s+của\s+Luật\b.*quy định như sau:\s*$",
        re.IGNORECASE,
    )
    _APPENDIX_RE = re.compile(r"^\s*(PHỤ LỤC|Phụ lục)\b", re.IGNORECASE)
    _TABLE_RE = re.compile(r"^\s*STT\b", re.IGNORECASE)
    _DATE_LIKE_NUMBERED_RE = re.compile(
        r"^\s*\d{1,2}(?:/\d{1,2}/\d{4}|\s+tháng\s+\d{1,2}\s+năm\s+\d{4})\b",
        re.IGNORECASE,
    )
    _SIGNATURE_OR_FOOTER_RE = re.compile(
        r"^\s*(Nơi nhận|CHỦ TỊCH|TM\.|KT\.|Văn bản liên quan)\b",
        re.IGNORECASE,
    )

    def recognize(self, normalized_text: str, *, law_id: str = "") -> HeadingRecognitionResult:
        """Recognize initial legal headings in an immutable source string.

        Args:
            normalized_text: Exact `normalized_json["normalized_text"]` source.
            law_id: Optional law identifier used in structured warnings.

        Returns:
            Recognized headings plus source-note exclusion warnings.

        Legal assumptions:
            Offsets are always calculated against `normalized_text`. The method
            may strip copied line candidates for matching but never changes the
            source string used for offsets.
        """
        lines = list(_iter_lines(normalized_text))
        headings: list[RecognizedHeading] = []
        ambiguous_candidates: list[RecognizedHeading] = []
        rejected_candidates: list[RecognizedHeading] = []
        boundaries: list[RecognizedBoundary] = []
        warnings: list[StructuredParsingIssue] = []
        state = _RecognitionState()

        for index, line in enumerate(lines):
            if self._is_blank(line.text):
                continue

            if self._is_source_note_intro(line.text):
                boundaries.append(self._build_boundary(line, RecognitionBoundaryKind.SOURCE_NOTE))
                warnings.append(self._source_note_warning(line, law_id=law_id))
                state.source_note_exclusion = True
                state.source_note_quote_open = False
                state.active_clause_number = None
                continue

            if self._is_appendix_heading(line.text):
                boundaries.append(self._build_boundary(line, RecognitionBoundaryKind.APPENDIX))
                state.appendix_exclusion = True
                state.active_clause_number = None
                continue

            if self._is_table_heading(line.text):
                boundaries.append(self._build_boundary(line, RecognitionBoundaryKind.TABLE))
                state.table_exclusion = True
                state.active_clause_number = None
                continue

            if self._is_signature_or_footer_boundary(line.text):
                boundaries.append(
                    self._build_boundary(line, RecognitionBoundaryKind.SIGNATURE_FOOTER)
                )
                state.active_clause_number = None
                continue

            if self._is_quoted_source_note_line(line.text, state):
                self._close_source_note_quote_if_needed(line.text, state)
                continue

            part = self._PART_RE.match(line.text)
            if part:
                headings.append(
                    self._build_structural_heading(
                        line=line,
                        match=part,
                        level=LegalNodeLevel.PART,
                        title_info=self._next_line_title(lines, index),
                    )
                )
                state.active_article_number = None
                state.active_clause_number = None
                continue

            chapter = self._CHAPTER_RE.match(line.text)
            if chapter:
                headings.append(
                    self._build_structural_heading(
                        line=line,
                        match=chapter,
                        level=LegalNodeLevel.CHAPTER,
                        title_info=self._next_line_title(lines, index),
                    )
                )
                state.active_article_number = None
                state.active_clause_number = None
                continue

            section = self._SECTION_RE.match(line.text)
            if section:
                headings.append(self._build_same_line_heading(line, section, LegalNodeLevel.SECTION))
                state.active_article_number = None
                state.active_clause_number = None
                continue

            article = self._ARTICLE_RE.match(line.text)
            if article and not state.appendix_exclusion and not state.table_exclusion:
                article_heading = self._build_same_line_heading(
                    line,
                    article,
                    LegalNodeLevel.ARTICLE,
                )
                headings.append(article_heading)
                state.active_article_number = article_heading.number
                state.active_clause_number = None
                state.source_note_exclusion = False
                continue

            point = self._POINT_RE.match(line.text)
            if point:
                candidate = self._build_contextual_heading(
                    line=line,
                    match=point,
                    level=LegalNodeLevel.POINT,
                    state=state,
                )
                if self._is_excluded(state):
                    rejected_candidates.append(
                        candidate.model_copy(
                            update={
                                "classification": CandidateClassification.REJECTED,
                                "metadata": {"reason": self._exclusion_reason(state)},
                            }
                        )
                    )
                    continue
                if state.active_clause_number is None:
                    rejected = candidate.model_copy(
                        update={
                            "classification": CandidateClassification.REJECTED,
                            "metadata": {"reason": "missing_active_clause"},
                        }
                    )
                    rejected_candidates.append(rejected)
                    warnings.append(self._point_outside_clause_warning(rejected, law_id=law_id))
                    continue
                headings.append(candidate)
                continue

            clause = self._CLAUSE_RE.match(line.text)
            if clause:
                candidate = self._build_contextual_heading(
                    line=line,
                    match=clause,
                    level=LegalNodeLevel.CLAUSE,
                    state=state,
                )
                rejected = self._reject_clause_candidate_if_needed(
                    candidate=candidate,
                    state=state,
                    date_like=self._is_date_like_numbered_line(line.text),
                )
                if rejected is not None:
                    rejected_candidates.append(rejected)
                    continue
                headings.append(candidate)
                state.active_clause_number = candidate.number
                continue

            ambiguous_clause = self._MALFORMED_DOT_CLAUSE_RE.match(
                line.text
            ) or self._MALFORMED_SPACE_CLAUSE_RE.match(line.text)
            if ambiguous_clause:
                candidate = self._build_contextual_heading(
                    line=line,
                    match=ambiguous_clause,
                    level=LegalNodeLevel.CLAUSE,
                    state=state,
                )
                rejected = self._reject_clause_candidate_if_needed(
                    candidate=candidate,
                    state=state,
                    date_like=self._is_date_like_numbered_line(line.text),
                )
                if rejected is not None:
                    rejected_candidates.append(rejected)
                    continue
                ambiguous = candidate.model_copy(
                    update={
                        "classification": CandidateClassification.AMBIGUOUS,
                        "metadata": {"reason": "malformed_numbered_clause_candidate"},
                    }
                )
                ambiguous_candidates.append(ambiguous)
                warnings.append(self._ambiguous_clause_warning(ambiguous, law_id=law_id))

        return HeadingRecognitionResult(
            headings=headings,
            ambiguous_candidates=ambiguous_candidates,
            rejected_candidates=rejected_candidates,
            boundaries=boundaries,
            warnings=warnings,
        )

    def _build_structural_heading(
        self,
        *,
        line: _LineInfo,
        match: re.Match[str],
        level: LegalNodeLevel,
        title_info: tuple[str, int, int] | None,
    ) -> RecognizedHeading:
        """Build a Part or Chapter heading with optional next-line title."""
        title: str | None = None
        title_start: int | None = None
        title_end: int | None = None
        if title_info is not None:
            title, title_start, title_end = title_info

        heading_start = line.start_offset + match.start("heading")
        heading_end = line.start_offset + match.end("heading")
        return RecognizedHeading(
            level=level,
            number=match.group("number"),
            title=title,
            heading_text=line.text[match.start("heading") : match.end("heading")],
            start_offset=heading_start,
            end_offset=heading_end,
            line_number=line.line_number,
            title_start_offset=title_start,
            title_end_offset=title_end,
            title_source="next_line" if title_info is not None else None,
            footnote=match.groupdict().get("footnote"),
        )

    def _build_same_line_heading(
        self,
        line: _LineInfo,
        match: re.Match[str],
        level: LegalNodeLevel,
    ) -> RecognizedHeading:
        """Build a Section or Article heading with a same-line semantic title."""
        heading_start = line.start_offset + match.start("heading")
        heading_end = line.start_offset + match.end("heading")
        title_start = line.start_offset + match.start("title")
        title_end = line.start_offset + match.end("title")
        return RecognizedHeading(
            level=level,
            number=match.group("number"),
            title=match.group("title").strip(),
            heading_text=line.text[match.start("heading") : match.end("heading")],
            start_offset=heading_start,
            end_offset=heading_end,
            line_number=line.line_number,
            title_start_offset=title_start,
            title_end_offset=title_end,
            title_source="same_line",
            footnote=match.groupdict().get("footnote"),
        )

    def _build_contextual_heading(
        self,
        *,
        line: _LineInfo,
        match: re.Match[str],
        level: LegalNodeLevel,
        state: _RecognitionState,
    ) -> RecognizedHeading:
        """Build a Clause or Point candidate with recognition-only context."""
        heading_start = line.start_offset + match.start("heading")
        heading_end = line.start_offset + match.end("heading")
        return RecognizedHeading(
            level=level,
            number=match.group("number"),
            title=None,
            heading_text=line.text[match.start("heading") : match.end("heading")],
            start_offset=heading_start,
            end_offset=heading_end,
            line_number=line.line_number,
            title_start_offset=None,
            title_end_offset=None,
            title_source=None,
            footnote=match.groupdict().get("footnote"),
            classification=CandidateClassification.CERTAIN,
            active_article_number=state.active_article_number,
            active_clause_number=state.active_clause_number,
        )

    def _reject_clause_candidate_if_needed(
        self,
        *,
        candidate: RecognizedHeading,
        state: _RecognitionState,
        date_like: bool,
    ) -> RecognizedHeading | None:
        """Return a rejected Clause candidate if current state disallows it."""
        reason: str | None = None
        if self._is_excluded(state):
            reason = self._exclusion_reason(state)
        elif date_like:
            reason = "date_like_numbered_line"
        elif state.active_article_number is None:
            reason = "missing_active_article"

        if reason is None:
            return None

        return candidate.model_copy(
            update={
                "classification": CandidateClassification.REJECTED,
                "metadata": {"reason": reason},
            }
        )

    def _next_line_title(
        self,
        lines: list[_LineInfo],
        current_index: int,
    ) -> tuple[str, int, int] | None:
        """Return the next non-empty title-like line, if strict guards accept it."""
        for candidate in lines[current_index + 1 :]:
            if self._is_blank(candidate.text):
                continue
            if not self._is_title_like(candidate.text):
                return None
            start, end = _stripped_offsets(candidate)
            return candidate.text[start - candidate.start_offset : end - candidate.start_offset], start, end
        return None

    def _is_title_like(self, line_text: str) -> bool:
        """Apply strict guards for Part/Chapter next-line title association."""
        candidate = line_text.strip()
        if not candidate:
            return False
        if len(candidate) > 150:
            return False
        if candidate.endswith((".", ";", ",", ":")):
            return False
        if self._is_source_note_intro(line_text) or self._SIGNATURE_OR_FOOTER_RE.match(line_text):
            return False
        if (
            self._PART_RE.match(line_text)
            or self._CHAPTER_RE.match(line_text)
            or self._SECTION_RE.match(line_text)
            or self._ARTICLE_RE.match(line_text)
            or self._CLAUSE_RE.match(line_text)
            or self._MALFORMED_DOT_CLAUSE_RE.match(line_text)
            or self._MALFORMED_SPACE_CLAUSE_RE.match(line_text)
            or self._POINT_RE.match(line_text)
        ):
            return False

        letters = [char for char in candidate if char.isalpha()]
        if not letters:
            return False

        uppercase_letters = [
            char for char in letters if char.upper() == char and char.lower() != char
        ]
        return len(uppercase_letters) / len(letters) >= 0.75

    def _is_source_note_intro(self, line_text: str) -> bool:
        """Detect source-law note introductions that resemble legal headings."""
        return self._SOURCE_NOTE_RE.match(line_text) is not None

    def _is_appendix_heading(self, line_text: str) -> bool:
        """Detect appendix headings that start non-hierarchy regions."""
        return self._APPENDIX_RE.match(line_text) is not None

    def _is_table_heading(self, line_text: str) -> bool:
        """Detect table headings that make numeric rows unsafe as Clauses."""
        return self._TABLE_RE.match(line_text) is not None

    def _is_signature_or_footer_boundary(self, line_text: str) -> bool:
        """Detect signature/footer lines as trailing-boundary hints."""
        return self._SIGNATURE_OR_FOOTER_RE.match(line_text) is not None

    def _is_date_like_numbered_line(self, line_text: str) -> bool:
        """Return whether a numbered line is a date, not a Clause."""
        return self._DATE_LIKE_NUMBERED_RE.match(line_text) is not None

    @staticmethod
    def _is_excluded(state: _RecognitionState) -> bool:
        """Return whether Clause/Point recognition is blocked by an excluded region."""
        return state.source_note_exclusion or state.appendix_exclusion or state.table_exclusion

    @staticmethod
    def _exclusion_reason(state: _RecognitionState) -> str:
        """Return the active exclusion reason for rejected candidates."""
        if state.source_note_exclusion:
            return "source_note_exclusion"
        if state.appendix_exclusion:
            return "appendix_exclusion"
        return "table_exclusion"

    @staticmethod
    def _is_blank(line_text: str) -> bool:
        """Return whether a source line has no visible text."""
        return line_text.strip() == ""

    def _is_quoted_source_note_line(
        self,
        line_text: str,
        state: _RecognitionState,
    ) -> bool:
        """Return whether the line belongs to a quoted source-law note block."""
        if not state.source_note_exclusion:
            return False
        if self._opens_source_note_quote(line_text):
            state.source_note_quote_open = True
        return state.source_note_quote_open

    @staticmethod
    def _opens_source_note_quote(line_text: str) -> bool:
        """Return whether a source-note content line opens a quote block."""
        return line_text.strip().startswith(("“", '"'))

    @staticmethod
    def _close_source_note_quote_if_needed(
        line_text: str,
        state: _RecognitionState,
    ) -> None:
        """Close quoted source-note state when a line terminates the quote."""
        stripped = line_text.strip()
        if state.source_note_quote_open and re.search(r'[”"]\s*\.?\s*$', stripped):
            state.source_note_quote_open = False

    @staticmethod
    def _source_note_warning(line: _LineInfo, *, law_id: str) -> StructuredParsingIssue:
        """Build a source-note exclusion hint for later segmentation."""
        start, end = _stripped_offsets(line)
        return StructuredParsingIssue(
            code=ParsingIssueCode.SOURCE_NOTE_EXCLUDED,
            message="Source-law note introduction excluded from hierarchy recognition.",
            law_id=law_id,
            node_id=None,
            start_offset=start,
            end_offset=end,
            context={"line_number": line.line_number, "line_text": line.text.strip()},
        )

    @staticmethod
    def _build_boundary(line: _LineInfo, kind: RecognitionBoundaryKind) -> RecognizedBoundary:
        """Build a structured boundary record from a detected source line."""
        start, end = _stripped_offsets(line)
        return RecognizedBoundary(
            kind=kind,
            start_offset=start,
            end_offset=end,
            line_number=line.line_number,
            text=line.text[start - line.start_offset : end - line.start_offset],
            metadata={},
        )

    @staticmethod
    def _ambiguous_clause_warning(
        candidate: RecognizedHeading,
        *,
        law_id: str,
    ) -> StructuredParsingIssue:
        """Build a warning for a malformed numbered Clause candidate."""
        return StructuredParsingIssue(
            code=ParsingIssueCode.AMBIGUOUS_CLAUSE_CANDIDATE,
            message="Malformed numbered line is an ambiguous Clause candidate.",
            law_id=law_id,
            node_id=None,
            start_offset=candidate.start_offset,
            end_offset=candidate.end_offset,
            context={
                "line_number": candidate.line_number,
                "line_text": candidate.heading_text,
                "classification": candidate.classification.value,
                "candidate_level": candidate.level.value,
            },
        )

    @staticmethod
    def _point_outside_clause_warning(
        candidate: RecognizedHeading,
        *,
        law_id: str,
    ) -> StructuredParsingIssue:
        """Build a warning for a point-like line outside active Clause context."""
        return StructuredParsingIssue(
            code=ParsingIssueCode.POINT_LIKE_LINE_OUTSIDE_CLAUSE,
            message="Point-like line was found outside an active Clause.",
            law_id=law_id,
            node_id=None,
            start_offset=candidate.start_offset,
            end_offset=candidate.end_offset,
            context={
                "line_number": candidate.line_number,
                "line_text": candidate.heading_text,
                "classification": candidate.classification.value,
                "candidate_level": candidate.level.value,
                "reason": candidate.metadata.get("reason", "missing_active_clause"),
            },
        )


def _iter_lines(text: str) -> list[_LineInfo]:
    """Yield source lines while preserving exact character offsets."""
    lines: list[_LineInfo] = []
    offset = 0
    for line_number, line_with_break in enumerate(text.splitlines(keepends=True), start=1):
        line_text = line_with_break.rstrip("\r\n")
        line_end = offset + len(line_text)
        lines.append(
            _LineInfo(
                text=line_text,
                start_offset=offset,
                end_offset=line_end,
                line_number=line_number,
            )
        )
        offset += len(line_with_break)
    return lines


def _stripped_offsets(line: _LineInfo) -> tuple[int, int]:
    """Return absolute offsets for a source line after trimming edge whitespace."""
    leading = len(line.text) - len(line.text.lstrip())
    trailing = len(line.text.rstrip())
    return line.start_offset + leading, line.start_offset + trailing
