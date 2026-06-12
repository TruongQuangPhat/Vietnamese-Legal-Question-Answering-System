"""Unit tests for Phase 9B generation result and citation guard helpers."""

from __future__ import annotations

from src.retrieval.generation import (
    FALLBACK_ANSWER_VI,
    CitationIssueSeverity,
    build_fallback_result,
    check_generated_citations,
)
from src.retrieval.prompting import PromptEvidence
from src.retrieval.selection import AnswerabilityDecision


def test_generated_answer_with_known_citation_maps_to_evidence() -> None:
    """Known [E#] IDs are mapped back to selected evidence citation metadata."""
    evidence = [_prompt_evidence("E1")]

    result = check_generated_citations(
        answer="Theo quy định được cung cấp, quyền này được bảo vệ [E1].",
        prompt_evidence=evidence,
    )

    assert result.cited_ids == ["E1"]
    assert len(result.valid_citations) == 1
    assert result.valid_citations[0].citation == "Điều 2, Bộ luật Dân sự 2015"
    assert result.issues == []


def test_generated_answer_with_unknown_citation_creates_issue() -> None:
    """Unknown [E#] IDs are not accepted as traceable citations."""
    result = check_generated_citations(
        answer="Nội dung không có trong bằng chứng [E99].",
        prompt_evidence=[_prompt_evidence("E1")],
    )

    assert result.valid_citations == []
    assert result.issues[0].code == "unknown_citation_id"
    assert result.issues[0].severity == CitationIssueSeverity.ERROR


def test_generated_answer_without_citation_creates_warning() -> None:
    """A non-empty legal answer without any [E#] citation receives a warning."""
    result = check_generated_citations(
        answer="Quyền dân sự được pháp luật bảo vệ.",
        prompt_evidence=[_prompt_evidence("E1")],
    )

    assert result.cited_ids == []
    assert result.issues[0].code == "missing_citation_id"
    assert result.issues[0].severity == CitationIssueSeverity.WARNING


def test_fallback_result_is_deterministic_and_does_not_claim_citations() -> None:
    """Fallback results should not include generated citations or LLM metadata."""
    result = build_fallback_result(
        query="Người lao động được nghỉ hằng năm bao nhiêu ngày?",
        decision=AnswerabilityDecision.FALLBACK_REQUIRED,
    )

    assert result.answer == FALLBACK_ANSWER_VI
    assert result.llm_called is False
    assert result.citations == []
    assert result.generation_metadata["fallback"] is True


def _prompt_evidence(evidence_id: str) -> PromptEvidence:
    return PromptEvidence(
        evidence_id=evidence_id,
        packet_id="P1",
        chunk_id="chunk-1",
        citation="Điều 2, Bộ luật Dân sự 2015",
        law_id="BLDS_2015",
        law_title="Bộ luật Dân sự 2015",
        article_number="2",
        source_url="https://thuvienphapluat.vn/test",
        citable_text="Quyền dân sự được công nhận, tôn trọng, bảo vệ.",
    )
