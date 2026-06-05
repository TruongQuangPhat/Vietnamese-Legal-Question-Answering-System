"""Tests for the initial deterministic legal heading recognizer."""

from __future__ import annotations

from pathlib import Path

from src.processing.legal_heading_recognizer import LegalHeadingRecognizer
from src.processing.legal_hierarchy_models import LegalNodeLevel, ParsingIssueCode

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "legal_hierarchy"


def _read_fixture(name: str) -> str:
    """Load a committed synthetic heading fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_part_thu_nhat_and_chapter_next_line_titles() -> None:
    """Recognize Part and Chapter headings with strict next-line titles."""
    text = _read_fixture("part_chapter_titles.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    part = result.headings[0]
    chapter = result.headings[1]

    assert part.level == LegalNodeLevel.PART
    assert part.number == "thứ nhất"
    assert part.title == "QUY ĐỊNH CHUNG"
    assert part.heading_text == "Phần thứ nhất"

    assert chapter.level == LegalNodeLevel.CHAPTER
    assert chapter.number == "I"
    assert chapter.title == "NHỮNG QUY ĐỊNH CHUNG"


def test_chapter_title_does_not_consume_following_article() -> None:
    """A following Article heading must not become a Chapter title."""
    text = "Chương II\nĐiều 2. Điều khoản chuyển tiếp\n"
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    chapter, article = result.headings

    assert chapter.level == LegalNodeLevel.CHAPTER
    assert chapter.title is None
    assert article.level == LegalNodeLevel.ARTICLE
    assert article.title == "Điều khoản chuyển tiếp"


def test_section_same_line_title_and_article_headings() -> None:
    """Recognize Section and Article same-line semantic titles."""
    text = _read_fixture("heading_patterns.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    section, article, suffix_article, footnote_article = result.headings

    assert section.level == LegalNodeLevel.SECTION
    assert section.number == "1"
    assert section.title == "NĂNG LỰC PHÁP LUẬT DÂN SỰ"

    assert article.level == LegalNodeLevel.ARTICLE
    assert article.number == "1"
    assert article.title == "Phạm vi điều chỉnh"

    assert suffix_article.number == "217a"
    assert suffix_article.title == "Áp dụng quy định chuyển tiếp"

    assert footnote_article.number == "4"
    assert footnote_article.footnote == "1"
    assert footnote_article.title == "Giải thích từ ngữ"


def test_cross_reference_is_rejected() -> None:
    """Inline legal references are not line-anchored Article headings."""
    text = "Theo Điều 3 của Luật này thì nội dung này chỉ là tham chiếu.\n"
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    assert result.headings == []
    assert result.warnings == []


def test_source_law_note_introduction_returns_exclusion_hint() -> None:
    """Source-law note introductions are excluded rather than parsed as Articles."""
    text = _read_fixture("source_note_tail.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    assert [heading.number for heading in result.headings] == ["1"]
    assert len(result.warnings) == 1
    assert result.warnings[0].code == ParsingIssueCode.SOURCE_NOTE_EXCLUDED
    assert result.warnings[0].start_offset == text.index("Điều 74")


def test_exact_heading_offsets_and_source_text_immutability() -> None:
    """Heading offsets point into the unchanged source string."""
    text = _read_fixture("heading_patterns.txt")
    original = text[:]
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    article = result.headings[1]

    assert text == original
    assert text[article.start_offset : article.end_offset] == "Điều 1. Phạm vi điều chỉnh"
    assert article.title == "Phạm vi điều chỉnh"
