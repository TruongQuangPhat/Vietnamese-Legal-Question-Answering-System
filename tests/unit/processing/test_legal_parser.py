"""Tests for the Phase 5 per-document legal parser facade."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.processing.legal_hierarchy_builder import LegalHierarchyBuildError
from src.processing.legal_hierarchy_models import (
    LegalParsingStatus,
    ParsingIssueCode,
    StructuredParsingIssue,
    ValidationSummary,
)
from src.processing.legal_parser import LegalParser
from src.processing.legal_tree_validator import LegalTreeValidationResult
from src.processing.normalized_input import NormalizedInputLoadResult, load_normalized_input

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "legal_hierarchy"


def _read_fixture(name: str) -> str:
    """Load a committed legal-hierarchy fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _artifact_payload(
    normalized_text: str,
    *,
    law_id: str = "TEST_LAW",
    law_name: str = "Luật Kiểm thử",
    article_count: int = 1,
    max_article: int = 1,
    has_article_1: bool = True,
    source_type: str = "html",
) -> dict[str, Any]:
    """Build a minimal normalized artifact payload for parser tests."""
    return {
        "law_id": law_id,
        "law_name": law_name,
        "source_url": "https://thuvienphapluat.vn/test.aspx",
        "source_domain": "thuvienphapluat.vn",
        "source_type": source_type,
        "raw_artifact_path": f"data/raw/{law_id}/latest/main.html",
        "normalized_text": normalized_text,
        "text_stats": {
            "normalized_text_chars": len(normalized_text),
            "line_count": len(normalized_text.splitlines()),
        },
        "markers": {
            "article_reference_count": article_count,
            "article_heading_count": article_count,
            "max_heading_article_number": max_article,
            "has_heading_article_1": has_article_1,
            "heading_sequence_score": 1.0,
        },
        "warnings": [],
        "metadata": {"cleaner_version": "v0.8.0"},
        "candidate_info": {"selection_strategy": "fixture"},
    }


def _write_normalized(
    tmp_path: Path,
    normalized_text: str,
    *,
    article_count: int = 1,
    max_article: int = 1,
    has_article_1: bool = True,
    cleaned_text: str | None = None,
) -> tuple[Path, Path]:
    """Write a normalized fixture and optional cleaned diagnostic text."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    normalized_path = tmp_path / "normalized.json"
    cleaned_path = tmp_path / "cleaned.txt"
    payload = _artifact_payload(
        normalized_text,
        article_count=article_count,
        max_article=max_article,
        has_article_1=has_article_1,
    )
    normalized_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if cleaned_text is not None:
        cleaned_path.write_text(cleaned_text, encoding="utf-8")
    return normalized_path, cleaned_path


def _parse_text(
    tmp_path: Path,
    text: str,
    *,
    article_count: int = 1,
    max_article: int = 1,
    has_article_1: bool = True,
    cleaned_text: str | None = None,
):
    """Parse one synthetic normalized document through the public facade."""
    normalized_path, cleaned_path = _write_normalized(
        tmp_path,
        text,
        article_count=article_count,
        max_article=max_article,
        has_article_1=has_article_1,
        cleaned_text=cleaned_text,
    )
    return LegalParser().parse_file(
        normalized_path=normalized_path,
        cleaned_path=cleaned_path if cleaned_text is not None else None,
    )


def _issue_codes(issues: list[StructuredParsingIssue]) -> list[ParsingIssueCode]:
    """Return issue codes in emitted order."""
    return [issue.code for issue in issues]


def test_article_only_document_parses_successfully_and_maps_metadata(tmp_path: Path) -> None:
    """A simple Article-only normalized document produces a valid hierarchy."""
    text = "Điều 1. Một\nNội dung một."
    normalized_path, _ = _write_normalized(tmp_path, text)

    result = LegalParser().parse_file(normalized_path=normalized_path)

    assert result.status == LegalParsingStatus.SUCCESS
    assert result.document is not None
    assert result.errors == []
    assert result.warnings == []
    assert result.document.source_file == str(normalized_path)
    assert result.document.metadata.source_type == "html"
    assert result.document.metadata.article_heading_count == 1
    assert result.document.nodes[0].text == text
    assert result.parsing_result.output_path is None
    assert result.parsing_result.counts_by_level == {"law": 1, "article": 1}
    assert result.parsing_result.node_count == 2
    assert result.parsing_result.has_article_1 is True


def test_full_and_missing_intermediate_hierarchies_parse_successfully(tmp_path: Path) -> None:
    """Full and omitted-level legal structures are accepted by the facade."""
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

    full_result = _parse_text(tmp_path / "full", full_text)
    missing_result = _parse_text(
        tmp_path / "missing",
        missing_text,
        article_count=3,
        max_article=3,
    )

    assert full_result.status == LegalParsingStatus.SUCCESS
    assert full_result.parsing_result.counts_by_level == {
        "law": 1,
        "part": 1,
        "chapter": 1,
        "section": 1,
        "article": 1,
        "clause": 1,
        "point": 1,
    }
    assert missing_result.status == LegalParsingStatus.SUCCESS
    assert missing_result.parsing_result.counts_by_level["article"] == 3
    assert missing_result.document is not None
    assert missing_result.document.nodes[0].children == [
        "TEST_LAW__root__article_1",
        "TEST_LAW__root__chapter_I",
        "TEST_LAW__root__part_thu_nhat",
    ]


def test_cleaned_mismatch_produces_success_with_warnings(tmp_path: Path) -> None:
    """Input-level cleaned text mismatch is preserved as a non-fatal warning."""
    text = "Điều 1. Một\nNội dung một."
    result = _parse_text(tmp_path, text, cleaned_text="Điều 1. Khác\n")

    assert result.status == LegalParsingStatus.SUCCESS_WITH_WARNINGS
    assert result.document is not None
    assert _issue_codes(result.warnings) == [ParsingIssueCode.CLEANED_TEXT_MISMATCH]


def test_recognition_warnings_reach_final_result_without_becoming_nodes(tmp_path: Path) -> None:
    """Ambiguous and rejected candidates warn but do not become hierarchy nodes."""
    text = _read_fixture("clause_point_candidates.txt")
    result = _parse_text(tmp_path, text, article_count=2, max_article=2)

    assert result.status == LegalParsingStatus.SUCCESS_WITH_WARNINGS
    assert {
        ParsingIssueCode.AMBIGUOUS_CLAUSE_CANDIDATE,
        ParsingIssueCode.POINT_LIKE_LINE_OUTSIDE_CLAUSE,
    }.issubset(set(_issue_codes(result.warnings)))
    assert result.document is not None
    heading_texts = {node.metadata.get("heading_text") for node in result.document.nodes}
    assert "1.Nội dung thiếu khoảng trắng" not in heading_texts
    assert "a) Điểm trực tiếp dưới điều không hợp lệ" not in heading_texts
    assert result.recognition_summary.ambiguous_candidate_count == 2
    assert result.recognition_summary.rejected_candidate_count >= 1


def test_quoted_source_note_article_does_not_fail_or_become_node(tmp_path: Path) -> None:
    """Article-like source-note lines remain outside the main hierarchy."""
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

    result = _parse_text(tmp_path, text, article_count=1, max_article=1)

    assert result.status == LegalParsingStatus.SUCCESS_WITH_WARNINGS
    assert result.document is not None
    assert _issue_codes(result.warnings) == [ParsingIssueCode.SOURCE_NOTE_EXCLUDED]
    article_headings = [
        node.metadata.get("heading_text")
        for node in result.document.nodes
        if node.level == "article"
    ]
    assert article_headings == ["Điều 1. Phạm vi điều chỉnh"]
    assert "Điều 4. Điều khoản chuyển tiếp" in result.document.nodes[0].text


def test_builder_and_validator_warnings_reach_final_result(tmp_path: Path) -> None:
    """Collision and Phase 4 metric warnings are surfaced by the facade."""
    collision_text = "\n".join(
        [
            "Điều 1. Một",
            "1. Khoản một",
            "1. Khoản một lặp lại",
        ]
    )
    metric_text = "Điều 1. Một\nNội dung một."

    collision_result = _parse_text(tmp_path / "collision", collision_text)
    metric_result = _parse_text(tmp_path / "metric", metric_text, article_count=2, max_article=1)

    assert collision_result.status == LegalParsingStatus.SUCCESS_WITH_WARNINGS
    assert ParsingIssueCode.NODE_ID_COLLISION_RESOLVED in _issue_codes(
        collision_result.warnings
    )
    assert metric_result.status == LegalParsingStatus.SUCCESS_WITH_WARNINGS
    assert ParsingIssueCode.ARTICLE_COUNT_MISMATCH in _issue_codes(metric_result.warnings)
    assert metric_result.validation_summary.article_heading_mismatch == 1


def test_identical_warnings_dedupe_but_distinct_same_code_warnings_remain(
    tmp_path: Path,
) -> None:
    """The parser keeps first-seen warning order and stable issue identity."""
    text = "Điều 1. Một\nNội dung một."
    normalized_path, _ = _write_normalized(tmp_path, text, article_count=2, max_article=1)
    load_result = load_normalized_input(normalized_path)
    duplicate = StructuredParsingIssue(
        code=ParsingIssueCode.ARTICLE_COUNT_MISMATCH,
        message="Parsed article count differs from Phase 4 heading count.",
        law_id="TEST_LAW",
        context={"expected": 2, "actual": 1},
    )
    distinct = StructuredParsingIssue(
        code=ParsingIssueCode.ARTICLE_COUNT_MISMATCH,
        message="Distinct inherited count warning.",
        law_id="TEST_LAW",
        context={"expected": 3, "actual": 1},
    )
    loaded_with_warnings = NormalizedInputLoadResult(
        artifact=load_result.artifact,
        warnings=[duplicate, distinct],
    )

    result = LegalParser().parse_loaded(
        input_result=loaded_with_warnings,
        source_file=str(normalized_path),
    )

    article_count_warnings = [
        warning
        for warning in result.warnings
        if warning.code == ParsingIssueCode.ARTICLE_COUNT_MISMATCH
    ]
    assert result.status == LegalParsingStatus.SUCCESS_WITH_WARNINGS
    assert len(article_count_warnings) == 2
    assert [warning.context["expected"] for warning in article_count_warnings] == [2, 3]


def test_failed_status_for_no_articles_and_input_validation_failure(tmp_path: Path) -> None:
    """Hard input and validation failures return failed results without a document."""
    no_article = _parse_text(
        tmp_path / "no_article",
        "Không có điều luật.",
        article_count=0,
        max_article=0,
        has_article_1=False,
    )
    invalid_path = tmp_path / "invalid" / "normalized.json"
    invalid_path.parent.mkdir()
    payload = _artifact_payload("Điều 1. Một\nNội dung một.")
    del payload["raw_artifact_path"]
    invalid_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    invalid = LegalParser().parse_file(normalized_path=invalid_path)

    assert no_article.status == LegalParsingStatus.FAILED
    assert no_article.document is None
    assert ParsingIssueCode.NO_ARTICLES_FOUND in _issue_codes(no_article.errors)
    assert invalid.status == LegalParsingStatus.FAILED
    assert invalid.document is None
    assert ParsingIssueCode.SCHEMA_VALIDATION_FAILED in _issue_codes(invalid.errors)


def test_builder_and_validator_failures_are_failed(tmp_path: Path) -> None:
    """Expected build and validation failures are converted to structured errors."""
    text = "Điều 1. Một\nNội dung một."
    normalized_path, _ = _write_normalized(tmp_path, text)

    class FailingBuilder:
        """Builder test double that raises an expected build error."""

        def build(self, **_: Any) -> None:
            """Raise a deterministic builder failure."""
            raise LegalHierarchyBuildError("forced build failure")

    class FailingValidator:
        """Validator test double that returns a hard invalid result."""

        def validate(self, **_: Any) -> LegalTreeValidationResult:
            """Return a deterministic invalid validation result."""
            return LegalTreeValidationResult(
                is_valid=False,
                validation_summary=ValidationSummary(invalid_parent_chain=1),
                warnings=[],
                errors=[
                    StructuredParsingIssue(
                        code=ParsingIssueCode.INVALID_TREE,
                        message="forced validator failure",
                        law_id="TEST_LAW",
                    )
                ],
            )

    build_failure = LegalParser(builder=FailingBuilder()).parse_file(
        normalized_path=normalized_path
    )
    validation_failure = LegalParser(validator=FailingValidator()).parse_file(
        normalized_path=normalized_path
    )

    assert build_failure.status == LegalParsingStatus.FAILED
    assert build_failure.document is None
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(build_failure.errors)
    assert validation_failure.status == LegalParsingStatus.FAILED
    assert validation_failure.document is None
    assert ParsingIssueCode.INVALID_TREE in _issue_codes(validation_failure.errors)


def test_parser_preserves_inputs_and_is_deterministic(tmp_path: Path) -> None:
    """Repeated parsing does not mutate inputs and returns stable serialized output."""
    text = "Điều 1. Một\nNội dung một."
    normalized_path, _ = _write_normalized(tmp_path, text)
    load_result = load_normalized_input(normalized_path)
    load_before = load_result.model_dump(mode="json")
    text_before = load_result.artifact.normalized_text[:]
    parser = LegalParser()

    first = parser.parse_loaded(input_result=load_result, source_file=str(normalized_path))
    second = parser.parse_loaded(input_result=load_result, source_file=str(normalized_path))

    assert load_result.model_dump(mode="json") == load_before
    assert load_result.artifact.normalized_text == text_before
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
