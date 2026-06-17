"""Unit tests for fallback-aware Naive RAG Naive RAG prompt construction."""

from __future__ import annotations

import pytest

from src.retrieval.evidence import (
    CitationScope,
    EvidenceCitation,
    EvidencePacket,
    EvidenceSafetyLevel,
    EvidenceText,
    ParentContextPolicy,
)
from src.retrieval.prompting import build_naive_rag_prompt
from src.retrieval.selection import (
    AnswerabilityDecision,
    EvidenceSelectionResult,
    SelectedEvidence,
)


def test_prompt_uses_selected_evidence_only() -> None:
    """Rejected or unselected text must not appear in the LLM prompt."""
    selected = _selection_result([_selected(_packet(text="Văn bản được chọn"))])

    prompt = build_naive_rag_prompt(
        query="Quyền dân sự được bảo vệ thế nào?",
        selection_result=selected,
    )

    assert "[E1]" in prompt.user_message
    assert "Văn bản được chọn" in prompt.user_message
    assert "rejected" not in prompt.user_message.casefold()
    assert prompt.evidence[0].evidence_id == "E1"


def test_prompt_labels_auxiliary_context_as_not_directly_citable() -> None:
    """Auxiliary parent context is visible but explicitly non-citable."""
    selected = _selection_result(
        [
            _selected(
                _packet(
                    text="Khoản con được chọn",
                    auxiliary="Điều cha rộng hơn không được trích dẫn trực tiếp",
                )
            )
        ]
    )

    prompt = build_naive_rag_prompt(query="Câu hỏi", selection_result=selected)

    assert "Auxiliary context, not directly citable" in prompt.user_message
    assert "Điều cha rộng hơn" in prompt.user_message
    assert "Không xem Auxiliary context là căn cứ trích dẫn trực tiếp" in prompt.system_message


def test_prompt_can_suppress_auxiliary_context() -> None:
    """The generation config can keep parent context out of the prompt."""
    selected = _selection_result([_selected(_packet(text="Citable", auxiliary="Parent context"))])

    prompt = build_naive_rag_prompt(
        query="Câu hỏi",
        selection_result=selected,
        include_auxiliary_context=False,
    )

    assert "Citable" in prompt.user_message
    assert "Parent context" not in prompt.user_message


def test_prompt_rejects_empty_selected_evidence() -> None:
    """A generation prompt requires at least one selected citable packet."""
    result = EvidenceSelectionResult(
        decision=AnswerabilityDecision.ANSWER_ALLOWED,
        selected_evidence=[],
        rejected_evidence=[],
        fallback_reasons=[],
        warnings=[],
        rendered_context="",
        selected_count=0,
        rejected_count=0,
        unsafe_rejected_count=0,
        caution_selected_count=0,
    )

    with pytest.raises(ValueError, match="selected citable evidence"):
        build_naive_rag_prompt(query="Câu hỏi", selection_result=result)


def _packet(
    *,
    text: str,
    auxiliary: str | None = None,
    rank: int = 1,
) -> EvidencePacket:
    safe_text = EvidenceText(text=text, original_chars=len(text), max_chars=2000)
    auxiliary_text = (
        EvidenceText(text=auxiliary, original_chars=len(auxiliary), max_chars=4000)
        if auxiliary
        else None
    )
    return EvidencePacket(
        packet_id=f"P{rank}",
        rank=rank,
        score=0.9,
        chunk_id=f"chunk-{rank}",
        law_id="BLDS_2015",
        law_title="Bộ luật Dân sự 2015",
        citation=f"Điều {rank}, Bộ luật Dân sự 2015",
        article_number=str(rank),
        clause_number=None,
        point_label=None,
        level="article",
        chunk_kind="article",
        source_url="https://thuvienphapluat.vn/test",
        source_domain="thuvienphapluat.vn",
        citation_metadata=EvidenceCitation(
            citation=f"Điều {rank}, Bộ luật Dân sự 2015",
            law_id="BLDS_2015",
            law_title="Bộ luật Dân sự 2015",
            article_number=str(rank),
            source_url="https://thuvienphapluat.vn/test",
            source_domain="thuvienphapluat.vn",
        ),
        child_text=safe_text,
        parent_text=auxiliary_text,
        safe_citable_text=safe_text,
        auxiliary_context=auxiliary_text,
        citation_scope=(
            CitationScope.UNSAFE_PARENT_CONTEXT if auxiliary_text else CitationScope.ARTICLE_CONTEXT
        ),
        parent_context_policy=(
            ParentContextPolicy.AUXILIARY_ONLY
            if auxiliary_text
            else ParentContextPolicy.CITABLE_ARTICLE_CONTEXT
        ),
        safety_level=EvidenceSafetyLevel.CAUTION if auxiliary_text else EvidenceSafetyLevel.SAFE,
        safety_issues=[],
        metadata={},
        warnings=[],
    )


def _selected(packet: EvidencePacket) -> SelectedEvidence:
    return SelectedEvidence(
        packet=packet,
        packet_id=packet.packet_id,
        rank=packet.rank,
        score=packet.score,
        chunk_id=packet.chunk_id,
        citation=packet.citation,
        safety_level=packet.safety_level,
        citation_scope=packet.citation_scope,
        has_auxiliary_context=packet.auxiliary_context is not None,
        warnings=[],
    )


def _selection_result(selected: list[SelectedEvidence]) -> EvidenceSelectionResult:
    return EvidenceSelectionResult(
        decision=AnswerabilityDecision.ANSWER_ALLOWED,
        selected_evidence=selected,
        rejected_evidence=[],
        fallback_reasons=[],
        warnings=[],
        rendered_context="",
        selected_count=len(selected),
        rejected_count=0,
        unsafe_rejected_count=0,
        caution_selected_count=sum(
            1 for item in selected if item.safety_level == EvidenceSafetyLevel.CAUTION
        ),
    )
