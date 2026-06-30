from __future__ import annotations

from src.api.schemas import LegalQARequest
from src.services.legal_qa_api_service import (
    LegalQAService,
    LegalQAWorkflowCitation,
    LegalQAWorkflowDecision,
    LegalQAWorkflowEvidence,
    LegalQAWorkflowMetadata,
    LegalQAWorkflowRequest,
    LegalQAWorkflowResult,
)


class StaticLegalQAWorkflow:
    def __init__(self, result: LegalQAWorkflowResult) -> None:
        self.result = result
        self.requests: list[LegalQAWorkflowRequest] = []

    def run(self, request: LegalQAWorkflowRequest) -> LegalQAWorkflowResult:
        self.requests.append(request)
        return self.result


def test_service_maps_answered_workflow_result_to_response() -> None:
    workflow = StaticLegalQAWorkflow(_answered_result())
    service = LegalQAService(workflow=workflow)

    response = service.answer(LegalQARequest(question="  Khi nào được nghỉ việc?  "))

    assert response.decision == "answered"
    assert response.answer == "Câu trả lời dựa trên bằng chứng [E1]."
    assert response.citations[0].evidence_id == "E1"
    assert response.evidence[0].evidence_id == "E1"
    assert response.metadata.retrieval_strategy == "coverage_aware_quota"
    assert response.metadata.model == "fake-workflow"
    assert response.metadata.reranking_used is False
    assert workflow.requests[0].request_id == response.request_id
    assert workflow.requests[0].question == "Khi nào được nghỉ việc?"
    assert workflow.requests[0].top_k == 10


def test_service_passes_prepared_context_without_rewriting_question() -> None:
    workflow = StaticLegalQAWorkflow(_answered_result())
    service = LegalQAService(workflow=workflow)

    response = service.answer(
        LegalQARequest(
            question="Vậy hợp đồng xác định thời hạn thì sao?",
            conversation_id="conversation-1",
            conversation_context=[
                {"role": "user", "content": "  Câu hỏi trước  "},
                {"role": "assistant", "content": "  Câu trả lời trước  "},
            ],
        )
    )

    workflow_request = workflow.requests[0]
    assert response.decision == "answered"
    assert workflow_request.question == "Vậy hợp đồng xác định thời hạn thì sao?"
    assert workflow_request.context is not None
    assert workflow_request.context.conversation_id == "conversation-1"
    assert workflow_request.context.message_count == 2
    assert [message.content for message in workflow_request.context.messages] == [
        "Câu hỏi trước",
        "Câu trả lời trước",
    ]


def test_fake_response_is_stable_with_conversation_context() -> None:
    service = LegalQAService()

    without_context = service.answer(LegalQARequest(question="Câu hỏi hợp lệ?"))
    with_context = service.answer(
        LegalQARequest(
            question="Câu hỏi hợp lệ?",
            conversation_context=[
                {"role": "user", "content": "Câu hỏi trước"},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    assert with_context.model_copy(update={"request_id": without_context.request_id}) == (
        without_context
    )


def test_service_maps_fallback_workflow_result_to_response() -> None:
    workflow = StaticLegalQAWorkflow(
        LegalQAWorkflowResult(
            decision=LegalQAWorkflowDecision.FALLBACK,
            answer="Không tìm thấy đủ căn cứ pháp lý trong nguồn hiện có.",
            citations=[_workflow_citation()],
            evidence=[_workflow_evidence()],
            warnings=["insufficient_evidence"],
            metadata=LegalQAWorkflowMetadata(model=None, latency_ms=5),
        )
    )
    service = LegalQAService(workflow=workflow)

    response = service.answer(LegalQARequest(question="Câu hỏi ngoài phạm vi?"))

    assert response.decision == "fallback"
    assert response.citations == []
    assert response.evidence == []
    assert response.warnings == ["insufficient_evidence", "fallback"]
    assert response.metadata.model is None
    assert response.metadata.latency_ms == 5


def test_service_hides_evidence_when_requested() -> None:
    service = LegalQAService(workflow=StaticLegalQAWorkflow(_answered_result()))

    response = service.answer(
        LegalQARequest(question="Khi nào được nghỉ việc?", include_evidence=False)
    )

    assert response.citations
    assert response.evidence == []


def test_service_preserves_citation_fields() -> None:
    service = LegalQAService(workflow=StaticLegalQAWorkflow(_answered_result()))

    response = service.answer(LegalQARequest(question="Khi nào được nghỉ việc?"))

    citation = response.citations[0]
    assert citation.evidence_id == "E1"
    assert citation.chunk_id == "chunk-001"
    assert citation.law_id == "law-001"
    assert citation.law_name == "Bộ luật Lao động"
    assert citation.citation == "Khoản 1 Điều 35 Bộ luật Lao động"
    assert str(citation.source_url) == "https://thuvienphapluat.vn/van-ban/lao-dong/"
    assert citation.hierarchy_path == "Điều 35 > Khoản 1"


def test_service_attaches_request_id() -> None:
    workflow = StaticLegalQAWorkflow(_answered_result())
    service = LegalQAService(workflow=workflow)

    response = service.answer(LegalQARequest(question="Khi nào được nghỉ việc?"))

    assert response.request_id
    assert workflow.requests[0].request_id == response.request_id


def _answered_result() -> LegalQAWorkflowResult:
    return LegalQAWorkflowResult(
        decision=LegalQAWorkflowDecision.ANSWERED,
        answer="Câu trả lời dựa trên bằng chứng [E1].",
        citations=[_workflow_citation()],
        evidence=[_workflow_evidence()],
        warnings=[],
        metadata=LegalQAWorkflowMetadata(
            retrieval_strategy="coverage_aware_quota",
            model="fake-workflow",
            reranking_used=False,
            latency_ms=7,
        ),
    )


def _workflow_citation() -> LegalQAWorkflowCitation:
    return LegalQAWorkflowCitation(
        evidence_id="E1",
        chunk_id="chunk-001",
        law_id="law-001",
        law_name="Bộ luật Lao động",
        citation="Khoản 1 Điều 35 Bộ luật Lao động",
        source_url="https://thuvienphapluat.vn/van-ban/lao-dong/",
        hierarchy_path="Điều 35 > Khoản 1",
    )


def _workflow_evidence() -> LegalQAWorkflowEvidence:
    return LegalQAWorkflowEvidence(
        evidence_id="E1",
        chunk_id="chunk-001",
        law_id="law-001",
        law_name="Bộ luật Lao động",
        citation="Khoản 1 Điều 35 Bộ luật Lao động",
        text="Người lao động có quyền đơn phương chấm dứt hợp đồng theo luật.",
        source_url="https://thuvienphapluat.vn/van-ban/lao-dong/",
        score=0.91,
    )
