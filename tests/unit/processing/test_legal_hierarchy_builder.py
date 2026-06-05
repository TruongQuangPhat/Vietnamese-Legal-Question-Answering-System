"""Tests for deterministic Phase 5 legal hierarchy construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.processing.legal_heading_recognizer import LegalHeadingRecognizer
from src.processing.legal_hierarchy_builder import LegalHierarchyBuilder, LegalHierarchyBuildError
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
    ParsingIssueCode,
    StructuredParsingIssue,
)
from src.processing.legal_span_segmenter import LegalSpanSegmenter, SegmentedLegalUnit

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "legal_hierarchy"


def _read_fixture(name: str) -> str:
    """Load a committed synthetic hierarchy fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _metadata(article_count: int = 1, max_article: int = 1) -> LegalHierarchyMetadata:
    """Create canonical document metadata for builder tests."""
    return LegalHierarchyMetadata(
        law_name="Luật Kiểm thử",
        source_url="https://thuvienphapluat.vn/test.aspx",
        source_domain="thuvienphapluat.vn",
        source_type="html",
        raw_artifact_path="data/raw/TEST_LAW/latest/main.html",
        article_heading_count=article_count,
        max_heading_article_number=max_article,
        has_heading_article_1=True,
        heading_sequence_score=1.0,
    )


def _segment_text(text: str) -> list[SegmentedLegalUnit]:
    """Recognize and segment fixture text with the public Step 3-5 APIs."""
    recognition = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    return LegalSpanSegmenter().segment(text, recognition).units


def _build_document(
    text: str,
    *,
    segmented_units: list[SegmentedLegalUnit] | None = None,
    inherited_warnings: list[StructuredParsingIssue] | None = None,
) -> LegalHierarchyDocument:
    """Build a hierarchy document with test metadata."""
    result = LegalHierarchyBuilder().build(
        law_id="TEST_LAW",
        law_name="Luật Kiểm thử",
        normalized_text=text,
        source_file="data/interim/TEST_LAW/normalized.json",
        cleaner_version="v0.8.0",
        metadata=_metadata(article_count=text.count("Điều "), max_article=5),
        segmented_units=segmented_units if segmented_units is not None else _segment_text(text),
        inherited_warnings=inherited_warnings,
    )
    return result.document


def _node(document: LegalHierarchyDocument, node_id: str) -> LegalNode:
    """Find one node by ID."""
    return next(node for node in document.nodes if node.node_id == node_id)


def _node_with_heading(document: LegalHierarchyDocument, heading_text: str) -> LegalNode:
    """Find one node by exact heading metadata."""
    return next(
        node
        for node in document.nodes
        if node.metadata.get("heading_text") == heading_text
    )


def _unit(
    *,
    level: LegalNodeLevel,
    number: str | None,
    text: str,
    start_offset: int,
    end_offset: int,
    active_article_number: str | None = None,
    active_clause_number: str | None = None,
) -> SegmentedLegalUnit:
    """Create a synthetic segmented unit for builder failure cases."""
    heading_text = text[start_offset:end_offset].splitlines()[0]
    return SegmentedLegalUnit(
        level=level,
        number=number,
        title=None,
        heading_text=heading_text,
        heading_start_offset=start_offset,
        heading_end_offset=start_offset + len(heading_text),
        start_offset=start_offset,
        end_offset=end_offset,
        text=text[start_offset:end_offset],
        line_number=1,
        active_article_number=active_article_number,
        active_clause_number=active_clause_number,
        metadata={},
    )


def test_root_node_contract_and_flat_order() -> None:
    """The builder creates exactly one real root Law node first."""
    text = "Điều 1. Phạm vi điều chỉnh\nNội dung Điều 1."
    document = _build_document(text)
    root = document.nodes[0]

    assert document.root_node_id == "TEST_LAW__root"
    assert root.node_id == document.root_node_id
    assert root.level == LegalNodeLevel.LAW
    assert root.number is None
    assert root.title == "Luật Kiểm thử"
    assert root.text == text
    assert root.start_offset == 0
    assert root.end_offset == len(text)
    assert root.parent_id is None
    assert [node.level for node in document.nodes].count(LegalNodeLevel.LAW) == 1


def test_article_only_document_attaches_articles_to_root() -> None:
    """Article-only documents use the root as the Article parent."""
    text = "Điều 1. Một\nNội dung một.\nĐiều 2. Hai\nNội dung hai."
    document = _build_document(text)
    root = document.nodes[0]

    assert root.children == [
        "TEST_LAW__root__article_1",
        "TEST_LAW__root__article_2",
    ]
    assert _node(document, "TEST_LAW__root__article_1").parent_id == root.node_id
    assert _node(document, "TEST_LAW__root__article_2").parent_id == root.node_id


def test_parent_assignment_for_part_chapter_section_article() -> None:
    """Part, Chapter, Section, and Article parent chains follow active context."""
    text = _read_fixture("mixed_hierarchy_spans.txt")
    document = _build_document(text)
    part = _node(document, "TEST_LAW__root__part_thu_nhat")
    chapter = _node(document, f"{part.node_id}__chapter_I")
    section = _node(document, f"{chapter.node_id}__section_1")
    article = _node(document, f"{section.node_id}__article_1")

    assert part.parent_id == document.root_node_id
    assert chapter.parent_id == part.node_id
    assert section.parent_id == chapter.node_id
    assert article.parent_id == section.node_id
    assert part.children[0] == chapter.node_id
    assert chapter.children[0] == section.node_id
    assert section.children[:2] == [
        article.node_id,
        f"{section.node_id}__article_2",
    ]


def test_missing_intermediate_levels_use_deterministic_fallbacks() -> None:
    """Article, Chapter->Article, Part->Article, and fallback Section all work."""
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
            "Mục 1. MỤC TRỰC TIẾP TRONG PHẦN",
            "Điều 4. Điều trong mục",
            "Nội dung 4.",
        ]
    )
    document = _build_document(text)
    root = document.nodes[0]
    direct_article = _node(document, "TEST_LAW__root__article_1")
    chapter = _node(document, "TEST_LAW__root__chapter_I")
    chapter_article = _node(document, f"{chapter.node_id}__article_2")
    part = _node(document, "TEST_LAW__root__part_thu_nhat")
    part_article = _node(document, f"{part.node_id}__article_3")
    section = _node(document, f"{part.node_id}__section_1")
    section_article = _node(document, f"{section.node_id}__article_4")

    assert direct_article.parent_id == root.node_id
    assert chapter_article.parent_id == chapter.node_id
    assert part_article.parent_id == part.node_id
    assert section.parent_id == part.node_id
    assert section_article.parent_id == section.node_id
    assert root.children == [direct_article.node_id, chapter.node_id, part.node_id]


def test_new_part_and_chapter_reset_lower_active_context() -> None:
    """New higher levels clear stale Chapter, Section, and Article contexts."""
    text = _read_fixture("mixed_hierarchy_spans.txt")
    document = _build_document(text)
    part_two = _node(document, "TEST_LAW__root__part_thu_hai")
    article_five = _node(document, f"{part_two.node_id}__article_5")

    assert part_two.parent_id == document.root_node_id
    assert part_two.children == [article_five.node_id]
    assert article_five.parent_id == part_two.node_id


def test_clause_and_point_parent_assignment() -> None:
    """Clauses attach to Articles and Points attach to the current Clause."""
    text = _read_fixture("article_clause_point_spans.txt")
    document = _build_document(text)
    article_1 = _node(document, "TEST_LAW__root__article_1")
    clause_1 = _node(document, f"{article_1.node_id}__clause_1")
    clause_2 = _node(document, f"{article_1.node_id}__clause_2")
    point_a = _node(document, f"{clause_1.node_id}__point_a")
    point_b = _node(document, f"{clause_1.node_id}__point_b")
    article_2 = _node(document, "TEST_LAW__root__article_2")
    article_2_clause = _node(document, f"{article_2.node_id}__clause_1")
    article_2_point = _node(document, f"{article_2_clause.node_id}__point_a")

    assert article_1.children == [clause_1.node_id, clause_2.node_id]
    assert clause_1.children == [point_a.node_id, point_b.node_id]
    assert clause_2.children == []
    assert article_2.children == [article_2_clause.node_id]
    assert article_2_point.parent_id == article_2_clause.node_id


def test_missing_required_clause_or_point_parent_fails_explicitly() -> None:
    """Builder does not invent Clause or Point fallback parents."""
    clause_text = "1. Khoản không có Điều"
    point_text = "a) Điểm không có khoản"

    with pytest.raises(LegalHierarchyBuildError, match="Clause requires an active Article"):
        _build_document(
            clause_text,
            segmented_units=[
                _unit(
                    level=LegalNodeLevel.CLAUSE,
                    number="1",
                    text=clause_text,
                    start_offset=0,
                    end_offset=len(clause_text),
                )
            ],
        )

    with pytest.raises(LegalHierarchyBuildError, match="Point requires an active Clause"):
        _build_document(
            point_text,
            segmented_units=[
                _unit(
                    level=LegalNodeLevel.POINT,
                    number="a",
                    text=point_text,
                    start_offset=0,
                    end_offset=len(point_text),
                    active_article_number="1",
                )
            ],
        )


def test_selected_parent_span_must_contain_child_span() -> None:
    """Structurally selected parents must contain child spans."""
    text = "Điều 1. Ngắn\n1. Khoản ngoài span"
    article = _unit(
        level=LegalNodeLevel.ARTICLE,
        number="1",
        text=text,
        start_offset=0,
        end_offset=text.index("\n"),
    )
    clause = _unit(
        level=LegalNodeLevel.CLAUSE,
        number="1",
        text=text,
        start_offset=text.index("1. Khoản"),
        end_offset=len(text),
        active_article_number="1",
    )

    with pytest.raises(LegalHierarchyBuildError, match="does not contain child span"):
        _build_document(text, segmented_units=[article, clause])


def test_introductory_and_trailing_text_remain_root_only() -> None:
    """Intro, source-note, appendix, and footer text excluded by spans stay root-only."""
    text = _read_fixture("intro_and_trailing_regions.txt")
    document = _build_document(text)
    root = document.nodes[0]
    article = _node(document, "TEST_LAW__root__article_1")

    assert "Quốc hội ban hành Luật kiểm thử." in root.text
    assert "Nơi nhận:" in root.text
    assert "Quốc hội ban hành Luật kiểm thử." not in article.text
    assert "Nơi nhận:" not in article.text


def test_deterministic_ids_preserve_legal_numbers_and_tokens() -> None:
    """ID normalization is deterministic and independent from display number."""
    text = "\n".join(
        [
            "Phần thứ nhất",
            "QUY ĐỊNH CHUNG",
            "Chương I",
            "NHỮNG QUY ĐỊNH CHUNG",
            "Mục 1. MỤC MỘT",
            "Điều 217a. Điều có hậu tố",
            "1. Khoản một",
            "đ) Điểm đ",
        ]
    )
    first = _build_document(text)
    second = _build_document(text)
    point_id = (
        "TEST_LAW__root__part_thu_nhat__chapter_I__section_1"
        "__article_217a__clause_1__point_đ"
    )
    point = _node(first, point_id)

    assert [node.node_id for node in first.nodes] == [node.node_id for node in second.nodes]
    assert _node(first, "TEST_LAW__root__part_thu_nhat").number == "thứ nhất"
    assert _node(first, "TEST_LAW__root__part_thu_nhat__chapter_I").number == "I"
    assert point.number == "đ"


def test_collision_suffixes_and_warnings_are_deterministic() -> None:
    """Duplicate sibling numbers receive source-ordered occurrence suffixes."""
    text = "\n".join(
        [
            "Điều 1. Một",
            "1. Khoản một",
            "1. Khoản một lặp lại",
            "1. Khoản một lặp lần ba",
        ]
    )
    document = _build_document(text)
    article = _node(document, "TEST_LAW__root__article_1")

    assert article.children == [
        "TEST_LAW__root__article_1__clause_1",
        "TEST_LAW__root__article_1__clause_1__occurrence_2",
        "TEST_LAW__root__article_1__clause_1__occurrence_3",
    ]
    collision_warnings = [
        warning
        for warning in document.warnings
        if warning.code == ParsingIssueCode.NODE_ID_COLLISION_RESOLVED
    ]
    assert [warning.context["occurrence"] for warning in collision_warnings] == [2, 3]
    assert all(warning.law_id == "TEST_LAW" for warning in collision_warnings)


def test_duplicate_numbers_under_different_parents_do_not_collide() -> None:
    """Node IDs include the resolved parent path before collision checks."""
    text = "\n".join(
        [
            "Chương I",
            "CHƯƠNG MỘT",
            "Điều 1. Một",
            "Chương II",
            "CHƯƠNG HAI",
            "Điều 1. Một",
        ]
    )
    document = _build_document(text)

    assert _node(document, "TEST_LAW__root__chapter_I__article_1").number == "1"
    assert _node(document, "TEST_LAW__root__chapter_II__article_1").number == "1"
    assert document.warnings == []


def test_children_of_collision_resolved_parent_use_final_parent_id() -> None:
    """Child IDs are generated from the final resolved parent node ID."""
    text = "\n".join(
        [
            "Điều 1. Một",
            "1. Khoản thuộc Điều đầu",
            "Điều 1. Một lặp",
            "1. Khoản thuộc Điều lặp",
        ]
    )
    document = _build_document(text)
    second_article = _node(document, "TEST_LAW__root__article_1__occurrence_2")
    child_id = "TEST_LAW__root__article_1__occurrence_2__clause_1"

    assert second_article.children == [child_id]
    assert _node(document, child_id).parent_id == second_article.node_id


def test_children_and_flat_nodes_are_source_ordered_without_synthetic_nodes() -> None:
    """Flat nodes are root-first, source-ordered, and child references are unique."""
    text = _read_fixture("mixed_hierarchy_spans.txt")
    document = _build_document(text)
    non_root_nodes = document.nodes[1:]
    child_references = [
        child_id
        for node in document.nodes
        for child_id in node.children
    ]

    assert [node.start_offset for node in non_root_nodes] == sorted(
        node.start_offset for node in non_root_nodes
    )
    assert len(child_references) == len(set(child_references))
    assert set(child_references) == {node.node_id for node in non_root_nodes}
    assert all(_node(document, child_id).level != LegalNodeLevel.CLAUSE for child_id in document.nodes[0].children)
    assert all(node.children == [] for node in document.nodes if node.level == LegalNodeLevel.POINT)
    assert LegalNodeLevel.SECTION in {node.level for node in document.nodes}
    assert LegalNodeLevel.CLAUSE not in {node.level for node in document.nodes}


def test_node_text_offsets_titles_metadata_and_serialization_are_preserved() -> None:
    """Builder preserves segmented spans, semantic titles, warnings, and JSON schema."""
    text = _read_fixture("article_clause_point_spans.txt")
    original_text = text[:]
    units = _segment_text(text)
    units_before = [unit.model_dump(mode="json") for unit in units]
    inherited_warning = StructuredParsingIssue(
        code=ParsingIssueCode.SOURCE_NOTE_EXCLUDED,
        message="Inherited warning.",
        law_id="TEST_LAW",
        context={"source": "test"},
    )
    document = _build_document(text, segmented_units=units, inherited_warnings=[inherited_warning])
    article = _node_with_heading(document, "Điều 1. Phạm vi điều chỉnh")

    assert text == original_text
    assert [unit.model_dump(mode="json") for unit in units] == units_before
    assert article.text == text[article.start_offset : article.end_offset]
    assert article.title == "Phạm vi điều chỉnh"
    assert article.number == "1"
    assert article.metadata["heading_text"] == "Điều 1. Phạm vi điều chỉnh"
    assert "law_id" not in article.metadata
    assert document.warnings[0] == inherited_warning
    round_trip = LegalHierarchyDocument.model_validate(document.model_dump(mode="json"))
    assert round_trip == document
