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
    UsedEvidence,
)
from src.retrieval.generation_evaluation import (
    GenerationEvalQuery,
    build_evidence_preview,
    build_generation_eval_report,
    is_likely_vietnamese,
    load_generation_eval_queries,
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
    assert report.status == "expanded_generation_eval_partial"


def test_repository_dataset_contains_five_reviewed_source_cases() -> None:
    """The expanded dataset uses every established manual retrieval case once."""
    cases = load_generation_eval_queries(
        Path("data/eval/manual_naive_rag_generation_queries.jsonl")
    )

    assert len(cases) == 5
    assert {case.id for case in cases} == {
        "annual_leave_days_generation",
        "civil_code_scope_generation",
        "civil_rights_protection_generation",
        "health_insurance_children_under_6_generation",
        "marriage_conditions_generation",
    }
    assert sum(case.manual_review_required for case in cases) == 2
    assert sum(not case.blocking for case in cases) == 2


def test_optional_review_metadata_allows_decision_driven_llm_policy() -> None:
    """Non-blocking review cases derive LLM policy from the actual decision."""
    case = _review_case()
    evaluated = validate_generation_result(
        case,
        _result(
            decision=AnswerabilityDecision.NEEDS_REVIEW,
            answer=FALLBACK_ANSWER_VI,
            llm_called=False,
            citations=[],
        ),
    )

    assert evaluated.passed is True
    assert evaluated.expected_llm_called is None
    assert evaluated.manual_review_required is True
    assert evaluated.blocking is False
    assert evaluated.citation_id_coverage_applicable is False


def test_citation_coverage_denominator_excludes_required_fallback_case() -> None:
    """Coverage is measured only when a citation-required case generates."""
    generated = validate_generation_result(
        _allowed_case(),
        _result(answer="Nội dung hợp lệ [E1].", citations=[_citation()]),
    )
    reviewed_fallback = validate_generation_result(
        _review_case(),
        _result(
            decision=AnswerabilityDecision.NEEDS_REVIEW,
            answer=FALLBACK_ANSWER_VI,
            llm_called=False,
            citations=[],
        ),
    )

    report = build_generation_eval_report(
        cases=[generated, reviewed_fallback],
        started_at=datetime.now(UTC),
        dataset_path=Path("data/eval/test.jsonl"),
        collection_name="collection",
        vector_name="dense",
        top_k=20,
        provider="openrouter",
        model="test/model",
    )

    assert report.citation_id_coverage_rate == 1.0


def test_manual_review_and_caution_metrics_are_aggregated() -> None:
    """Review, caution, and selection warning signals remain non-semantic metrics."""
    reviewed = validate_generation_result(
        _review_case(),
        _result(
            answer="Quyền dân sự được pháp luật bảo vệ [E1].",
            citations=[_citation()],
            selection_metadata={
                "selected_count": 2,
                "caution_selected_count": 2,
            },
            selection_warnings=["all_selected_evidence_has_caution"],
        ),
    )

    report = build_generation_eval_report(
        cases=[reviewed],
        started_at=datetime.now(UTC),
        dataset_path=Path("data/eval/test.jsonl"),
        collection_name="collection",
        vector_name="dense",
        top_k=20,
        provider="openrouter",
        model="test/model",
    )

    assert report.manual_review_required_count == 1
    assert report.non_blocking_case_count == 1
    assert report.total_caution_selected_count == 2
    assert report.cases_with_all_caution_evidence == 1
    assert report.selection_warning_count == 1


def test_evidence_preview_uses_only_redacted_bounded_citable_text() -> None:
    """Preview excludes parent content, redacts secrets, and records truncation."""
    preview = build_evidence_preview(
        _used_evidence(
            safe_citable_text="sk-or-example " + ("x" * 80),
            auxiliary_context_present=True,
            parent_context_included_in_prompt=True,
        ),
        max_chars=40,
    )

    assert preview.text_preview_truncated is True
    assert len(preview.text_preview or "") == 43
    assert "sk-or-" not in (preview.text_preview or "")
    assert "[REDACTED]" in (preview.text_preview or "")
    assert preview.auxiliary_context_present is True
    assert preview.parent_context_included_in_prompt is True
    assert "parent_text" not in preview.model_dump()


def test_case_maps_cited_ids_to_evidence_previews() -> None:
    """Generated [E#] IDs map to selected preview records."""
    evaluated = validate_generation_result(
        _allowed_case(),
        _result(
            answer="Nội dung hợp lệ [E1].",
            citations=[_citation()],
            used_evidence=[_used_evidence()],
        ),
        include_evidence_preview=True,
        evidence_preview_chars=500,
    )

    assert evaluated.evidence_preview_count == 1
    assert evaluated.cited_evidence_preview_count == 1
    assert evaluated.all_cited_ids_have_preview is True
    assert evaluated.evidence_preview_missing_count == 0
    assert evaluated.cited_evidence_previews[0].evidence_id == "E1"


def test_missing_cited_evidence_preview_is_readiness_metric_only() -> None:
    """A missing preview is reported without weakening citation validation."""
    evaluated = validate_generation_result(
        _allowed_case(),
        _result(
            answer="Nội dung hợp lệ [E1].",
            citations=[_citation()],
            used_evidence=[],
        ),
        include_evidence_preview=True,
    )

    assert evaluated.passed is True
    assert evaluated.all_cited_ids_have_preview is False
    assert evaluated.evidence_preview_missing_count == 1


def test_evidence_preview_report_metrics_are_aggregated() -> None:
    """Report readiness metrics summarize available and missing previews."""
    available = validate_generation_result(
        _allowed_case(),
        _result(
            answer="Nội dung [E1].",
            citations=[_citation()],
            used_evidence=[_used_evidence()],
        ),
        include_evidence_preview=True,
    )
    missing = validate_generation_result(
        _allowed_case(case_id="missing-preview"),
        _result(answer="Nội dung [E1].", citations=[_citation()]),
        include_evidence_preview=True,
    )

    report = build_generation_eval_report(
        cases=[available, missing],
        started_at=datetime.now(UTC),
        dataset_path=Path("data/eval/test.jsonl"),
        collection_name="collection",
        vector_name="dense",
        top_k=20,
        provider="openrouter",
        model="test/model",
    )

    assert report.evidence_preview_case_count == 1
    assert report.evidence_preview_total_count == 1
    assert report.cited_evidence_preview_total_count == 1
    assert report.evidence_preview_missing_count == 1
    assert report.all_cited_ids_have_preview_rate == 0.5
    assert report.cases_missing_evidence_preview == ["missing-preview"]


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


def _review_case() -> GenerationEvalQuery:
    return GenerationEvalQuery(
        id="review",
        query="Quyền dân sự được công nhận và bảo vệ như thế nào?",
        allowed_decisions=[
            AnswerabilityDecision.ANSWER_ALLOWED,
            AnswerabilityDecision.NEEDS_REVIEW,
        ],
        expected_llm_called=None,
        requires_citation_ids=True,
        expected_language="vi",
        manual_review_required=True,
        blocking=False,
    )


def _result(
    *,
    decision: AnswerabilityDecision = AnswerabilityDecision.ANSWER_ALLOWED,
    answer: str,
    llm_called: bool = True,
    citations: list[RagCitation],
    citation_issues: list[CitationIssue] | None = None,
    selection_metadata: dict[str, object] | None = None,
    selection_warnings: list[str] | None = None,
    used_evidence: list[UsedEvidence] | None = None,
) -> RagAnswerResult:
    return RagAnswerResult(
        query="Câu hỏi",
        decision=decision,
        answer=answer,
        citations=citations,
        used_evidence=used_evidence or [],
        fallback_reasons=[],
        selection_warnings=selection_warnings or [],
        citation_issues=citation_issues or [],
        retrieval_metadata={},
        selection_metadata=selection_metadata or {},
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


def _used_evidence(
    *,
    safe_citable_text: str = "Quyền dân sự được pháp luật bảo vệ.",
    auxiliary_context_present: bool = False,
    parent_context_included_in_prompt: bool = False,
) -> UsedEvidence:
    return UsedEvidence(
        evidence_id="E1",
        packet_id="P1",
        chunk_id="chunk-1",
        citation="Điều 1",
        law_id="BLDS_2015",
        law_title="Bộ luật Dân sự 2015",
        article_number="1",
        source_url="https://thuvienphapluat.vn/test",
        citation_scope="child_exact",
        safety_level="caution",
        is_directly_citable=True,
        safe_citable_text=safe_citable_text,
        auxiliary_context_present=auxiliary_context_present,
        parent_context_included_in_prompt=parent_context_included_in_prompt,
    )
