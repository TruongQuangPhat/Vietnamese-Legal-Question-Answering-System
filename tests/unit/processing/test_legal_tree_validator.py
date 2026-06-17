"""Tests for deterministic Phase 5 legal tree validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.processing.legal_heading_recognizer import LegalHeadingRecognizer
from src.processing.legal_hierarchy_builder import LegalHierarchyBuilder
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
    ParsingIssueCode,
    StructuredParsingIssue,
)
from src.processing.legal_span_segmenter import LegalSpanSegmenter
from src.processing.legal_tree_validator import LegalTreeValidationResult, LegalTreeValidator

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "legal_hierarchy"


def _read_fixture(name: str) -> str:
    """Load a committed synthetic validation fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _metadata(
    *,
    article_count: int,
    max_article: int,
    has_article_1: bool = True,
) -> LegalHierarchyMetadata:
    """Create document metadata for validator tests."""
    return LegalHierarchyMetadata(
        law_name="Luật Kiểm thử",
        source_url="https://thuvienphapluat.vn/test.aspx",
        source_domain="thuvienphapluat.vn",
        source_type="html",
        raw_artifact_path="data/raw/TEST_LAW/latest/main.html",
        article_heading_count=article_count,
        max_heading_article_number=max_article,
        has_heading_article_1=has_article_1,
        heading_sequence_score=1.0,
    )


def _build_document(
    text: str,
    *,
    article_count: int | None = None,
    max_article: int | None = None,
    has_article_1: bool = True,
    warnings: list[StructuredParsingIssue] | None = None,
) -> LegalHierarchyDocument:
    """Build a hierarchy through the public Step 3-6 pipeline."""
    recognition = LegalHeadingRecognizer().recognize(text, law_id="TEST_LAW")
    segmented = LegalSpanSegmenter().segment(text, recognition)
    articles = [unit for unit in segmented.units if unit.level == LegalNodeLevel.ARTICLE]
    numeric_articles = [
        _article_numeric_prefix(unit.number)
        for unit in articles
        if _article_numeric_prefix(unit.number) is not None
    ]
    result = LegalHierarchyBuilder().build(
        law_id="TEST_LAW",
        law_name="Luật Kiểm thử",
        normalized_text=text,
        source_file="data/interim/TEST_LAW/normalized.json",
        cleaner_version="v0.8.0",
        metadata=_metadata(
            article_count=article_count if article_count is not None else len(articles),
            max_article=max_article
            if max_article is not None
            else max(numeric_articles, default=0),
            has_article_1=has_article_1,
        ),
        segmented_units=segmented.units,
        inherited_warnings=warnings,
    )
    return result.document


def _validate(
    document: LegalHierarchyDocument,
    text: str,
) -> LegalTreeValidationResult:
    """Validate a hierarchy document with the Step 7 public API."""
    return LegalTreeValidator().validate(document=document, normalized_text=text)


def _node(document: LegalHierarchyDocument, node_id: str) -> LegalNode:
    """Find one node by ID."""
    return next(node for node in document.nodes if node.node_id == node_id)


def _article_numeric_prefix(number: str | None) -> int | None:
    """Return the comparable Article number prefix used by tests."""
    if number is None:
        return None
    digits = ""
    for char in number:
        if not char.isdigit():
            break
        digits += char
    return int(digits) if digits else None


def _copy_document(
    document: LegalHierarchyDocument,
    **updates: Any,
) -> LegalHierarchyDocument:
    """Create a deep malformed copy without revalidating Pydantic invariants."""
    return document.model_copy(deep=True, update=updates)


def _copy_node(node: LegalNode, **updates: Any) -> LegalNode:
    """Create a malformed node copy without weakening production schemas."""
    return node.model_copy(deep=True, update=updates)


def _issue_codes(issues: list[StructuredParsingIssue]) -> list[ParsingIssueCode]:
    """Return issue codes in emitted order."""
    return [issue.code for issue in issues]


def test_valid_article_only_hierarchy_passes_and_is_read_only() -> None:
    """A valid Article-only document passes and validation mutates nothing."""
    text = "Điều 1. Một\nNội dung một.\nĐiều 2. Hai\nNội dung hai."
    document = _build_document(text)
    document_before = document.model_dump(mode="json")
    text_before = text[:]

    first = _validate(document, text)
    second = _validate(document, text)

    assert first.is_valid is True
    assert first.errors == []
    assert first.warnings == []
    assert first.validation_summary.model_dump() == second.validation_summary.model_dump()
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert document.model_dump(mode="json") == document_before
    assert text == text_before


def test_valid_full_and_missing_intermediate_hierarchies_pass() -> None:
    """Full and missing-level legal structures are accepted."""
    full_text = "\n".join(
        [
            "Phần thứ nhất",
            "QUY ĐỊNH CHUNG",
            "Chương I",
            "NHỮNG QUY ĐỊNH CHUNG",
            "Mục 1. MỤC MỘT",
            "Điều 1. Một",
            "1. Khoản một",
            "a) Điểm a",
        ]
    )
    missing_text = "\n".join(
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

    assert _validate(_build_document(full_text), full_text).is_valid is True
    assert _validate(_build_document(missing_text), missing_text).is_valid is True


def test_valid_document_with_existing_warning_remains_valid_and_preserves_warning() -> None:
    """Document warnings are carried into the result without mutation."""
    text = "Điều 1. Một\nNội dung một."
    warning = StructuredParsingIssue(
        code=ParsingIssueCode.SOURCE_NOTE_EXCLUDED,
        message="Existing warning.",
        law_id="TEST_LAW",
        context={"line_number": 3},
    )
    document = _build_document(text, warnings=[warning])

    result = _validate(document, text)

    assert result.is_valid is True
    assert result.errors == []
    assert result.warnings == [warning]
    assert document.warnings == [warning]


def test_root_validation_errors_are_reported() -> None:
    """Root reference, multiplicity, offset, parent, and text defects are invalid."""
    text = "Điều 1. Một\nNội dung một."
    document = _build_document(text)
    root = document.nodes[0]
    article = document.nodes[1]
    extra_root = _copy_node(root, node_id="TEST_LAW__root_extra")

    missing_reference = _copy_document(document, root_node_id="TEST_LAW__missing_root")
    id_mismatch = _copy_document(document, root_node_id=article.node_id)
    multiple_roots = _copy_document(document, nodes=[*document.nodes, extra_root])
    root_with_parent = _copy_document(
        document,
        nodes=[_copy_node(root, parent_id=article.node_id), article],
    )
    root_wrong_offsets = _copy_document(
        document,
        nodes=[_copy_node(root, end_offset=len(text) - 1), article],
    )
    root_text_mismatch = _copy_document(
        document,
        nodes=[_copy_node(root, text=f"{text}x"), article],
    )

    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(missing_reference, text).errors)
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(id_mismatch, text).errors)
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(multiple_roots, text).errors)
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(root_with_parent, text).errors)
    assert ParsingIssueCode.INVALID_OFFSET in _issue_codes(
        _validate(root_wrong_offsets, text).errors
    )
    assert ParsingIssueCode.TEXT_OFFSET_MISMATCH in _issue_codes(
        _validate(root_text_mismatch, text).errors
    )


def test_duplicate_ids_and_reference_consistency_errors_are_detected() -> None:
    """Duplicate IDs, broken references, and bidirectional mismatches are invalid."""
    text = _read_fixture("article_clause_point_spans.txt")
    document = _build_document(text)
    root = document.nodes[0]
    article = _node(document, "TEST_LAW__root__article_1")
    clause = _node(document, f"{article.node_id}__clause_1")
    article_2 = _node(document, "TEST_LAW__root__article_2")

    duplicate_id = _copy_document(
        document,
        nodes=[*document.nodes, _copy_node(article_2, node_id=article.node_id)],
    )
    missing_parent = _copy_document(
        document,
        nodes=[
            node if node.node_id != clause.node_id else _copy_node(node, parent_id="missing")
            for node in document.nodes
        ],
    )
    missing_child_reference = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != root.node_id
            else _copy_node(node, children=[*node.children, "missing_child"])
            for node in document.nodes
        ],
    )
    bidirectional_mismatch = _copy_document(
        document,
        nodes=[
            node if node.node_id != clause.node_id else _copy_node(node, parent_id=root.node_id)
            for node in document.nodes
        ],
    )
    duplicate_child_reference = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != article.node_id
            else _copy_node(node, children=[*node.children, clause.node_id])
            for node in document.nodes
        ],
    )
    listed_by_multiple_parents = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != root.node_id
            else _copy_node(node, children=[*node.children, clause.node_id])
            for node in document.nodes
        ],
    )
    missing_from_parent_children = _copy_document(
        document,
        nodes=[
            node if node.node_id != article.node_id else _copy_node(node, children=[])
            for node in document.nodes
        ],
    )

    assert ParsingIssueCode.UNRESOLVED_DUPLICATE_NODE_ID in _issue_codes(
        _validate(duplicate_id, text).errors
    )
    assert ParsingIssueCode.ORPHAN_NODE in _issue_codes(_validate(missing_parent, text).errors)
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(
        _validate(missing_child_reference, text).errors
    )
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(
        _validate(bidirectional_mismatch, text).errors
    )
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(
        _validate(duplicate_child_reference, text).errors
    )
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(
        _validate(listed_by_multiple_parents, text).errors
    )
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(
        _validate(missing_from_parent_children, text).errors
    )


def test_cycles_and_unreachable_nodes_are_detected_safely() -> None:
    """Self cycles, multi-node cycles, and unreachable nodes return structured errors."""
    text = _read_fixture("article_clause_point_spans.txt")
    document = _build_document(text)
    article = _node(document, "TEST_LAW__root__article_1")
    clause = _node(document, f"{article.node_id}__clause_1")

    self_cycle = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != article.node_id
            else _copy_node(node, parent_id=node.node_id, children=[node.node_id])
            for node in document.nodes
        ],
    )
    multi_cycle = _copy_document(
        document,
        nodes=[
            _copy_node(node, parent_id=clause.node_id, children=[clause.node_id])
            if node.node_id == article.node_id
            else _copy_node(node, parent_id=article.node_id, children=[article.node_id])
            if node.node_id == clause.node_id
            else node
            for node in document.nodes
        ],
    )
    unreachable = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != article.node_id
            else _copy_node(node, parent_id=document.root_node_id)
            for node in document.nodes
        ],
    )
    root = unreachable.nodes[0]
    root.children.remove(article.node_id)

    self_result = _validate(self_cycle, text)
    multi_result = _validate(multi_cycle, text)
    unreachable_result = _validate(unreachable, text)

    assert ParsingIssueCode.PARENT_CYCLE in _issue_codes(self_result.errors)
    assert ParsingIssueCode.PARENT_CYCLE in _issue_codes(multi_result.errors)
    assert ParsingIssueCode.ORPHAN_NODE in _issue_codes(unreachable_result.errors)
    assert self_result.is_valid is False
    assert multi_result.is_valid is False


def test_allowed_legal_parent_chains_are_enforced() -> None:
    """Illegal Clause/Point parent chains are invalid while omitted levels pass."""
    valid_text = "Điều 1. Một\nNội dung một."
    valid = _validate(_build_document(valid_text), valid_text)
    text = _read_fixture("article_clause_point_spans.txt")
    document = _build_document(text)
    root = document.nodes[0]
    article = _node(document, "TEST_LAW__root__article_1")
    clause = _node(document, f"{article.node_id}__clause_1")
    point = _node(document, f"{clause.node_id}__point_a")

    clause_under_law = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != root.node_id
            else _copy_node(node, children=[*node.children, clause.node_id])
            if node.node_id == root.node_id
            else node
            for node in document.nodes
        ],
    )
    for node in clause_under_law.nodes:
        if node.node_id == clause.node_id:
            node.parent_id = root.node_id

    point_under_article = _copy_document(document)
    for node in point_under_article.nodes:
        if node.node_id == point.node_id:
            node.parent_id = article.node_id
        if node.node_id == article.node_id:
            node.children.append(point.node_id)

    point_with_child = _copy_document(document)
    for node in point_with_child.nodes:
        if node.node_id == point.node_id:
            node.children.append(clause.node_id)

    assert valid.is_valid is True
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(clause_under_law, text).errors)
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(
        _validate(point_under_article, text).errors
    )
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(point_with_child, text).errors)


def test_offsets_text_slices_parent_containment_and_sibling_order_are_validated() -> None:
    """Offset bounds, text agreement, containment, ordering, and overlap are checked."""
    text = "Điều 1. Một\nNội dung một.\nĐiều 2. Hai\nNội dung hai."
    document = _build_document(text)
    article_1 = _node(document, "TEST_LAW__root__article_1")
    article_2 = _node(document, "TEST_LAW__root__article_2")

    negative_offset = _copy_document(
        document,
        nodes=[
            node if node.node_id != article_1.node_id else _copy_node(node, start_offset=-1)
            for node in document.nodes
        ],
    )
    beyond_end = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != article_1.node_id
            else _copy_node(node, end_offset=len(text) + 1)
            for node in document.nodes
        ],
    )
    reversed_offset = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != article_1.node_id
            else _copy_node(node, start_offset=10, end_offset=5)
            for node in document.nodes
        ],
    )
    text_mismatch = _copy_document(
        document,
        nodes=[
            node if node.node_id != article_1.node_id else _copy_node(node, text="khác")
            for node in document.nodes
        ],
    )
    hierarchy_text = _read_fixture("article_clause_point_spans.txt")
    hierarchy_document = _build_document(hierarchy_text)
    hierarchy_article = _node(hierarchy_document, "TEST_LAW__root__article_1")
    hierarchy_clause = _node(hierarchy_document, f"{hierarchy_article.node_id}__clause_1")
    child_outside_parent = _copy_document(
        hierarchy_document,
        nodes=[
            node
            if node.node_id != hierarchy_article.node_id
            else _copy_node(node, end_offset=hierarchy_clause.start_offset)
            for node in hierarchy_document.nodes
        ],
    )
    sibling_overlap = _copy_document(
        document,
        nodes=[
            node
            if node.node_id != article_2.node_id
            else _copy_node(node, start_offset=article_1.start_offset + 5)
            for node in document.nodes
        ],
    )
    out_of_order = _copy_document(document)
    out_of_order.nodes[0].children = [article_2.node_id, article_1.node_id]

    assert ParsingIssueCode.INVALID_OFFSET in _issue_codes(_validate(negative_offset, text).errors)
    assert ParsingIssueCode.INVALID_OFFSET in _issue_codes(_validate(beyond_end, text).errors)
    assert ParsingIssueCode.INVALID_OFFSET in _issue_codes(_validate(reversed_offset, text).errors)
    assert ParsingIssueCode.TEXT_OFFSET_MISMATCH in _issue_codes(
        _validate(text_mismatch, text).errors
    )
    assert ParsingIssueCode.INVALID_OFFSET in _issue_codes(
        _validate(child_outside_parent, hierarchy_text).errors
    )
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(sibling_overlap, text).errors)
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(_validate(out_of_order, text).errors)
    assert _validate(document, text).is_valid is True


def test_article_presence_metric_warnings_and_empty_article_detection() -> None:
    """Article requirements and Phase 4 metric comparisons are deterministic."""
    root_only_text = "Không có điều luật."
    root = LegalNode(
        node_id="TEST_LAW__root",
        level=LegalNodeLevel.LAW,
        number=None,
        title="Luật Kiểm thử",
        text=root_only_text,
        start_offset=0,
        end_offset=len(root_only_text),
        parent_id=None,
    )
    root_only = LegalHierarchyDocument(
        schema_version="1.0",
        parser_version="v0.1.0",
        cleaner_version="v0.8.0",
        law_id="TEST_LAW",
        source_file="data/interim/TEST_LAW/normalized.json",
        root_node_id=root.node_id,
        metadata=_metadata(article_count=0, max_article=0, has_article_1=False),
        nodes=[root],
    )
    count_mismatch = _build_document("Điều 1. Một\nNội dung một.", article_count=2, max_article=1)
    max_mismatch = _build_document("Điều 1. Một\nNội dung một.", article_count=1, max_article=2)
    missing_article_1 = _build_document(
        "Điều 2. Hai\nNội dung hai.",
        article_count=1,
        max_article=2,
        has_article_1=True,
    )
    suffix_ok = _build_document(
        "Điều 217a. Điều có hậu tố\nNội dung.",
        article_count=1,
        max_article=217,
        has_article_1=False,
    )
    empty_article = _build_document("Điều 1. Một", article_count=1, max_article=1)

    assert ParsingIssueCode.NO_ARTICLES_FOUND in _issue_codes(
        _validate(root_only, root_only_text).errors
    )
    assert ParsingIssueCode.ARTICLE_COUNT_MISMATCH in _issue_codes(
        _validate(count_mismatch, count_mismatch.nodes[0].text).warnings
    )
    assert ParsingIssueCode.MAX_ARTICLE_NUMBER_MISMATCH in _issue_codes(
        _validate(max_mismatch, max_mismatch.nodes[0].text).warnings
    )
    assert ParsingIssueCode.MISSING_ARTICLE_1 in _issue_codes(
        _validate(missing_article_1, missing_article_1.nodes[0].text).warnings
    )
    assert ParsingIssueCode.MAX_ARTICLE_NUMBER_MISMATCH not in _issue_codes(
        _validate(suffix_ok, suffix_ok.nodes[0].text).warnings
    )
    assert ParsingIssueCode.EMPTY_ARTICLE_NODE in _issue_codes(
        _validate(empty_article, empty_article.nodes[0].text).warnings
    )


def test_validation_summary_counts_issue_deduplication_order_and_serialization() -> None:
    """Summary counts match issues, warnings dedupe, and result serializes."""
    text = "Điều 2. Hai\nNội dung hai."
    duplicate_warning = StructuredParsingIssue(
        code=ParsingIssueCode.ARTICLE_COUNT_MISMATCH,
        message="Parsed article count differs from Phase 4 heading count.",
        law_id="TEST_LAW",
        context={"expected": 2, "actual": 1},
    )
    distinct_warning = StructuredParsingIssue(
        code=ParsingIssueCode.ARTICLE_COUNT_MISMATCH,
        message="Distinct inherited warning.",
        law_id="TEST_LAW",
        context={"expected": 3, "actual": 1},
    )
    document = _build_document(
        text,
        article_count=2,
        max_article=3,
        has_article_1=True,
        warnings=[duplicate_warning, distinct_warning],
    )

    result = _validate(document, text)
    warning_codes = _issue_codes(result.warnings)

    assert result.is_valid is True
    assert result.validation_summary.missing_article_1 == 1
    assert result.validation_summary.article_heading_mismatch == 1
    assert result.validation_summary.empty_article_nodes == 0
    assert warning_codes == [
        ParsingIssueCode.ARTICLE_COUNT_MISMATCH,
        ParsingIssueCode.ARTICLE_COUNT_MISMATCH,
        ParsingIssueCode.MISSING_ARTICLE_1,
        ParsingIssueCode.MAX_ARTICLE_NUMBER_MISMATCH,
    ]
    assert warning_codes.count(ParsingIssueCode.ARTICLE_COUNT_MISMATCH) == 2
    assert LegalTreeValidationResult.model_validate(result.model_dump(mode="json")) == result
