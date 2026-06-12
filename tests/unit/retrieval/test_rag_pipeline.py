"""Unit tests for Phase 9B fallback-aware Naive RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.retrieval.evaluation import ExpectedTarget
from src.retrieval.generation import RagGenerationConfig
from src.retrieval.llm_client import LLMResponse, MockLLMClient
from src.retrieval.models import RetrievalResult, RetrievedChunk
from src.retrieval.rag_pipeline import run_naive_rag
from src.retrieval.selection import AnswerabilityDecision, EvidenceSelectionConfig


@dataclass
class FakeRetriever:
    """Minimal retriever test double returning a configured retrieval result."""

    result: RetrievalResult
    calls: int = 0

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        self.calls += 1
        return self.result


@pytest.mark.asyncio
async def test_fallback_required_selection_does_not_call_llm() -> None:
    """Missing expected Clause/Point evidence should fallback before generation."""
    retriever = FakeRetriever(
        _result(
            [
                _chunk(
                    law_id="BLLD_VBHN",
                    article_number="113",
                    clause_number="4",
                    text="4. Người sử dụng lao động có trách nhiệm...",
                    parent_text="Điều 113. Nghỉ hằng năm ... 1. Người lao động được nghỉ...",
                )
            ],
            query="Người lao động được nghỉ hằng năm bao nhiêu ngày?",
        )
    )
    llm = MockLLMClient([_llm_response("Không được gọi [E1]")])

    result = await run_naive_rag(
        query=retriever.result.query,
        retriever=retriever,
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
        expected_targets=[
            ExpectedTarget(
                law_id="BLLD_VBHN",
                article_number="113",
                clause_number="1",
                point_label=None,
                match_level="clause",
            )
        ],
    )

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert result.llm_called is False
    assert llm.requests == []
    assert "exact_target_missing_in_eval_mode" in result.fallback_reasons


@pytest.mark.asyncio
async def test_needs_review_selection_does_not_call_llm() -> None:
    """needs_review is not answer_allowed and must not trigger generation."""
    retriever = FakeRetriever(
        _result(
            [
                _chunk(
                    law_id="BLLD_VBHN",
                    article_number="113",
                    clause_number="4",
                    text="4. Người sử dụng lao động có trách nhiệm...",
                    parent_text="Điều 113. Nghỉ hằng năm ...",
                )
            ]
        )
    )
    llm = MockLLMClient([_llm_response("Không được gọi [E1]")])

    result = await run_naive_rag(
        query="Câu hỏi cần xem xét",
        retriever=retriever,
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
        selection_config=EvidenceSelectionConfig(
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=True,
            eval_missing_target_requires_fallback=False,
        ),
    )

    assert result.decision == AnswerabilityDecision.NEEDS_REVIEW
    assert result.llm_called is False
    assert llm.requests == []


@pytest.mark.asyncio
async def test_answer_allowed_selection_calls_llm_once_and_maps_citation() -> None:
    """Safe selected evidence should allow exactly one LLM call."""
    retriever = FakeRetriever(
        _result(
            [
                _chunk(
                    law_id="LBHYT_VBHN",
                    article_number="16",
                    clause_number="3",
                    point_label="d",
                    text="d) Trẻ em dưới 6 tuổi...",
                    citation="Điểm d, Khoản 3, Điều 16, Luật Bảo hiểm y tế",
                )
            ],
            query="Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?",
        )
    )
    llm = MockLLMClient([_llm_response("Trẻ em dưới 6 tuổi được cấp thẻ [E1].")])

    result = await run_naive_rag(
        query=retriever.result.query,
        retriever=retriever,
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
        expected_targets=[
            ExpectedTarget(
                law_id="LBHYT_VBHN",
                article_number="16",
                clause_number="3",
                point_label="d",
                match_level="point",
            )
        ],
    )

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.llm_called is True
    assert len(llm.requests) == 1
    assert result.citations[0].evidence_id == "E1"
    assert result.citations[0].citation == "Điểm d, Khoản 3, Điều 16, Luật Bảo hiểm y tế"


@pytest.mark.asyncio
async def test_prompt_sent_to_llm_excludes_rejected_unsafe_evidence() -> None:
    """Rejected unsafe text must never be sent to the model prompt."""
    retriever = FakeRetriever(
        _result(
            [
                _chunk(
                    rank=1,
                    chunk_id="unsafe",
                    citation=None,
                    text="UNSAFE rejected text",
                ),
                _chunk(
                    rank=2,
                    chunk_id="safe",
                    text="SAFE selected text",
                    citation="Điều 2, Bộ luật Dân sự 2015",
                ),
            ]
        )
    )
    llm = MockLLMClient([_llm_response("Câu trả lời [E1]")])

    result = await run_naive_rag(
        query="Quyền dân sự được bảo vệ thế nào?",
        retriever=retriever,
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )

    assert result.llm_called is True
    user_prompt = llm.requests[0].messages[1].content
    assert "SAFE selected text" in user_prompt
    assert "UNSAFE rejected text" not in user_prompt


@pytest.mark.asyncio
async def test_invalid_generated_citation_is_reported() -> None:
    """Unknown model citation IDs are surfaced in RagAnswerResult."""
    retriever = FakeRetriever(_result([_chunk(text="Citable text")]))
    llm = MockLLMClient([_llm_response("Câu trả lời [E99]")])

    result = await run_naive_rag(
        query="Câu hỏi",
        retriever=retriever,
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )

    assert result.llm_called is True
    assert result.citation_issues[0].code == "unknown_citation_id"


@pytest.mark.asyncio
async def test_strict_invalid_citation_returns_fallback() -> None:
    """Strict citation mode converts unknown citation IDs into fallback."""
    retriever = FakeRetriever(_result([_chunk(text="Citable text")]))
    llm = MockLLMClient([_llm_response("Câu trả lời [E99]")])

    result = await run_naive_rag(
        query="Câu hỏi",
        retriever=retriever,
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
    )

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert result.llm_called is False
    assert result.errors == ["generated answer cited unknown evidence ID [E99]"]


def _result(
    chunks: list[RetrievedChunk],
    *,
    query: str = "Quyền dân sự được bảo vệ thế nào?",
) -> RetrievalResult:
    return RetrievalResult(
        query=query,
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
        top_k=20,
        elapsed_ms=12.0,
        query_vector_dimension=1024,
        results=chunks,
        issues=[],
    )


def _chunk(
    *,
    rank: int = 1,
    score: float = 0.9,
    chunk_id: str = "chunk-1",
    law_id: str = "BLDS_2015",
    law_name: str = "Bộ luật Dân sự 2015",
    article_number: str = "2",
    clause_number: str | None = None,
    point_label: str | None = None,
    citation: str | None = "Điều 2, Bộ luật Dân sự 2015",
    text: str = "Quyền dân sự được công nhận, tôn trọng, bảo vệ.",
    parent_text: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=score,
        point_id=f"point-{rank}",
        chunk_id=chunk_id,
        law_id=law_id,
        law_name=law_name,
        level="article" if clause_number is None and point_label is None else "clause",
        chunk_kind="article" if clause_number is None and point_label is None else "clause",
        article_number=article_number,
        clause_number=clause_number,
        point_label=point_label,
        citation=citation,
        text=text,
        parent_text=parent_text,
        source_url="https://thuvienphapluat.vn/test",
        source_domain="thuvienphapluat.vn",
        metadata={},
        warnings=[],
        issues=[],
    )


def _llm_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        model="mock-model",
        provider="mock",
        latency_ms=2.0,
    )
