"""Tests for the initial deterministic legal heading recognizer."""

from __future__ import annotations

from pathlib import Path

from src.processing.legal_heading_recognizer import CandidateClassification, LegalHeadingRecognizer
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


def test_titleless_article_headings_are_recognized_without_consuming_body() -> None:
    """Titleless Article headings such as Constitution Articles are accepted."""
    text = "\n".join(
        [
            "Điều 1.",
            "Nước Cộng hòa xã hội chủ nghĩa Việt Nam là một nước độc lập.",
            "Điều 2.",
            "1. Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam là nhà nước pháp quyền.",
            "Điều 120.",
            "1. Chủ tịch nước có quyền đề nghị làm Hiến pháp.",
        ]
    )

    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    articles = [heading for heading in result.headings if heading.level == LegalNodeLevel.ARTICLE]

    assert [article.number for article in articles] == ["1", "2", "120"]
    assert [article.title for article in articles] == [None, None, None]
    assert [article.heading_text for article in articles] == ["Điều 1.", "Điều 2.", "Điều 120."]
    assert all(article.title_source is None for article in articles)


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

    assert result.headings == []
    assert len(result.warnings) == 1
    assert result.warnings[0].code == ParsingIssueCode.SOURCE_NOTE_EXCLUDED
    assert result.warnings[0].start_offset == text.index("Điều 74")


def test_article_like_line_inside_quoted_source_note_is_not_promoted() -> None:
    """Article-like lines inside quoted source-law content stay excluded."""
    text = "\n".join(
        [
            "Điều 1. Phạm vi điều chỉnh",
            "Nội dung chính.",
            "Điều 3 và Điều 4 của Luật số 86/2025/QH15 sửa đổi, bổ sung một số điều của Bộ luật Hình sự, có hiệu lực kể từ ngày 01 tháng 7 năm 2025 quy định như sau:",
            "“Điều 3. Hiệu lực thi hành",
            "Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2025.",
            "Điều 4. Điều khoản chuyển tiếp",
            "1. Nội dung chuyển tiếp trong ghi chú nguồn.\".",
        ]
    )

    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    assert [heading.number for heading in result.headings] == ["1"]
    assert "Điều 4. Điều khoản chuyển tiếp" not in {
        heading.heading_text for heading in result.headings
    }
    assert result.warnings[0].code == ParsingIssueCode.SOURCE_NOTE_EXCLUDED


def test_unquoted_article_like_lines_inside_source_note_tail_are_not_promoted() -> None:
    """Unquoted Article-like amendment-law tail content remains excluded."""
    text = "\n".join(
        [
            "Điều 1. Nội dung chính",
            "Nội dung chính.",
            "Điều 10 của Luật số 01/2025/QH15 sửa đổi, bổ sung một số điều của Luật Kiểm thử, có hiệu lực kể từ ngày 01 tháng 7 năm 2025 quy định như sau:",
            "Điều 1. Nội dung trong ghi chú nguồn",
            "1. Khoản trong ghi chú nguồn",
            "Điều 2. Nội dung khác trong ghi chú nguồn",
        ]
    )

    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    articles = [heading for heading in result.headings if heading.level == LegalNodeLevel.ARTICLE]

    assert [article.heading_text for article in articles] == ["Điều 1. Nội dung chính"]
    assert result.warnings[0].code == ParsingIssueCode.SOURCE_NOTE_EXCLUDED


def test_quoted_source_note_with_inner_quote_does_not_promote_later_article() -> None:
    """Inner quoted text must not close a source-law tail before Article 4."""
    text = "\n".join(
        [
            "Điều 1. Nội dung chính",
            "Nội dung chính.",
            "Điều 3 và Điều 4 của Luật số 42/2019/QH14 sửa đổi, bổ sung một số điều của Luật Kiểm thử, có hiệu lực kể từ ngày 01 tháng 11 năm 2019 quy định như sau:",
            "“Điều 3. Hiệu lực thi hành",
            "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 11 năm 2019.",
            "“32a. Dịch vụ phụ trợ bao gồm tư vấn, đánh giá rủi ro”.",
            "Điều 4. Quy định chuyển tiếp",
            "1. Nội dung chuyển tiếp trong ghi chú nguồn.",
        ]
    )

    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    articles = [heading for heading in result.headings if heading.level == LegalNodeLevel.ARTICLE]

    assert [article.heading_text for article in articles] == ["Điều 1. Nội dung chính"]
    assert "Điều 4. Quy định chuyển tiếp" not in {
        heading.heading_text for heading in result.headings
    }
    assert result.warnings[0].code == ParsingIssueCode.SOURCE_NOTE_EXCLUDED


def test_exact_heading_offsets_and_source_text_immutability() -> None:
    """Heading offsets point into the unchanged source string."""
    text = _read_fixture("heading_patterns.txt")
    original = text[:]
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    article = result.headings[1]

    assert text == original
    assert text[article.start_offset : article.end_offset] == "Điều 1. Phạm vi điều chỉnh"
    assert article.title == "Phạm vi điều chỉnh"


def test_standard_and_footnoted_clauses_under_active_article() -> None:
    """Certain Clause candidates require active Article context."""
    text = _read_fixture("clause_point_candidates.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    clauses = [heading for heading in result.headings if heading.level == LegalNodeLevel.CLAUSE]

    assert [clause.number for clause in clauses] == ["1", "2", "1"]
    assert clauses[0].classification == CandidateClassification.CERTAIN
    assert clauses[0].active_article_number == "1"
    assert clauses[0].footnote is None
    assert clauses[1].number == "2"
    assert clauses[1].footnote == "3"
    assert clauses[1].active_article_number == "1"
    assert clauses[2].active_article_number == "2"


def test_numbered_line_before_first_article_is_rejected() -> None:
    """A numbered line before any Article is not a Clause node."""
    text = "1. Nội dung trước Điều\nĐiều 1. Phạm vi điều chỉnh\n"
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    assert [heading.level for heading in result.headings] == [LegalNodeLevel.ARTICLE]
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].classification == CandidateClassification.REJECTED
    assert result.rejected_candidates[0].metadata["reason"] == "missing_active_article"


def test_clause_context_resets_at_next_article() -> None:
    """A new Article resets active Clause before Point recognition."""
    text = _read_fixture("clause_point_candidates.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    rejected_points = [
        candidate
        for candidate in result.rejected_candidates
        if candidate.level == LegalNodeLevel.POINT
    ]
    accepted_points = [
        heading for heading in result.headings if heading.level == LegalNodeLevel.POINT
    ]

    assert rejected_points[0].heading_text == "a) Điểm trực tiếp dưới điều không hợp lệ"
    assert rejected_points[0].active_article_number == "2"
    assert rejected_points[0].active_clause_number is None
    assert accepted_points[-1].heading_text == "a) Điểm thuộc khoản mới"
    assert accepted_points[-1].active_article_number == "2"
    assert accepted_points[-1].active_clause_number == "1"


def test_malformed_numeric_clause_candidates_are_ambiguous_not_certain() -> None:
    """Malformed `N.text` and `N text` lines are preserved as ambiguous only."""
    text = _read_fixture("clause_point_candidates.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    assert [candidate.heading_text for candidate in result.ambiguous_candidates] == [
        "1.Nội dung thiếu khoảng trắng",
        "2 Nội dung thiếu dấu chấm",
    ]
    assert all(
        candidate.classification == CandidateClassification.AMBIGUOUS
        for candidate in result.ambiguous_candidates
    )
    assert all(
        candidate.heading_text not in {heading.heading_text for heading in result.headings}
        for candidate in result.ambiguous_candidates
    )
    assert [
        warning.code
        for warning in result.warnings
        if warning.code == ParsingIssueCode.AMBIGUOUS_CLAUSE_CANDIDATE
    ] == [
        ParsingIssueCode.AMBIGUOUS_CLAUSE_CANDIDATE,
        ParsingIssueCode.AMBIGUOUS_CLAUSE_CANDIDATE,
    ]


def test_unrelated_numbered_date_is_rejected_not_promoted() -> None:
    """Date-like numbered lines inside an Article are not Clause candidates."""
    text = _read_fixture("clause_point_candidates.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    rejected = [
        candidate
        for candidate in result.rejected_candidates
        if candidate.heading_text == "01 tháng 01 năm 2026 không phải khoản"
    ]

    assert len(rejected) == 1
    assert rejected[0].metadata["reason"] == "date_like_numbered_line"
    assert rejected[0].heading_text not in {heading.heading_text for heading in result.headings}


def test_clause_candidate_inside_source_note_region_is_rejected() -> None:
    """Source-note regions suppress Clause recognition until the next Article."""
    text = "\n".join(
        [
            "Điều 74 và Điều 75 của Luật Giá số 16/2023/QH15 quy định như sau:",
            "1. Khoản trong ghi chú nguồn",
            "Điều 1. Phạm vi điều chỉnh",
            "1. Khoản chính",
        ]
    )
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    clauses = [heading for heading in result.headings if heading.level == LegalNodeLevel.CLAUSE]
    rejected_clauses = [
        candidate
        for candidate in result.rejected_candidates
        if candidate.level == LegalNodeLevel.CLAUSE
    ]

    assert [clause.heading_text for clause in clauses] == ["1. Khoản chính"]
    assert rejected_clauses[0].heading_text == "1. Khoản trong ghi chú nguồn"
    assert rejected_clauses[0].metadata["reason"] == "source_note_exclusion"


def test_clause_candidate_inside_appendix_or_table_region_is_rejected() -> None:
    """Appendix/table regions suppress Clause recognition."""
    text = "\n".join(
        [
            "Điều 1. Phạm vi điều chỉnh",
            "PHỤ LỤC",
            "1. Dòng phụ lục",
            "STT",
            "2. Dòng bảng",
        ]
    )
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    assert [heading.level for heading in result.headings] == [LegalNodeLevel.ARTICLE]
    assert [candidate.metadata["reason"] for candidate in result.rejected_candidates] == [
        "appendix_exclusion",
        "appendix_exclusion",
    ]


def test_standard_vietnamese_and_footnoted_points_under_active_clause() -> None:
    """Certain Point candidates require the current active Clause."""
    text = _read_fixture("clause_point_candidates.txt")
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    points = [heading for heading in result.headings if heading.level == LegalNodeLevel.POINT]

    assert [point.number for point in points[:3]] == ["a", "đ", "c"]
    assert points[0].classification == CandidateClassification.CERTAIN
    assert points[0].active_article_number == "1"
    assert points[0].active_clause_number == "2"
    assert points[1].number == "đ"
    assert points[2].footnote == "4"


def test_point_outside_clause_and_direct_article_to_point_are_rejected_or_flagged() -> None:
    """Point-like lines outside active Clause are not accepted."""
    text = "Điều 1. Phạm vi điều chỉnh\na) Điểm trực tiếp dưới Điều\n"
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")

    assert [heading.level for heading in result.headings] == [LegalNodeLevel.ARTICLE]
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].level == LegalNodeLevel.POINT
    assert result.rejected_candidates[0].classification == CandidateClassification.REJECTED
    assert result.rejected_candidates[0].metadata["reason"] == "missing_active_clause"
    assert result.warnings[0].code == ParsingIssueCode.POINT_LIKE_LINE_OUTSIDE_CLAUSE


def test_exact_clause_point_offsets_and_source_text_immutability() -> None:
    """Clause and Point candidate offsets refer to the original source string."""
    text = _read_fixture("clause_point_candidates.txt")
    original = text[:]
    result = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    clause = next(
        heading
        for heading in result.headings
        if heading.heading_text == "2.[3] Khoản chắc chắn có chú thích"
    )
    point = next(
        heading
        for heading in result.headings
        if heading.heading_text == "đ) Điểm đ thuộc khoản 2"
    )

    assert text == original
    assert text[clause.start_offset : clause.end_offset] == clause.heading_text
    assert text[point.start_offset : point.end_offset] == point.heading_text
