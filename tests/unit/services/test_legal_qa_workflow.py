from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.api.dependencies import clear_legal_qa_service_cache, get_legal_qa_service
from src.api.schemas import LegalQARequest
from src.api.settings import get_settings
from src.retrieval.generation import FALLBACK_ANSWER_VI, RagAnswerResult, RagCitation
from src.retrieval.llm_client import LLMResponse, MockLLMClient
from src.retrieval.models import RetrievalResult, RetrievedChunk
from src.retrieval.selection import AnswerabilityDecision
from src.services.legal_qa_api_service import (
    FakeLegalQAWorkflow,
    LegalQAService,
    LegalQAWorkflowRequest,
)
from src.services.legal_qa_context import LegalQAContextPreparer
from src.services.legal_qa_workflow import (
    LegalQARuntimeSettings,
    LegalQAServiceMode,
    RealLegalQAWorkflow,
    build_legal_qa_service,
)


class StaticRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "collection_name": collection_name,
            }
        )
        return self.result.model_copy(update={"query": query})


def test_real_workflow_adapter_maps_answered_result_with_citations() -> None:
    retriever = StaticRetriever(_retrieval_result([_retrieved_chunk()]))
    llm_client = MockLLMClient(
        [
            LLMResponse(
                text="Người lao động có quyền theo căn cứ đã chọn [E1].",
                model="google/gemini-2.5-flash",
                provider="openrouter",
                latency_ms=12.0,
                finish_reason="stop",
            )
        ]
    )
    workflow = RealLegalQAWorkflow(
        retriever=retriever,
        llm_client=llm_client,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )

    response = workflow.run(
        LegalQAWorkflowRequest(
            request_id="request-1",
            question="Vậy hợp đồng xác định thời hạn thì sao?",
            top_k=10,
            context=LegalQAContextPreparer().prepare(
                LegalQARequest(
                    question="Vậy hợp đồng xác định thời hạn thì sao?",
                    conversation_context=[
                        {
                            "role": "user",
                            "content": (
                                "Người lao động được quyền đơn phương chấm dứt hợp đồng khi nào?"
                            ),
                        }
                    ],
                )
            ),
        )
    )

    assert response.decision == "answered"
    assert response.answer == "Người lao động có quyền theo căn cứ đã chọn [E1]."
    assert response.citations[0].evidence_id == "E1"
    assert response.citations[0].chunk_id == "chunk-001"
    assert response.citations[0].law_id == "BLLD_2019"
    assert response.citations[0].law_name == "Bộ luật Lao động 2019"
    assert response.citations[0].citation == "Khoản 1 Điều 35 Bộ luật Lao động 2019"
    assert str(response.citations[0].source_url) == ("https://thuvienphapluat.vn/van-ban/lao-dong/")
    assert response.evidence[0].text == "Người lao động có quyền đơn phương chấm dứt."
    assert response.metadata.retrieval_strategy == "coverage_aware_quota"
    assert response.metadata.model == "google/gemini-2.5-flash"
    assert retriever.calls[0]["query"] == (
        "Người lao động được quyền đơn phương chấm dứt hợp đồng khi nào? "
        "Vậy hợp đồng xác định thời hạn thì sao?"
    )


def test_real_workflow_adapter_maps_fallback_result() -> None:
    retriever = StaticRetriever(_retrieval_result([]))
    llm_client = MockLLMClient([])
    workflow = RealLegalQAWorkflow(
        retriever=retriever,
        llm_client=llm_client,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )

    response = workflow.run(
        LegalQAWorkflowRequest(
            request_id="request-1",
            question="Câu hỏi ngoài phạm vi?",
            top_k=10,
        )
    )

    assert response.decision == "fallback"
    assert response.answer == FALLBACK_ANSWER_VI
    assert response.citations == []
    assert response.evidence == []
    assert "no_evidence" in response.warnings
    assert not llm_client.requests


def test_real_workflow_adapter_does_not_mark_reranking_used() -> None:
    retriever = StaticRetriever(_retrieval_result([]))
    workflow = RealLegalQAWorkflow(
        retriever=retriever,
        llm_client=MockLLMClient([]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )

    response = workflow.run(
        LegalQAWorkflowRequest(
            request_id="request-1",
            question="Câu hỏi ngoài phạm vi?",
            top_k=10,
        )
    )

    assert response.metadata.reranking_used is False


async def test_real_workflow_adapter_rejects_active_event_loop() -> None:
    async def fallback_runner(**_: Any) -> RagAnswerResult:
        return RagAnswerResult(
            query="Câu hỏi hợp lệ?",
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            answer=FALLBACK_ANSWER_VI,
            fallback_reasons=["no_evidence"],
            model="google/gemini-2.5-flash",
            provider="openrouter",
        )

    workflow = RealLegalQAWorkflow(
        retriever=StaticRetriever(_retrieval_result([])),
        llm_client=MockLLMClient([]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        runner=fallback_runner,
    )

    with pytest.raises(RuntimeError, match="worker thread or async adapter"):
        workflow.run(
            LegalQAWorkflowRequest(
                request_id="request-1",
                question="Câu hỏi hợp lệ?",
                top_k=10,
            )
        )


def test_real_workflow_adapter_falls_back_when_answer_lacks_traceable_citations() -> None:
    async def untraceable_answer_runner(**_: Any) -> RagAnswerResult:
        return RagAnswerResult(
            query="Câu hỏi hợp lệ?",
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            answer="Câu trả lời không đủ truy vết [E1].",
            citations=[RagCitation(evidence_id="E1", packet_id="P1")],
            used_evidence=[],
            model="google/gemini-2.5-flash",
            provider="openrouter",
            llm_called=True,
        )

    workflow = RealLegalQAWorkflow(
        retriever=StaticRetriever(_retrieval_result([])),
        llm_client=MockLLMClient([]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        runner=untraceable_answer_runner,
    )

    response = workflow.run(
        LegalQAWorkflowRequest(
            request_id="request-1",
            question="Câu hỏi hợp lệ?",
            top_k=10,
        )
    )

    assert response.decision == "fallback"
    assert response.answer == FALLBACK_ANSWER_VI
    assert response.citations == []
    assert response.evidence == []
    assert "missing_citation_chunk_id" in response.warnings
    assert "missing_citation_source_url" in response.warnings


async def test_dependency_provider_uses_fake_workflow_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LEGAL_QA_SERVICE_MODE", raising=False)
    get_settings.cache_clear()
    clear_legal_qa_service_cache()

    service = await get_legal_qa_service()

    response = service.answer(LegalQARequest(question="Câu hỏi hợp lệ?"))
    assert response.decision == "answered"
    assert response.metadata.model == "stub"


def test_service_factory_can_select_real_workflow_with_mocked_dependencies() -> None:
    class MockWorkflow:
        def run(self, request: LegalQAWorkflowRequest):
            return FakeLegalQAWorkflow().run(request)

    settings = LegalQARuntimeSettings(service_mode=LegalQAServiceMode.REAL)

    service = build_legal_qa_service(
        settings=settings,
        real_workflow_builder=lambda runtime_settings: MockWorkflow(),
    )

    assert isinstance(service, LegalQAService)
    response = service.answer(LegalQARequest(question="Câu hỏi hợp lệ?"))
    assert response.decision == "answered"
    assert response.metadata.model == "stub"


def test_route_contract_remains_stable_with_workflow_service() -> None:
    retriever = StaticRetriever(_retrieval_result([_retrieved_chunk()]))
    llm_client = MockLLMClient(
        [
            LLMResponse(
                text="Câu trả lời có căn cứ [E1].",
                model="google/gemini-2.5-flash",
                provider="openrouter",
                latency_ms=9.0,
            )
        ]
    )
    service = LegalQAService(
        workflow=RealLegalQAWorkflow(
            retriever=retriever,
            llm_client=llm_client,
            collection_name="vnlaw_chunks_bgem3_v1_full",
        )
    )

    response = service.answer(LegalQARequest(question="Câu hỏi hợp lệ?"))

    assert response.model_dump(mode="json").keys() == {
        "request_id",
        "decision",
        "answer",
        "citations",
        "evidence",
        "warnings",
        "metadata",
    }


def _retrieval_result(chunks: list[RetrievedChunk]) -> RetrievalResult:
    return RetrievalResult(
        query="Câu hỏi hợp lệ?",
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
        top_k=10,
        elapsed_ms=1.0,
        query_vector_dimension=1024,
        results=chunks,
        issues=[],
    )


def _retrieved_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        rank=1,
        score=0.95,
        chunk_id="chunk-001",
        law_id="BLLD_2019",
        law_name="Bộ luật Lao động 2019",
        level="clause",
        chunk_kind="clause",
        article_number="35",
        clause_number="1",
        citation="Khoản 1 Điều 35 Bộ luật Lao động 2019",
        text="Người lao động có quyền đơn phương chấm dứt.",
        source_url="https://thuvienphapluat.vn/van-ban/lao-dong/",
        source_domain="thuvienphapluat.vn",
    )
