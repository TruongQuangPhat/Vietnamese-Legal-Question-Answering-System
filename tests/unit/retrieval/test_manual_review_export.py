"""Unit tests for the offline manual review manual review exporter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.retrieval.generation_evaluation import (
    EvidencePreview,
    GenerationEvalCaseResult,
    GenerationEvalReport,
)
from src.retrieval.manual_review import render_manual_review, write_manual_review
from src.retrieval.selection import AnswerabilityDecision


def test_render_manual_review_includes_cases_claims_and_fallback() -> None:
    """Markdown contains generated and fallback review sections."""
    rendered = render_manual_review(_report())

    assert "allowed-case" in rendered
    assert "fallback-case" in rendered
    assert "Nội dung được hỗ trợ [E1]." in rendered
    assert "Claim-to-Citation Checklist" in rendered
    assert "Evidence Preview Table" in rendered
    assert "Nội dung Điều 1" in rendered
    assert "Fallback Review" in rendered
    assert "not_applicable_for_fallback" in rendered


def test_all_caution_case_is_flagged_for_priority_review() -> None:
    """All-caution evidence is visible in summary and case metadata."""
    rendered = render_manual_review(_report())

    assert "Priority review: `allowed-case`" in rendered
    assert "All selected evidence caution: `true`" in rendered


def test_truncated_answer_is_flagged() -> None:
    """Markdown makes source answer truncation explicit."""
    report = _report()
    report.cases[0].answer_preview_truncated = True

    rendered = render_manual_review(report)

    assert "Answer truncated: `true`" in rendered
    assert "Preview truncated" in rendered


def test_write_manual_review_rejects_secret_like_content(tmp_path: Path) -> None:
    """Unsafe authentication content is never written to an artifact."""
    output = tmp_path / "review.md"

    with pytest.raises(ValueError, match="unsafe"):
        write_manual_review(output, "unsafe provider credential marker: sk-or-example")

    assert not output.exists()


def test_write_manual_review_creates_markdown_without_external_calls(
    tmp_path: Path,
) -> None:
    """Exporter writes local Markdown and has no infrastructure dependencies."""
    output = tmp_path / "review.md"

    write_manual_review(output, render_manual_review(_report()))

    assert output.is_file()
    assert "allowed-case" in output.read_text(encoding="utf-8")


def _report() -> GenerationEvalReport:
    now = datetime.now(UTC).isoformat()
    cases = [_allowed_case(), _fallback_case()]
    return GenerationEvalReport(
        status="expanded_generation_eval_passed",
        started_at=now,
        finished_at=now,
        dataset_path="data/eval/test.jsonl",
        collection_name="test",
        vector_name="dense",
        top_k=20,
        provider="mock",
        model="test/model",
        total_cases=2,
        passed_cases=2,
        failed_cases=0,
        blocking_case_count=2,
        non_blocking_case_count=0,
        blocking_failed_cases=0,
        manual_review_required_count=0,
        decision_pass_rate=1.0,
        llm_call_policy_pass_rate=1.0,
        citation_id_coverage_rate=1.0,
        unknown_citation_id_count=0,
        missing_citation_id_count=0,
        fallback_policy_pass_rate=1.0,
        vietnamese_language_pass_rate=1.0,
        forbidden_phrase_failures=0,
        secret_leak_failures=0,
        total_caution_selected_count=1,
        cases_with_all_caution_evidence=1,
        selection_warning_count=1,
        evidence_preview_case_count=1,
        evidence_preview_total_count=1,
        cited_evidence_preview_total_count=1,
        evidence_preview_missing_count=0,
        all_cited_ids_have_preview_rate=1.0,
        cases=cases,
    )


def _allowed_case() -> GenerationEvalCaseResult:
    return GenerationEvalCaseResult(
        id="allowed-case",
        query="Quy định này là gì?",
        passed=True,
        allowed_decisions=[AnswerabilityDecision.ANSWER_ALLOWED],
        decision=AnswerabilityDecision.ANSWER_ALLOWED,
        decision_passed=True,
        expected_llm_called=True,
        llm_called=True,
        llm_call_policy_passed=True,
        fallback_policy_passed=True,
        requires_citation_ids=True,
        citation_id_coverage_applicable=True,
        citation_id_coverage_passed=True,
        citation_count=1,
        citation_issue_count=0,
        unknown_citation_id_count=0,
        missing_citation_id_count=0,
        vietnamese_language_passed=True,
        selection_warnings=["all_selected_evidence_caution"],
        selected_evidence_count=1,
        caution_selected_count=1,
        all_selected_evidence_caution=True,
        manual_review_required=False,
        blocking=True,
        evidence_previews=[_preview()],
        cited_evidence_previews=[_preview()],
        evidence_preview_count=1,
        cited_evidence_preview_count=1,
        answer_preview="Nội dung được hỗ trợ [E1].",
        provider="mock",
        model="test/model",
        pipeline_error_count=0,
    )


def _preview() -> EvidencePreview:
    return EvidencePreview(
        evidence_id="E1",
        packet_id="P1",
        citation="Điều 1, Bộ luật Dân sự 2015",
        citation_scope="child_exact",
        safety_level="caution",
        is_directly_citable=True,
        text_preview="Nội dung Điều 1",
        source_url="https://thuvienphapluat.vn/test",
        auxiliary_context_present=True,
        parent_context_included_in_prompt=True,
    )


def _fallback_case() -> GenerationEvalCaseResult:
    return GenerationEvalCaseResult(
        id="fallback-case",
        query="Câu hỏi chưa đủ căn cứ?",
        passed=True,
        allowed_decisions=[AnswerabilityDecision.FALLBACK_REQUIRED],
        decision=AnswerabilityDecision.FALLBACK_REQUIRED,
        decision_passed=True,
        expected_llm_called=False,
        llm_called=False,
        llm_call_policy_passed=True,
        fallback_policy_passed=True,
        requires_citation_ids=False,
        citation_id_coverage_applicable=False,
        citation_id_coverage_passed=True,
        citation_count=0,
        citation_issue_count=0,
        unknown_citation_id_count=0,
        missing_citation_id_count=0,
        vietnamese_language_passed=True,
        fallback_reasons=["insufficient_evidence"],
        selected_evidence_count=0,
        caution_selected_count=0,
        all_selected_evidence_caution=False,
        manual_review_required=False,
        blocking=True,
        answer_preview="Hệ thống chưa có đủ căn cứ pháp lý để trả lời.",
        provider="mock",
        model=None,
        pipeline_error_count=0,
    )
