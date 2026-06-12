"""Unit tests for Phase 9C deterministic generation validators."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.retrieval.generation import (
    FALLBACK_ANSWER_VI,
    CitationIssue,
    CitationIssueSeverity,
    RagAnswerResult,
    RagCitation,
)
from src.retrieval.generation_evaluation import (
    GenerationEvalQuery,
    build_generation_eval_report,
    is_likely_vietnamese,
    validate_generation_result,
)
from src.retrieval.selection import AnswerabilityDecision


def test_answer_allowed_with_valid_citation_passes() -> None:
    """Allowed generation with a mapped citation ID passes."""
    evaluated = validate_generation_result(
        _allowed_case(),
        _result(
            answer="Trẻ em dưới 6 tuổi được cấp thẻ bảo hiểm y tế [E1].",
            citations=[_citation()],
        ),
    )

    assert evaluated.passed is True
    assert evaluated.citation_id_coverage_passed is True


def test_answer_allowed_without_required_citation_fails() -> None:
    """Missing citation IDs are report-blocking Phase 9C failures."""
    evaluated = validate_generation_result(
        _allowed_case(),
        _result(
            answer="Trẻ em dưới 6 tuổi được cấp thẻ bảo hiểm y tế.",
            citations=[],
            citation_issues=[_citation_issue("missing_citation_id")],
        ),
    )

    assert evaluated.passed is False
    assert evaluated.missing_citation_id_count == 1


def test_unknown_citation_id_fails() -> None:
    """Unknown model citation IDs are deterministic failures."""
    evaluated = validate_generation_result(
        _allowed_case(),
        _result(
            answer="Nội dung không hợp lệ [E999].",
            citations=[],
            citation_issues=[_citation_issue("unknown_citation_id")],
        ),
    )

    assert evaluated.passed is False
    assert evaluated.unknown_citation_id_count == 1


def test_fallback_without_llm_or_citations_passes() -> None:
    """Deterministic fallback passes without an LLM call or citations."""
    evaluated = validate_generation_result(
        _fallback_case(),
        _result(
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            answer=FALLBACK_ANSWER_VI,
            llm_called=False,
            citations=[],
        ),
    )

    assert evaluated.passed is True
    assert evaluated.fallback_policy_passed is True


def test_fallback_with_llm_call_fails() -> None:
    """Fallback decisions must never report an LLM call."""
    evaluated = validate_generation_result(
        _fallback_case(),
        _result(
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            answer=FALLBACK_ANSWER_VI,
            llm_called=True,
            citations=[],
        ),
    )

    assert evaluated.passed is False
    assert evaluated.llm_call_policy_passed is False


def test_forbidden_phrase_detection_fails() -> None:
    """Configured unsafe/confidence phrases are rejected case-insensitively."""
    case = _allowed_case(must_not_contain=["theo tôi"])
    evaluated = validate_generation_result(
        case,
        _result(
            answer="Theo tôi, quy định này áp dụng [E1].",
            citations=[_citation()],
        ),
    )

    assert evaluated.passed is False
    assert evaluated.forbidden_phrase_failures == ["theo tôi"]


def test_vietnamese_language_heuristic_passes_vietnamese() -> None:
    """Vietnamese legal text passes the deterministic heuristic."""
    assert is_likely_vietnamese("Theo Điều 1, quyền dân sự được pháp luật bảo vệ.")


def test_vietnamese_language_heuristic_fails_english_only_answer() -> None:
    """Obvious English-only output fails when Vietnamese is expected."""
    evaluated = validate_generation_result(
        _allowed_case(),
        _result(
            answer="Children receive health insurance coverage [E1].",
            citations=[_citation()],
        ),
    )

    assert evaluated.passed is False
    assert evaluated.vietnamese_language_passed is False


@pytest.mark.parametrize(
    "secret_text",
    [
        "OPENROUTER_API_KEY",
        "Authorization: token",
        "Bearer token-value",
        "sk-or-example",
    ],
)
def test_secret_leak_detection_fails_and_redacts_preview(secret_text: str) -> None:
    """Secret-like markers fail validation and are absent from previews."""
    evaluated = validate_generation_result(
        _allowed_case(),
        _result(
            answer=f"Nội dung {secret_text} [E1].",
            citations=[_citation()],
        ),
    )

    assert evaluated.passed is False
    assert evaluated.secret_leak_failures
    assert secret_text not in evaluated.answer_preview


def test_aggregate_report_metrics_are_computed() -> None:
    """Aggregate rates and citation counts reflect case outcomes."""
    passed = validate_generation_result(
        _allowed_case(),
        _result(answer="Nội dung hợp lệ [E1].", citations=[_citation()]),
    )
    failed = validate_generation_result(
        _allowed_case(case_id="missing"),
        _result(
            answer="Nội dung thiếu trích dẫn.",
            citations=[],
            citation_issues=[_citation_issue("missing_citation_id")],
        ),
    )

    report = build_generation_eval_report(
        cases=[passed, failed],
        started_at=datetime.now(UTC),
        dataset_path=Path("data/eval/test.jsonl"),
        collection_name="collection",
        vector_name="dense",
        top_k=20,
        provider="openrouter",
        model="test/model",
    )

    assert report.total_cases == 2
    assert report.passed_cases == 1
    assert report.failed_cases == 1
    assert report.citation_id_coverage_rate == 0.5
    assert report.missing_citation_id_count == 1
    assert report.status == "validated_generation_eval_partial"


def _allowed_case(
    *,
    case_id: str = "allowed",
    must_not_contain: list[str] | None = None,
) -> GenerationEvalQuery:
    return GenerationEvalQuery(
        id=case_id,
        query="Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?",
        allowed_decisions=[AnswerabilityDecision.ANSWER_ALLOWED],
        expected_llm_called=True,
        requires_citation_ids=True,
        expected_language="vi",
        must_not_contain=must_not_contain or [],
    )


def _fallback_case() -> GenerationEvalQuery:
    return GenerationEvalQuery(
        id="fallback",
        query="Người lao động được nghỉ hằng năm bao nhiêu ngày?",
        allowed_decisions=[
            AnswerabilityDecision.FALLBACK_REQUIRED,
            AnswerabilityDecision.NEEDS_REVIEW,
        ],
        expected_llm_called=False,
        requires_citation_ids=False,
        expected_language="vi",
    )


def _result(
    *,
    decision: AnswerabilityDecision = AnswerabilityDecision.ANSWER_ALLOWED,
    answer: str,
    llm_called: bool = True,
    citations: list[RagCitation],
    citation_issues: list[CitationIssue] | None = None,
) -> RagAnswerResult:
    return RagAnswerResult(
        query="Câu hỏi",
        decision=decision,
        answer=answer,
        citations=citations,
        used_evidence=[],
        fallback_reasons=[],
        selection_warnings=[],
        citation_issues=citation_issues or [],
        retrieval_metadata={},
        selection_metadata={},
        generation_metadata={},
        llm_called=llm_called,
        model="test/model",
        provider="mock",
        errors=[],
    )


def _citation() -> RagCitation:
    return RagCitation(
        evidence_id="E1",
        packet_id="P1",
        citation="Điều 1",
        source_url="https://thuvienphapluat.vn/test",
    )


def _citation_issue(code: str) -> CitationIssue:
    return CitationIssue(
        code=code,
        severity=(
            CitationIssueSeverity.ERROR
            if code == "unknown_citation_id"
            else CitationIssueSeverity.WARNING
        ),
        message="citation validation issue",
    )
