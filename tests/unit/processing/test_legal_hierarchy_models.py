"""Tests for Phase 5 legal hierarchy schemas and structured issues."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
    LegalParsingReport,
    LegalParsingResult,
    LegalParsingStatus,
    ParsingIssueCode,
    StructuredParsingIssue,
    ValidationSummary,
)


def _metadata() -> LegalHierarchyMetadata:
    """Create canonical document metadata for hierarchy schema tests."""
    return LegalHierarchyMetadata(
        law_name="Luật Kiểm thử",
        source_url="https://thuvienphapluat.vn/test.aspx",
        source_domain="thuvienphapluat.vn",
        source_type="html",
        raw_artifact_path="data/raw/TEST_LAW/latest/main.html",
        article_heading_count=1,
        max_heading_article_number=1,
        has_heading_article_1=True,
        heading_sequence_score=1.0,
    )


def _root_node(text: str = "Điều 1. Phạm vi điều chỉnh\n") -> LegalNode:
    """Create a valid root Law node."""
    return LegalNode(
        node_id="TEST_LAW__root",
        level=LegalNodeLevel.LAW,
        number=None,
        title="Luật Kiểm thử",
        text=text,
        start_offset=0,
        end_offset=len(text),
        parent_id=None,
        children=[],
        metadata={},
    )


def test_canonical_hierarchy_schema_validation() -> None:
    """Validate the approved top-level hierarchy document contract."""
    root = _root_node()
    document = LegalHierarchyDocument(
        schema_version="1.0",
        parser_version="v0.1.0",
        cleaner_version="v0.8.0",
        law_id="TEST_LAW",
        source_file="data/interim/TEST_LAW/normalized.json",
        root_node_id=root.node_id,
        metadata=_metadata(),
        warnings=[],
        nodes=[root],
    )

    dumped = document.model_dump(mode="json")

    assert dumped["root_node_id"] == "TEST_LAW__root"
    assert dumped["nodes"][0]["level"] == "law"
    assert "Luật Kiểm thử" in json.dumps(dumped, ensure_ascii=False)


def test_canonical_parsing_report_schema_validation() -> None:
    """Validate the approved batch parsing report contract."""
    result = LegalParsingResult(
        law_id="TEST_LAW",
        status=LegalParsingStatus.SUCCESS,
        input_path="data/interim/TEST_LAW/normalized.json",
        output_path="data/interim/TEST_LAW/hierarchy.json",
        duration_seconds=0.1,
        node_count=1,
        counts_by_level={"law": 1},
        has_article_1=True,
        max_article_number=1,
        expected_article_heading_count=1,
        article_heading_count_matches=True,
        expected_max_heading_article_number=1,
        max_article_number_matches=True,
        warnings=[],
        errors=[],
    )
    report = LegalParsingReport(
        schema_version="1.0",
        parser_version="v0.1.0",
        started_at="2026-06-05T10:00:00Z",
        finished_at="2026-06-05T10:00:01Z",
        duration_seconds=1.0,
        input_dir="data/interim",
        output_dir="data/interim",
        total_documents=1,
        successful=1,
        success_with_warnings=0,
        failed=0,
        nodes_by_level={"law": 1},
        validation_summary=ValidationSummary(),
        results=[result],
        warnings=[],
        errors=[],
    )

    assert report.results[0].status == LegalParsingStatus.SUCCESS
    assert report.validation_summary.invalid_offsets == 0


def test_root_node_contract_is_enforced() -> None:
    """Reject hierarchy documents whose root Law node violates invariants."""
    bad_root = _root_node()
    bad_root.parent_id = "TEST_LAW__other"

    with pytest.raises(ValidationError, match="root parent_id"):
        LegalHierarchyDocument(
            schema_version="1.0",
            parser_version="v0.1.0",
            cleaner_version="v0.8.0",
            law_id="TEST_LAW",
            source_file="data/interim/TEST_LAW/normalized.json",
            root_node_id=bad_root.node_id,
            metadata=_metadata(),
            nodes=[bad_root],
        )


def test_structured_warning_error_serialization_and_nullable_locations() -> None:
    """Serialize structured issues with nullable node and offset locations."""
    issue = StructuredParsingIssue(
        code=ParsingIssueCode.CLEANED_TEXT_MISMATCH,
        message="cleaned.txt differs from normalized_text.",
        law_id="TEST_LAW",
        node_id=None,
        start_offset=None,
        end_offset=None,
        context={"normalized_length": 10, "cleaned_length": 11},
    )

    dumped = issue.model_dump(mode="json")

    assert dumped["code"] == "CLEANED_TEXT_MISMATCH"
    assert dumped["node_id"] is None
    assert dumped["context"]["cleaned_length"] == 11


def test_mutable_defaults_are_independent() -> None:
    """Ensure list and dict defaults do not leak across model instances."""
    first = LegalNode(
        node_id="a",
        level=LegalNodeLevel.ARTICLE,
        number="1",
        title="Một",
        text="Điều 1. Một",
        start_offset=0,
        end_offset=11,
        parent_id="root",
    )
    second = LegalNode(
        node_id="b",
        level=LegalNodeLevel.ARTICLE,
        number="2",
        title="Hai",
        text="Điều 2. Hai",
        start_offset=12,
        end_offset=23,
        parent_id="root",
    )

    first.children.append("child")
    first.metadata["heading_text"] = "Điều 1. Một"

    assert second.children == []
    assert second.metadata == {}


def test_invalid_node_level_is_rejected() -> None:
    """Reject node levels outside the canonical Phase 5 level set."""
    with pytest.raises(ValidationError):
        LegalNode(
            node_id="bad",
            level="appendix",
            number="I",
            title=None,
            text="Phụ lục I",
            start_offset=0,
            end_offset=8,
            parent_id="root",
        )


def test_invalid_node_offsets_are_rejected() -> None:
    """Reject node offsets that cannot represent a Python slice."""
    with pytest.raises(ValidationError, match="end_offset"):
        LegalNode(
            node_id="bad",
            level=LegalNodeLevel.ARTICLE,
            number="1",
            title=None,
            text="Điều 1.",
            start_offset=5,
            end_offset=5,
            parent_id="root",
        )
