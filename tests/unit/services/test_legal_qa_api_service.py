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


def test_service_maps_answered_with_caution_workflow_result_to_response() -> None:
    workflow = StaticLegalQAWorkflow(
        LegalQAWorkflowResult(
            decision=LegalQAWorkflowDecision.ANSWERED_WITH_CAUTION,
            answer="Câu trả lời thận trọng dựa trên bằng chứng [E1].",
            citations=[_workflow_citation()],
            evidence=[_workflow_evidence()],
            warnings=["all_selected_evidence_caution"],
            metadata=LegalQAWorkflowMetadata(model="fake-workflow", latency_ms=7),
        )
    )
    service = LegalQAService(workflow=workflow)

    response = service.answer(LegalQARequest(question="Nghỉ phép năm bao nhiêu ngày?"))

    assert response.decision == "answered_with_caution"
    assert response.citations[0].evidence_id == "E1"
    assert response.evidence[0].score == 0.91
    assert response.warnings == ["all_selected_evidence_caution"]


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
    assert workflow_request.context.context_used is True
    assert workflow_request.context.follow_up_detected is True
    assert workflow_request.context.retrieval_question == (
        "Câu hỏi trước Vậy hợp đồng xác định thời hạn thì sao?"
    )
    assert [message.content for message in workflow_request.context.messages] == [
        "Câu hỏi trước",
        "Câu trả lời trước",
    ]
    assert response.metadata.conversation_context_used is True
    assert response.metadata.conversation_context_message_count == 2
    assert response.metadata.follow_up_detected is True
    assert response.metadata.retrieval_question_prepared is True


def test_service_keeps_short_independent_question_standalone_with_prior_context() -> None:
    workflow = StaticLegalQAWorkflow(_answered_result())
    service = LegalQAService(workflow=workflow)

    response = service.answer(
        LegalQARequest(
            question="Nghỉ phép năm bao nhiêu ngày?",
            conversation_context=[
                {"role": "user", "content": "Điều kiện kết hôn là gì?"},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    workflow_request = workflow.requests[0]
    assert response.decision == "answered"
    assert workflow_request.context is not None
    assert workflow_request.context.follow_up_detected is False
    assert workflow_request.context.context_used is False
    assert workflow_request.context.retrieval_question == "Nghỉ phép năm bao nhiêu ngày?"
    assert response.metadata.follow_up_detected is False
    assert response.metadata.retrieval_question_prepared is False


def test_service_uses_context_for_true_follow_up_question() -> None:
    workflow = StaticLegalQAWorkflow(_answered_result())
    service = LegalQAService(workflow=workflow)
    prior_question = "Nghỉ phép năm bao nhiêu ngày?"
    current_question = "Vậy có được nghỉ thêm không?"

    response = service.answer(
        LegalQARequest(
            question=current_question,
            conversation_context=[
                {"role": "user", "content": prior_question},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    workflow_request = workflow.requests[0]
    assert response.decision == "answered"
    assert workflow_request.context is not None
    assert workflow_request.context.follow_up_detected is True
    assert workflow_request.context.context_used is True
    assert workflow_request.context.retrieval_question == f"{prior_question} {current_question}"
    assert response.metadata.follow_up_detected is True
    assert response.metadata.retrieval_question_prepared is True


def test_fake_answer_and_evidence_are_stable_with_conversation_context() -> None:
    service = LegalQAService()
    question = "Vậy trường hợp này thì sao?"

    without_context = service.answer(LegalQARequest(question=question))
    with_context = service.answer(
        LegalQARequest(
            question=question,
            conversation_context=[
                {"role": "user", "content": "Câu hỏi trước"},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    assert with_context.answer == without_context.answer
    assert with_context.citations == without_context.citations
    assert with_context.evidence == without_context.evidence
    assert with_context.metadata.conversation_context_message_count == 2
    assert with_context.metadata.conversation_context_used is True
    assert with_context.metadata.retrieval_question_prepared is True


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


def test_service_falls_back_for_ui_payload_with_invalid_traceability_url() -> None:
    service = LegalQAService(
        workflow=StaticLegalQAWorkflow(
            LegalQAWorkflowResult(
                decision=LegalQAWorkflowDecision.ANSWERED,
                answer="Câu trả lời không được xuất bản nếu nguồn không hợp lệ [E1].",
                citations=[
                    LegalQAWorkflowCitation(
                        evidence_id="E1",
                        chunk_id="chunk-001",
                        law_id="law-001",
                        law_name="Bộ luật Dân sự",
                        citation="Điều 123 Bộ luật Dân sự",
                        source_url="Unknown",
                        hierarchy_path="Điều 123",
                    )
                ],
                evidence=[
                    LegalQAWorkflowEvidence(
                        evidence_id="E1",
                        chunk_id="chunk-001",
                        law_id="law-001",
                        law_name="Bộ luật Dân sự",
                        citation="Điều 123 Bộ luật Dân sự",
                        text="Giao dịch dân sự vô hiệu khi vi phạm điều cấm.",
                        source_url="Unknown",
                        score=0.91,
                    )
                ],
                metadata=LegalQAWorkflowMetadata(model="fake-workflow", latency_ms=7),
            )
        )
    )

    response = service.answer(
        LegalQARequest(
            question=(
                "Theo Bộ luật Dân sự Việt Nam, hợp đồng dân sự có thể bị vô hiệu "
                "trong những trường hợp nào?"
            ),
            conversation_id="cbe5be82-8924-4cd4-acb4-a00ca1e70d52",
            conversation_context=[
                {"role": "user", "content": "Câu hỏi trước"},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
            top_k=10,
            include_evidence=True,
            include_debug=False,
        )
    )

    assert response.decision == "fallback"
    assert response.citations == []
    assert response.evidence == []
    assert "invalid_citation_source_url" in response.warnings
    assert "invalid_evidence_source_url" in response.warnings
    assert "fallback" in response.warnings


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
