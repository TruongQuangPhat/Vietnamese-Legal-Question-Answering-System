from __future__ import annotations

import pytest

from scripts.deployment.validate_production_ask_smoke_response import (
    GENERIC_ERROR_ANSWERS,
    SEVERE_WARNINGS,
    SmokeValidationError,
    validate_response_payload,
)

DEFAULT_CITATIONS = object()


def test_smoke_validation_passes_for_standalone_question_without_prepared_retrieval() -> None:
    lines = validate_response_payload(_valid_payload(retrieval_question_prepared=False))

    assert any(
        line
        == "retrieval_question_prepared=false is acceptable for this standalone smoke question."
        for line in lines
    )


def test_smoke_validation_passes_when_follow_up_detected_false_without_prepared_retrieval() -> None:
    lines = validate_response_payload(
        _valid_payload(
            follow_up_detected=False,
            retrieval_question_prepared=False,
        )
    )

    assert any("standalone smoke question" in line for line in lines)


def test_smoke_validation_fails_for_non_200_http_status() -> None:
    with pytest.raises(SmokeValidationError, match="non-200"):
        validate_response_payload(_valid_payload(), http_status="502")


def test_smoke_validation_fails_for_error_decision() -> None:
    payload = _valid_payload(decision="error")

    with pytest.raises(SmokeValidationError, match="decision=error"):
        validate_response_payload(payload)


@pytest.mark.parametrize("metadata", [{"model": None}, {}])
def test_smoke_validation_fails_for_missing_model(metadata: dict[str, object]) -> None:
    payload = _valid_payload()
    payload["metadata"] = {
        "latency_ms": 123,
        "follow_up_detected": False,
        "retrieval_question_prepared": False,
        **metadata,
    }

    with pytest.raises(SmokeValidationError, match="metadata.model"):
        validate_response_payload(payload)


@pytest.mark.parametrize("citations", [[], None])
def test_smoke_validation_fails_for_missing_citations(citations: object) -> None:
    payload = _valid_payload(citations=citations)

    with pytest.raises(SmokeValidationError, match="no citations"):
        validate_response_payload(payload)


@pytest.mark.parametrize("answer", ["", "Ngắn."])
def test_smoke_validation_fails_for_empty_or_too_short_answer(answer: str) -> None:
    payload = _valid_payload(answer=answer)

    with pytest.raises(SmokeValidationError, match="too-short answer"):
        validate_response_payload(payload)


def test_smoke_validation_fails_for_generic_internal_error_answer() -> None:
    payload = _valid_payload(answer=next(iter(GENERIC_ERROR_ANSWERS)))

    with pytest.raises(SmokeValidationError, match="generic internal-error answer"):
        validate_response_payload(payload)


@pytest.mark.parametrize("warning", sorted(SEVERE_WARNINGS))
def test_smoke_validation_fails_for_severe_warnings(warning: str) -> None:
    payload = _valid_payload(warnings=[warning])

    with pytest.raises(SmokeValidationError, match="severe warning"):
        validate_response_payload(payload)


def test_smoke_validation_fails_for_hybrid_fallback_metadata() -> None:
    payload = _valid_payload(
        metadata_overrides={
            "dense_retrieval_used": False,
            "dense_retrieval_fallback_used": True,
            "fallback_used": True,
            "retriever_stage_failed": "embedding_model_load_timeout",
        }
    )

    with pytest.raises(SmokeValidationError, match="degraded dense retrieval fallback"):
        validate_response_payload(payload)


def test_smoke_validation_fails_when_hybrid_dense_was_not_used() -> None:
    payload = _valid_payload(metadata_overrides={"dense_retrieval_used": False})

    with pytest.raises(SmokeValidationError, match="did not use dense retrieval"):
        validate_response_payload(payload)


def test_smoke_validation_passes_with_evidence_caution_warning() -> None:
    lines = validate_response_payload(_valid_payload(warnings=["all_selected_evidence_caution"]))

    assert "Warnings: all_selected_evidence_caution" in lines


def test_smoke_validation_fails_when_follow_up_was_not_prepared() -> None:
    payload = _valid_payload(
        follow_up_detected=True,
        retrieval_question_prepared=False,
    )

    with pytest.raises(SmokeValidationError, match="follow-up question"):
        validate_response_payload(payload)


def test_smoke_validation_logs_sanitized_summary_fields() -> None:
    lines = validate_response_payload(_valid_payload())

    assert "Decision: answered" in lines
    assert "Answer length: 77" in lines
    assert "Citation count: 1" in lines
    assert "Evidence count: 0" in lines
    assert "Response latency_ms: 25257" in lines
    assert "Metadata model exists: True" in lines
    assert "Retrieval mode: hybrid" in lines
    assert "Dense retrieval used: True" in lines
    assert "Dense retrieval fallback used: False" in lines
    assert "Fallback used: False" in lines
    assert "Retriever stage failed: None" in lines
    assert "Retrieval question prepared: False" in lines
    assert "Follow-up detected: False" in lines
    assert "Warnings: " in lines


def _valid_payload(
    *,
    answer: str = "Câu trả lời hợp lệ có căn cứ trích dẫn và đủ dài cho smoke kiểm tra sản xuất.",
    citations: object = DEFAULT_CITATIONS,
    decision: str = "answered",
    follow_up_detected: bool | None = False,
    retrieval_question_prepared: bool = False,
    warnings: list[str] | None = None,
    metadata_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "latency_ms": 25257,
        "model": "google/gemini-2.5-flash",
        "retrieval_mode": "hybrid",
        "dense_retrieval_used": True,
        "dense_retrieval_fallback_used": False,
        "fallback_used": False,
        "retriever_stage_failed": None,
        "follow_up_detected": follow_up_detected,
        "retrieval_question_prepared": retrieval_question_prepared,
    }
    if metadata_overrides:
        metadata.update(metadata_overrides)
    return {
        "answer": answer,
        "citations": [{"id": "E1"}] if citations is DEFAULT_CITATIONS else citations,
        "decision": decision,
        "evidence": [],
        "metadata": metadata,
        "request_id": "test-request",
        "warnings": [] if warnings is None else warnings,
    }
