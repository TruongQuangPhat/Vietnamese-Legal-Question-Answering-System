from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_legal_qa_service
from src.services.legal_qa_api_service import LegalQAService, LegalQAWorkflowRequest


def test_ask_route_returns_answer_with_fake_service() -> None:
    client = TestClient(create_app())

    response = client.post(
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


def test_ask_route_hides_evidence_when_requested() -> None:
    client = TestClient(create_app())

    response = client.post(
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


def test_ask_route_rejects_empty_question() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/legal-qa/ask",
        json={"question": "   "},
    )

    assert response.status_code == 422


def test_ask_route_rejects_invalid_top_k() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/legal-qa/ask",
        json={"question": "Câu hỏi hợp lệ?", "top_k": 21},
    )

    assert response.status_code == 422


def test_ask_route_returns_safe_error_when_service_fails() -> None:
    app = create_app()

    class FailingLegalQAWorkflow:
        def run(self, request: LegalQAWorkflowRequest) -> None:
            raise RuntimeError("secret traceback details")

    def get_failing_service() -> LegalQAService:
        return LegalQAService(workflow=FailingLegalQAWorkflow())

    app.dependency_overrides[get_legal_qa_service] = get_failing_service
    client = TestClient(app)

    response = client.post(
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
    }
    assert "secret traceback details" not in response.text
