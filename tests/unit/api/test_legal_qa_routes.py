from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from threading import Thread, get_ident
from typing import Any

import httpx
import pytest

from src.api.app import create_app
from src.api.dependencies import get_legal_qa_service, get_runtime_readiness_service
from src.api.schemas import (
    MAX_LEGAL_QA_CONTEXT_MESSAGE_LENGTH,
    MAX_LEGAL_QA_CONTEXT_MESSAGES,
    MAX_QUESTION_LENGTH,
    LegalQADecision,
    LegalQARequest,
    LegalQAResponse,
    ResponseMetadataDTO,
)
from src.api.settings import AppSettings
from src.retrieval.dense_retriever import QueryEmbeddingTimeoutError
from src.services.legal_qa_api_service import (
    LegalQAService,
    LegalQAWorkflowCitation,
    LegalQAWorkflowDecision,
    LegalQAWorkflowEvidence,
    LegalQAWorkflowMetadata,
    LegalQAWorkflowRequest,
    LegalQAWorkflowResult,
)
from src.services.legal_qa_workflow import LegalQAServiceMode
from src.services.runtime_readiness import RuntimeReadinessService


@pytest.fixture(autouse=True)
def use_worker_thread_offload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.api.routes.legal_qa.anyio.to_thread.run_sync", _run_sync_in_thread)


async def _run_sync_in_thread(func: Callable[..., Any], *args: Any, **_: Any) -> Any:
    result: list[Any] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            result.append(func(*args))
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=worker)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return result[0]


@pytest.mark.asyncio
async def test_ask_route_returns_answer_with_fake_service() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Người lao động được quyền đơn phương chấm dứt hợp đồng khi nào?",
                "top_k": 10,
                "include_evidence": True,
                "include_debug": False,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["request_id"]
    assert body["decision"] == "answered"
    assert body["answer"]
    assert body["citations"][0]["evidence_id"] == "E1"
    assert body["evidence"][0]["evidence_id"] == "E1"
    assert body["metadata"]["retrieval_strategy"] == "coverage_aware_quota"
    assert body["metadata"]["model"] == "stub"
    assert body["metadata"]["reranking_used"] is False


@pytest.mark.asyncio
async def test_ask_route_hides_evidence_when_requested() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Người lao động được quyền đơn phương chấm dứt hợp đồng khi nào?",
                "include_evidence": False,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["citations"]
    assert body["evidence"] == []
    assert "internal_error" not in body["warnings"]


@pytest.mark.asyncio
async def test_ask_route_minimal_payload_does_not_return_internal_error() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Hợp đồng dân sự vô hiệu khi nào?",
                "top_k": 10,
                "include_evidence": False,
                "include_debug": False,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"] == "answered"
    assert body["metadata"]["model"] == "stub"
    assert "internal_error" not in body["warnings"]


@pytest.mark.asyncio
async def test_ask_route_include_evidence_payload_does_not_return_internal_error() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Hợp đồng dân sự vô hiệu khi nào?",
                "top_k": 10,
                "include_evidence": True,
                "include_debug": False,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"] == "answered"
    assert body["evidence"]
    assert "internal_error" not in body["warnings"]


@pytest.mark.asyncio
async def test_ask_route_ui_style_payload_does_not_return_internal_error() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Hợp đồng dân sự vô hiệu khi nào?",
                "conversation_id": "cbe5be82-8924-4cd4-acb4-a00ca1e70d52",
                "conversation_context": [
                    {"role": "user", "content": "Câu hỏi trước"},
                    {"role": "assistant", "content": "Câu trả lời trước"},
                ],
                "top_k": 10,
                "include_evidence": True,
                "include_debug": False,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"] == "answered"
    assert body["metadata"]["conversation_context_message_count"] == 2
    assert "internal_error" not in body["warnings"]


@pytest.mark.asyncio
async def test_ask_route_accepts_valid_conversation_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="src.api.routes.legal_qa")
    private_context = "Nội dung riêng tư CONTEXT-MARKER-7842"
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Vậy hợp đồng xác định thời hạn thì sao?",
                "conversation_id": "conversation-1",
                "conversation_context": [
                    {
                        "role": "user",
                        "content": private_context,
                        "created_at": "2025-01-01T00:00:00Z",
                    },
                    {
                        "role": "assistant",
                        "content": "Câu trả lời trước có căn cứ.",
                    },
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["decision"] == "answered"
    assert response.json()["metadata"]["conversation_context_used"] is True
    assert response.json()["metadata"]["conversation_context_message_count"] == 2
    assert response.json()["metadata"]["follow_up_detected"] is True
    assert response.json()["metadata"]["retrieval_question_prepared"] is True
    assert private_context not in response.text
    assert private_context not in caplog.text


@pytest.mark.asyncio
async def test_ask_route_rejects_invalid_context_role() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Câu hỏi hợp lệ?",
                "conversation_context": [{"role": "system", "content": "Không được chấp nhận."}],
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_route_rejects_too_long_context_message() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Câu hỏi hợp lệ?",
                "conversation_context": [
                    {
                        "role": "user",
                        "content": "x" * (MAX_LEGAL_QA_CONTEXT_MESSAGE_LENGTH + 1),
                    }
                ],
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_route_rejects_too_many_context_messages() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": "Câu hỏi hợp lệ?",
                "conversation_context": [
                    {"role": "user", "content": f"Tin nhắn {index}"}
                    for index in range(MAX_LEGAL_QA_CONTEXT_MESSAGES + 1)
                ],
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_route_rejects_empty_question() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "   "},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_route_rejects_invalid_top_k() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "Câu hỏi hợp lệ?", "top_k": 21},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_route_rejects_too_long_question() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "x" * (MAX_QUESTION_LENGTH + 1)},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_route_returns_safe_error_when_service_fails() -> None:
    app = create_app()

    class FailingLegalQAWorkflow:
        def run(self, request: LegalQAWorkflowRequest) -> None:
            raise RuntimeError("secret traceback details")

    async def get_failing_service() -> LegalQAService:
        return LegalQAService(workflow=FailingLegalQAWorkflow())

    app.dependency_overrides[get_legal_qa_service] = get_failing_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "Câu hỏi hợp lệ?"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"] == "error"
    assert body["answer"] == "Không thể xử lý yêu cầu lúc này. Vui lòng thử lại sau."
    assert body["citations"] == []
    assert body["evidence"] == []
    assert body["warnings"] == ["internal_error"]
    assert body["metadata"] == {
        "retrieval_strategy": "coverage_aware_quota",
        "model": None,
        "reranking_used": False,
        "latency_ms": body["metadata"]["latency_ms"],
        "conversation_context_used": False,
        "conversation_context_message_count": 0,
        "follow_up_detected": False,
        "retrieval_question_prepared": False,
    }
    assert "secret traceback details" not in response.text


@pytest.mark.asyncio
async def test_ask_route_ui_payload_with_invalid_traceability_returns_fallback() -> None:
    app = create_app()

    class InvalidTraceabilityWorkflow:
        def run(self, request: LegalQAWorkflowRequest) -> LegalQAWorkflowResult:
            return LegalQAWorkflowResult(
                decision=LegalQAWorkflowDecision.ANSWERED,
                answer="Câu trả lời không được xuất bản nếu nguồn không hợp lệ [E1].",
                citations=[
                    LegalQAWorkflowCitation(
                        evidence_id="E1",
                        chunk_id="chunk-001",
                        law_id="BLDS_2015",
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
                        law_id="BLDS_2015",
                        law_name="Bộ luật Dân sự",
                        citation="Điều 123 Bộ luật Dân sự",
                        text="Giao dịch dân sự vô hiệu khi vi phạm điều cấm.",
                        source_url="Unknown",
                        score=0.91,
                    )
                ],
                metadata=LegalQAWorkflowMetadata(model="fake-workflow", latency_ms=7),
            )

    async def get_invalid_traceability_service() -> LegalQAService:
        return LegalQAService(workflow=InvalidTraceabilityWorkflow())

    app.dependency_overrides[get_legal_qa_service] = get_invalid_traceability_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": (
                    "Theo Bộ luật Dân sự Việt Nam, hợp đồng dân sự có thể bị vô hiệu "
                    "trong những trường hợp nào?"
                ),
                "conversation_id": "cbe5be82-8924-4cd4-acb4-a00ca1e70d52",
                "conversation_context": [
                    {"role": "user", "content": "Câu hỏi trước"},
                    {"role": "assistant", "content": "Câu trả lời trước"},
                ],
                "top_k": 10,
                "include_evidence": True,
                "include_debug": False,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"] == "fallback"
    assert body["citations"] == []
    assert body["evidence"] == []
    assert "internal_error" not in body["warnings"]
    assert "invalid_citation_source_url" in body["warnings"]
    assert "invalid_evidence_source_url" in body["warnings"]


@pytest.mark.asyncio
async def test_ask_route_logs_safe_completion_metadata(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="src.api.routes.legal_qa")
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "Người lao động được quyền đơn phương chấm dứt hợp đồng khi nào?"},
        )

    assert response.status_code == 200
    record = _single_log_record(caplog, "legal_qa_request_completed")
    assert record.request_id == response.json()["request_id"]
    assert record.decision == "answered"
    assert record.retrieval_strategy == "coverage_aware_quota"
    assert record.warning_count == 0
    assert record.citation_count == 1
    assert record.evidence_count == 1
    assert isinstance(record.latency_ms, int)


@pytest.mark.asyncio
async def test_ask_route_logs_safe_error_metadata(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="src.api.routes.legal_qa")
    app = create_app()
    raw_question = "Câu hỏi hợp lệ có SECRET-QUESTION-8899?"
    conversation_id = "conversation-secret-id-1"

    class FailingLegalQAWorkflow:
        def run(self, request: LegalQAWorkflowRequest) -> None:
            try:
                raise ValueError("secret traceback details")
            except ValueError as exc:
                raise RuntimeError("outer secret traceback details") from exc

    async def get_failing_service() -> LegalQAService:
        return LegalQAService(workflow=FailingLegalQAWorkflow())

    app.dependency_overrides[get_legal_qa_service] = get_failing_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": raw_question,
                "conversation_id": conversation_id,
                "conversation_context": [
                    {"role": "user", "content": "Nội dung riêng tư không được log."},
                    {"role": "assistant", "content": "Câu trả lời riêng tư không được log."},
                ],
                "top_k": 10,
                "include_evidence": True,
                "include_debug": False,
            },
        )

    assert response.status_code == 200
    record = _single_log_record_prefix(caplog, "legal_qa_request_failed")
    assert record.request_id == response.json()["request_id"]
    assert record.exception_class == "ValueError"
    assert record.failure_stage == "workflow_run"
    assert isinstance(record.latency_ms, int)
    assert record.top_k == 10
    assert record.include_evidence is True
    assert record.include_debug is False
    assert record.has_conversation_id is True
    assert record.context_message_count == 2
    assert "secret traceback details" not in caplog.text
    assert "outer secret traceback details" not in caplog.text
    assert raw_question not in caplog.text
    assert "Nội dung riêng tư" not in caplog.text
    assert conversation_id not in caplog.text


@pytest.mark.asyncio
async def test_ask_route_does_not_log_raw_question(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="src.api.routes.legal_qa")
    raw_question = "Câu hỏi có mã riêng tư SECRET-QUESTION-12345?"
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": raw_question},
        )

    assert response.status_code == 200
    assert raw_question not in caplog.text


@pytest.mark.asyncio
async def test_ask_route_logs_sanitized_timing_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="src.api.routes.legal_qa")
    raw_question = "Câu hỏi có mã riêng tư SECRET-TIMING-54321?"
    conversation_id = "conversation-timing-secret-1"
    private_context = "Nội dung riêng tư TIMING-CONTEXT-7821"
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={
                "question": raw_question,
                "conversation_id": conversation_id,
                "conversation_context": [{"role": "user", "content": private_context}],
                "top_k": 7,
                "include_evidence": True,
                "include_debug": False,
            },
        )

    assert response.status_code == 200
    timing_records = _log_records_prefix(caplog, "legal_qa_request_timing")
    stages = {record.stage for record in timing_records}
    assert {
        "request_received",
        "request_validation",
        "conversation_context_loading",
        "retrieval_question_preparation",
        "response_mapping",
        "request_completed",
    }.issubset(stages)
    completed = next(record for record in timing_records if record.stage == "request_completed")
    assert completed.request_id == response.json()["request_id"]
    assert completed.top_k == 7
    assert completed.include_evidence is True
    assert completed.include_debug is False
    assert completed.has_conversation_id is True
    assert completed.context_message_count == 1
    assert completed.service_mode in {"fake", "unknown"}
    assert isinstance(completed.elapsed_ms, int)
    assert isinstance(completed.total_elapsed_ms, int)
    assert raw_question not in caplog.text
    assert private_context not in caplog.text
    assert conversation_id not in caplog.text


@pytest.mark.asyncio
async def test_ask_route_returns_controlled_timeout_response(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.INFO, logger="src.api.routes.legal_qa")
    raw_question = "Câu hỏi có mã riêng tư SECRET-TIMEOUT-9911?"
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "fake",
            "LEGAL_QA_ASK_TIMEOUT_SECONDS": "0.01",
            "LEGAL_QA_MAX_TOP_K": "5",
        }
    )
    app = create_app(settings)

    async def slow_run_sync(
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        await asyncio.sleep(1)
        return func(*args)

    monkeypatch.setattr("src.api.routes.legal_qa.anyio.to_thread.run_sync", slow_run_sync)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": raw_question, "top_k": 10},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"] == "error"
    assert body["warnings"] == ["ask_timeout"]
    assert body["answer"] == "Yêu cầu xử lý quá lâu. Vui lòng thử lại sau."
    record = _single_log_record_prefix(caplog, "legal_qa_request_failed")
    assert record.failure_stage == "ask_timeout"
    assert record.exception_class == "TimeoutError"
    timing_records = _log_records_prefix(caplog, "legal_qa_request_timing")
    assert any(record.stage == "request_failed" for record in timing_records)
    assert all(record.top_k == 5 for record in timing_records)
    assert raw_question not in caplog.text


@pytest.mark.asyncio
async def test_ask_route_returns_precise_query_embedding_timeout_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="src.api.routes.legal_qa")
    app = create_app(
        AppSettings.from_env(
            {
                "LEGAL_QA_SERVICE_MODE": "fake",
                "LEGAL_QA_ASK_TIMEOUT_SECONDS": "10",
            }
        )
    )

    class QueryEmbeddingTimeoutWorkflow:
        def run(self, request: LegalQAWorkflowRequest) -> None:
            raise QueryEmbeddingTimeoutError(timeout_seconds=0.001)

    async def get_timeout_service() -> LegalQAService:
        return LegalQAService(workflow=QueryEmbeddingTimeoutWorkflow())

    app.dependency_overrides[get_legal_qa_service] = get_timeout_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "Câu hỏi riêng tư SECRET-EMBEDDING-TIMEOUT?"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"] == "error"
    assert body["warnings"] == ["query_embedding_timeout"]
    assert body["answer"] == "Yêu cầu xử lý quá lâu. Vui lòng thử lại sau."
    assert "SECRET-EMBEDDING-TIMEOUT" not in caplog.text


@pytest.mark.asyncio
async def test_warmup_endpoint_is_disabled_by_default() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/legal-qa/warmup")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_warmup_endpoint_returns_sanitized_status_when_enabled() -> None:
    app = create_app(
        AppSettings.from_env(
            {
                "LEGAL_QA_SERVICE_MODE": "fake",
                "LEGAL_QA_WARMUP_ENDPOINT_ENABLED": "true",
            }
        )
    )

    class WarmableService:
        def warmup_embedding(self):
            return type(
                "WarmupResult",
                (),
                {"warmed": True, "elapsed_ms": 7, "exception_class": None},
            )()

    async def get_warmable_service() -> WarmableService:
        return WarmableService()

    app.dependency_overrides[get_legal_qa_service] = get_warmable_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/legal-qa/warmup")

    assert response.status_code == 200
    assert response.json() == {"warmed": True, "elapsed_ms": 7, "exception_class": None}


@pytest.mark.asyncio
async def test_ask_route_offloads_service_answer_from_event_loop() -> None:
    app = create_app()
    event_loop_thread_id = get_ident()
    answer_thread_ids: list[int] = []

    class ThreadRecordingService:
        def answer(self, request: LegalQARequest) -> LegalQAResponse:
            answer_thread_ids.append(get_ident())
            return LegalQAResponse(
                request_id="request-1",
                decision=LegalQADecision.ANSWERED,
                answer="Câu trả lời thử nghiệm.",
                citations=[],
                evidence=[],
                warnings=[],
                metadata=ResponseMetadataDTO(
                    retrieval_strategy="coverage_aware_quota",
                    model="stub",
                    reranking_used=False,
                    latency_ms=1,
                ),
            )

    async def get_thread_recording_service() -> ThreadRecordingService:
        return ThreadRecordingService()

    app.dependency_overrides[get_legal_qa_service] = get_thread_recording_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "Câu hỏi hợp lệ?"},
        )

    assert response.status_code == 200
    assert response.json()["decision"] == "answered"
    assert answer_thread_ids
    assert answer_thread_ids[0] != event_loop_thread_id


@pytest.mark.asyncio
async def test_ask_route_allows_requests_within_rate_limit() -> None:
    app = create_app(_rate_limit_settings(requests=2, window_seconds=60))
    service = CountingLegalQAService()
    app.dependency_overrides[get_legal_qa_service] = lambda: service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post("/api/v1/legal-qa/ask", json={"question": "Câu hỏi hợp lệ?"})
        second = await client.post("/api/v1/legal-qa/ask", json={"question": "Câu hỏi hợp lệ?"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert service.call_count == 2


@pytest.mark.asyncio
async def test_ask_route_returns_429_when_rate_limit_exceeded() -> None:
    app = create_app(_rate_limit_settings(requests=1, window_seconds=60))
    service = CountingLegalQAService()
    service_dependency_calls = 0

    def get_counting_service() -> CountingLegalQAService:
        nonlocal service_dependency_calls
        service_dependency_calls += 1
        return service

    app.dependency_overrides[get_legal_qa_service] = get_counting_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        allowed = await client.post("/api/v1/legal-qa/ask", json={"question": "Câu hỏi hợp lệ?"})
        blocked = await client.post("/api/v1/legal-qa/ask", json={"question": "Câu hỏi hợp lệ?"})

    assert allowed.status_code == 200
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert blocked.json() == {
        "detail": {
            "error": "rate_limit_exceeded",
            "message": "Too many Legal QA requests. Please retry later.",
        }
    }
    assert service.call_count == 1
    assert service_dependency_calls == 1


@pytest.mark.asyncio
async def test_ask_route_rate_limit_can_be_disabled() -> None:
    app = create_app(_rate_limit_settings(enabled=False, requests=1, window_seconds=60))
    service = CountingLegalQAService()
    app.dependency_overrides[get_legal_qa_service] = lambda: service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post("/api/v1/legal-qa/ask", json={"question": "Câu hỏi hợp lệ?"})
        second = await client.post("/api/v1/legal-qa/ask", json={"question": "Câu hỏi hợp lệ?"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert service.call_count == 2


@pytest.mark.asyncio
async def test_health_and_readiness_are_not_rate_limited() -> None:
    app = create_app(_rate_limit_settings(requests=1, window_seconds=60))
    service = CountingLegalQAService()
    app.dependency_overrides[get_legal_qa_service] = lambda: service
    app.dependency_overrides[get_runtime_readiness_service] = lambda: RuntimeReadinessService(
        service_mode=LegalQAServiceMode.FAKE,
        configuration_issues=(),
        qdrant_collection=None,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        blocked_seed = await client.post(
            "/api/v1/legal-qa/ask",
            json={"question": "Câu hỏi hợp lệ?"},
        )
        blocked = await client.post("/api/v1/legal-qa/ask", json={"question": "Câu hỏi hợp lệ?"})
        health = await client.get("/health")
        readiness = await client.get("/api/v1/readiness")

    assert blocked_seed.status_code == 200
    assert blocked.status_code == 429
    assert health.status_code == 200
    assert readiness.status_code == 200
    assert service.call_count == 1


class CountingLegalQAService:
    def __init__(self) -> None:
        self.call_count = 0

    def answer(self, request: LegalQARequest) -> LegalQAResponse:
        self.call_count += 1
        return LegalQAResponse(
            request_id=f"request-{self.call_count}",
            decision=LegalQADecision.ANSWERED,
            answer="Câu trả lời thử nghiệm.",
            citations=[],
            evidence=[],
            warnings=[],
            metadata=ResponseMetadataDTO(
                retrieval_strategy="coverage_aware_quota",
                model="stub",
                reranking_used=False,
                latency_ms=1,
            ),
        )


def _rate_limit_settings(
    *,
    enabled: bool = True,
    requests: int,
    window_seconds: int,
) -> AppSettings:
    return AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "fake",
            "LEGAL_QA_RATE_LIMIT_ENABLED": str(enabled).lower(),
            "LEGAL_QA_RATE_LIMIT_REQUESTS": str(requests),
            "LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS": str(window_seconds),
        }
    )


def _single_log_record(caplog: pytest.LogCaptureFixture, message: str) -> logging.LogRecord:
    matching_records = [record for record in caplog.records if record.getMessage() == message]
    assert len(matching_records) == 1
    return matching_records[0]


def _single_log_record_prefix(
    caplog: pytest.LogCaptureFixture,
    message_prefix: str,
) -> logging.LogRecord:
    matching_records = [
        record for record in caplog.records if record.getMessage().startswith(message_prefix)
    ]
    assert len(matching_records) == 1
    return matching_records[0]


def _log_records_prefix(
    caplog: pytest.LogCaptureFixture,
    message_prefix: str,
) -> list[logging.LogRecord]:
    matching_records = [
        record for record in caplog.records if record.getMessage().startswith(message_prefix)
    ]
    assert matching_records
    return matching_records
