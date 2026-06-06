"""Tests for deterministic Phase 5 span segmentation."""

from __future__ import annotations

from pathlib import Path

from src.processing.legal_heading_recognizer import (
    CandidateClassification,
    LegalHeadingRecognizer,
)
from src.processing.legal_hierarchy_models import LegalNodeLevel
from src.processing.legal_span_segmenter import LegalSpanSegmenter, SegmentedLegalUnit

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "legal_hierarchy"


def _read_fixture(name: str) -> str:
    """Load a committed synthetic span fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _segment_text(text: str) -> list[SegmentedLegalUnit]:
    """Recognize and segment fixture text using the public Step 5 API."""
    recognition = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    return LegalSpanSegmenter().segment(text, recognition).units


def _units_by_level(units: list[SegmentedLegalUnit], level: LegalNodeLevel) -> list[SegmentedLegalUnit]:
    """Filter segmented units by legal level."""
    return [unit for unit in units if unit.level == level]


def _unit_with_heading(units: list[SegmentedLegalUnit], heading_text: str) -> SegmentedLegalUnit:
    """Find one segmented unit by exact heading text."""
    return next(unit for unit in units if unit.heading_text == heading_text)


def _assert_exact_slices(text: str, units: list[SegmentedLegalUnit]) -> None:
    """Assert every segmented unit preserves exact original source slices."""
    for unit in units:
        assert unit.text == text[unit.start_offset : unit.end_offset]
        assert unit.heading_text == text[unit.heading_start_offset : unit.heading_end_offset]
        assert unit.start_offset == unit.heading_start_offset
        assert unit.classification == CandidateClassification.CERTAIN


def test_article_only_document_spans_end_at_next_article_or_document_end() -> None:
    """Article-only spans end at the next Article or EOF."""
    text = "Điều 1. Một\nNội dung một.\nĐiều 2. Hai\nNội dung hai."
    units = _segment_text(text)
    articles = _units_by_level(units, LegalNodeLevel.ARTICLE)

    assert len(articles) == 2
    assert articles[0].end_offset == articles[1].start_offset
    assert articles[1].end_offset == len(text)
    _assert_exact_slices(text, units)


def test_titleless_article_spans_include_body_without_title() -> None:
    """Titleless Articles span following body text and keep title null."""
    text = "\n".join(
        [
            "Điều 1.",
            "Nước Cộng hòa xã hội chủ nghĩa Việt Nam là một nước độc lập.",
            "Điều 2.",
            "1. Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam là nhà nước pháp quyền.",
        ]
    )
    units = _segment_text(text)
    articles = _units_by_level(units, LegalNodeLevel.ARTICLE)

    assert [article.number for article in articles] == ["1", "2"]
    assert [article.title for article in articles] == [None, None]
    assert "Nước Cộng hòa" in articles[0].text
    assert "Nhà nước Cộng hòa" in articles[1].text
    assert articles[0].end_offset == articles[1].start_offset
    assert articles[1].end_offset == len(text)
    _assert_exact_slices(text, units)


def test_chapter_contains_articles_and_ends_before_next_chapter() -> None:
    """Chapter spans include descendant Articles but end before sibling Chapter."""
    text = _read_fixture("part_chapter_titles.txt")
    units = _segment_text(text)
    chapter_i = _unit_with_heading(units, "Chương I")
    chapter_ii = _unit_with_heading(units, "Chương II")
    article_1 = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")

    assert chapter_i.start_offset < article_1.start_offset < article_1.end_offset
    assert chapter_i.end_offset == chapter_ii.start_offset
    assert "NHỮNG QUY ĐỊNH CHUNG" in chapter_i.text
    assert article_1.text in chapter_i.text


def test_part_chapter_section_article_parent_inclusive_spans() -> None:
    """Part, Chapter, and Section parent spans include descendants."""
    text = _read_fixture("mixed_hierarchy_spans.txt")
    units = _segment_text(text)
    part_one = _unit_with_heading(units, "Phần thứ nhất")
    part_two = _unit_with_heading(units, "Phần thứ hai")
    chapter_i = _unit_with_heading(units, "Chương I")
    section_1 = _unit_with_heading(units, "Mục 1. PHẠM VI VÀ NGUYÊN TẮC")
    article_1 = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")

    assert part_one.end_offset == part_two.start_offset
    assert part_one.start_offset < chapter_i.start_offset < chapter_i.end_offset <= part_one.end_offset
    assert chapter_i.start_offset < section_1.start_offset < section_1.end_offset <= chapter_i.end_offset
    assert section_1.start_offset < article_1.start_offset < article_1.end_offset <= section_1.end_offset
    assert "QUY ĐỊNH CHUNG" in part_one.text
    assert "NHỮNG QUY ĐỊNH CHUNG" in chapter_i.text


def test_missing_intermediate_levels_are_supported() -> None:
    """Direct Articles, Chapter->Article, and Part->Article all segment."""
    text = "\n".join(
        [
            "Điều 1. Điều trực tiếp",
            "Nội dung 1.",
            "Chương I",
            "QUY ĐỊNH CHƯƠNG",
            "Điều 2. Điều trong chương",
            "Nội dung 2.",
            "Phần thứ nhất",
            "PHẦN TRỰC TIẾP",
            "Điều 3. Điều trong phần",
            "Nội dung 3.",
        ]
    )
    units = _segment_text(text)
    articles = _units_by_level(units, LegalNodeLevel.ARTICLE)
    chapter = _unit_with_heading(units, "Chương I")
    part = _unit_with_heading(units, "Phần thứ nhất")

    assert [article.number for article in articles] == ["1", "2", "3"]
    assert chapter.start_offset < articles[1].start_offset < articles[1].end_offset <= chapter.end_offset
    assert part.start_offset < articles[2].start_offset < articles[2].end_offset <= part.end_offset


def test_article_clause_and_point_spans_are_parent_inclusive() -> None:
    """Articles contain Clauses, and Clauses contain Points."""
    text = _read_fixture("article_clause_point_spans.txt")
    units = _segment_text(text)
    article_1 = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")
    clause_1 = _unit_with_heading(units, "1. Khoản một của Điều 1")
    point_a = _unit_with_heading(units, "a) Điểm a thuộc khoản một")
    point_b = _unit_with_heading(units, "b) Điểm b thuộc khoản một")
    clause_2 = _unit_with_heading(units, "2. Khoản hai của Điều 1")

    assert article_1.start_offset < clause_1.start_offset < clause_1.end_offset <= article_1.end_offset
    assert clause_1.start_offset < point_a.start_offset < point_a.end_offset <= clause_1.end_offset
    assert point_a.end_offset == point_b.start_offset
    assert point_b.end_offset == clause_2.start_offset
    assert clause_2.end_offset == _unit_with_heading(units, "Điều 2. Đối tượng áp dụng").start_offset


def test_point_context_resets_at_next_clause_and_article() -> None:
    """Point spans do not continue into the next Clause or Article."""
    text = _read_fixture("article_clause_point_spans.txt")
    units = _segment_text(text)
    point_b = _unit_with_heading(units, "b) Điểm b thuộc khoản một")
    clause_2 = _unit_with_heading(units, "2. Khoản hai của Điều 1")
    article_2 = _unit_with_heading(units, "Điều 2. Đối tượng áp dụng")

    assert point_b.end_offset == clause_2.start_offset
    assert clause_2.end_offset == article_2.start_offset


def test_exact_source_slicing_and_text_immutability() -> None:
    """Segmentation preserves source text, Unicode, punctuation, and footnotes."""
    text = _read_fixture("clause_point_candidates.txt")
    original = text[:]
    units = _segment_text(text)
    footnoted_clause = _unit_with_heading(units, "2.[3] Khoản chắc chắn có chú thích")
    footnoted_point = _unit_with_heading(units, "c)[4] Điểm c có chú thích")

    assert text == original
    assert "[3]" in footnoted_clause.text
    assert "[4]" in footnoted_point.text
    assert "đ) Điểm đ thuộc khoản 2" in _unit_with_heading(
        units,
        "2.[3] Khoản chắc chắn có chú thích",
    ).text
    _assert_exact_slices(text, units)


def test_introductory_text_is_not_included_in_first_non_root_unit() -> None:
    """Text before the first certain heading remains outside non-root spans."""
    text = _read_fixture("mixed_hierarchy_spans.txt")
    units = _segment_text(text)
    first_unit = units[0]

    assert first_unit.heading_text == "Phần thứ nhất"
    assert first_unit.start_offset == text.index("Phần thứ nhất")
    assert "Lời giới thiệu trước thân luật." not in first_unit.text


def test_ambiguous_and_rejected_candidates_do_not_create_boundaries() -> None:
    """Ambiguous/rejected candidates remain inside containing certain spans."""
    text = _read_fixture("clause_point_candidates.txt")
    units = _segment_text(text)
    article_1 = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")
    clause_2 = _unit_with_heading(units, "2.[3] Khoản chắc chắn có chú thích")
    compact_clause = _unit_with_heading(units, "1.Nội dung thiếu khoảng trắng")

    assert "1.Nội dung thiếu khoảng trắng" in article_1.text
    assert "2 Nội dung thiếu dấu chấm" in article_1.text
    assert "01 tháng 01 năm 2026 không phải khoản" in article_1.text
    assert "1.Nội dung thiếu khoảng trắng" not in clause_2.text
    assert "2 Nội dung thiếu dấu chấm" in compact_clause.text
    assert "01 tháng 01 năm 2026 không phải khoản" in compact_clause.text


def test_trailing_source_note_ends_final_legal_unit_span() -> None:
    """A trailing source-note boundary ends the final Article span."""
    text = "\n".join(
        [
            "Điều 1. Phạm vi điều chỉnh",
            "Nội dung Điều 1.",
            "Điều 74 và Điều 75 của Luật Giá số 16/2023/QH15 quy định như sau:",
            "1. Nội dung ghi chú nguồn.",
        ]
    )
    units = _segment_text(text)
    article = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")

    assert article.end_offset == text.index("Điều 74")
    assert "Nội dung ghi chú nguồn" not in article.text


def test_source_note_followed_by_valid_article_keeps_later_article() -> None:
    """Source-note exclusion does not remove a later validated Article."""
    text = _read_fixture("source_note_boundaries.txt")
    units = _segment_text(text)
    article_1 = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")
    article_2 = _unit_with_heading(units, "Điều 2. Nội dung được nhận diện lại")

    assert article_1.end_offset == text.index("Điều 74")
    assert article_2.text == text[article_2.start_offset : article_2.end_offset]
    assert "Nội dung Điều 2." in article_2.text


def test_trailing_appendix_region_ends_final_legal_unit_span() -> None:
    """Appendix text is not included in the final legal-unit span."""
    text = "\n".join(
        [
            "Điều 1. Phạm vi điều chỉnh",
            "Nội dung Điều 1.",
            "PHỤ LỤC",
            "1. Dòng phụ lục",
        ]
    )
    units = _segment_text(text)
    article = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")

    assert article.end_offset == text.index("PHỤ LỤC")
    assert "Dòng phụ lục" not in article.text


def test_table_marker_inside_article_does_not_end_article() -> None:
    """Table markers suppress false candidates but do not end Article spans."""
    text = "\n".join(
        [
            "Điều 1. Phạm vi điều chỉnh",
            "Nội dung trước bảng.",
            "STT",
            "1. Dòng bảng không phải khoản",
        ]
    )
    units = _segment_text(text)
    article = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")

    assert article.end_offset == len(text)
    assert "STT" in article.text
    assert "Dòng bảng không phải khoản" in article.text


def test_signature_footer_boundary_applies_only_as_trailing_boundary() -> None:
    """Signature/footer-like text may end a final legal-unit span."""
    text = _read_fixture("intro_and_trailing_regions.txt")
    units = _segment_text(text)
    article = _unit_with_heading(units, "Điều 1. Phạm vi điều chỉnh")

    assert article.end_offset == text.index("Nơi nhận:")
    assert "Ủy ban thường vụ Quốc hội." not in article.text


def test_units_are_source_ordered_and_same_level_siblings_do_not_overlap() -> None:
    """Segmented units are deterministic, source ordered, and sibling-safe."""
    text = _read_fixture("mixed_hierarchy_spans.txt")
    units = _segment_text(text)

    assert [unit.start_offset for unit in units] == sorted(unit.start_offset for unit in units)
    for level in LegalNodeLevel:
        siblings = _units_by_level(units, level)
        for previous, current in zip(siblings, siblings[1:], strict=False):
            assert previous.end_offset <= current.start_offset


def test_repeated_segmentation_is_deterministic() -> None:
    """Identical input and recognition output produce identical segments."""
    text = _read_fixture("article_clause_point_spans.txt")
    first = [unit.model_dump(mode="json") for unit in _segment_text(text)]
    second = [unit.model_dump(mode="json") for unit in _segment_text(text)]

    assert first == second
