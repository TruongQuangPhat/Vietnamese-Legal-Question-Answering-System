"""Initial line-anchored recognizer for Vietnamese legal hierarchy headings."""

from __future__ import annotations

import re
from dataclasses import dataclass

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

    Legal assumptions:
        This recognizer only finds deterministic heading candidates. It does
        not build spans, assign parents, validate trees, or parse Clauses and
        Points in this first implementation slice.
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


class HeadingRecognitionResult(BaseModel):
    """Headings and structured warnings produced by a recognizer run."""

    model_config = ConfigDict(extra="forbid")

    headings: list[RecognizedHeading] = Field(default_factory=list)
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
    _CLAUSE_GUARD_RE = re.compile(r"^\s*\d+\.(?:\[\d+\])?\s+\S")
    _POINT_GUARD_RE = re.compile(r"^\s*[a-zđ]\)(?:\[\d+\])?\s+\S")
    _SOURCE_NOTE_RE = re.compile(
        r"^\s*Điều\s+\d+[a-z]?(?:\s+và\s+Điều\s+\d+[a-z]?)*"
        r"\s+của\s+Luật\b.*quy định như sau:\s*$",
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
        warnings: list[StructuredParsingIssue] = []

        for index, line in enumerate(lines):
            if self._is_blank(line.text):
                continue

            if self._is_source_note_intro(line.text):
                warnings.append(self._source_note_warning(line, law_id=law_id))
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
                continue

            section = self._SECTION_RE.match(line.text)
            if section:
                headings.append(self._build_same_line_heading(line, section, LegalNodeLevel.SECTION))
                continue

            article = self._ARTICLE_RE.match(line.text)
            if article:
                headings.append(self._build_same_line_heading(line, article, LegalNodeLevel.ARTICLE))

        return HeadingRecognitionResult(headings=headings, warnings=warnings)

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
            or self._CLAUSE_GUARD_RE.match(line_text)
            or self._POINT_GUARD_RE.match(line_text)
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

    @staticmethod
    def _is_blank(line_text: str) -> bool:
        """Return whether a source line has no visible text."""
        return line_text.strip() == ""

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
