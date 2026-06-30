from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Thread, get_ident
from typing import Any

import httpx
import pytest

from src.api.app import create_app
from src.api.dependencies import get_legal_qa_service
from src.api.schemas import (
    MAX_LEGAL_QA_CONTEXT_MESSAGE_LENGTH,
    MAX_LEGAL_QA_CONTEXT_MESSAGES,
    MAX_QUESTION_LENGTH,
    LegalQADecision,
    LegalQARequest,
    LegalQAResponse,
    ResponseMetadataDTO,
)
from src.services.legal_qa_api_service import LegalQAService, LegalQAWorkflowRequest


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

    assert response.status_code == 200
    record = _single_log_record(caplog, "legal_qa_request_failed")
    assert record.request_id == response.json()["request_id"]
    assert record.error_type == "RuntimeError"
    assert isinstance(record.latency_ms, int)
    assert "secret traceback details" not in caplog.text


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


def _single_log_record(caplog: pytest.LogCaptureFixture, message: str) -> logging.LogRecord:
    matching_records = [record for record in caplog.records if record.getMessage() == message]
    assert len(matching_records) == 1
    return matching_records[0]
