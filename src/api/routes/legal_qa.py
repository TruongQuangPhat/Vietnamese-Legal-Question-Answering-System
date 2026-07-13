"""Legal QA API routes."""

from __future__ import annotations

import logging
import os
from time import perf_counter
from typing import Any

import anyio
from fastapi import APIRouter, Depends

from src.api.dependencies import get_legal_qa_service
from src.api.rate_limit import enforce_ask_rate_limit
from src.api.schemas import LegalQADecision, LegalQARequest, LegalQAResponse, ResponseMetadataDTO
from src.services.legal_qa_api_service import (
    LegalQAService,
    LegalQAServiceError,
    LegalQATimingLogger,
)

router = APIRouter(prefix="/legal-qa", tags=["legal-qa"])
logger = logging.getLogger(__name__)

SAFE_ERROR_ANSWER = "Không thể xử lý yêu cầu lúc này. Vui lòng thử lại sau."


@router.post("/ask", response_model=LegalQAResponse)
async def ask_legal_question(
    request: LegalQARequest,
    _: None = Depends(enforce_ask_rate_limit),
    service: LegalQAService = Depends(get_legal_qa_service),
) -> LegalQAResponse:
    """Answer a legal question through the API service boundary.

    Args:
        request: Validated legal QA request.
        service: Injected legal QA service. Unit tests may override this dependency
            with deterministic fakes.

    Returns:
        Legal QA response with citations, optional evidence, warnings, and metadata.
        Unexpected service failures return a sanitized error payload without traceback,
        prompts, secrets, or internal debug data.
    """
    started_at = perf_counter()
    _log_request_timing(
        request=request,
        stage="request_received",
        request_id=None,
        elapsed_ms=0,
        total_elapsed_ms=0,
    )
    _log_request_timing(
        request=request,
        stage="request_validation",
        request_id=None,
        elapsed_ms=0,
        total_elapsed_ms=0,
    )
    timing_logger = _build_timing_logger(request)
    try:
        response = await anyio.to_thread.run_sync(
            _answer_with_optional_timing,
            service,
            request,
            timing_logger,
        )
        latency_ms = int((perf_counter() - started_at) * 1000)
        _log_request_timing(
            request=request,
            stage="request_completed",
            request_id=response.request_id,
            elapsed_ms=latency_ms,
            total_elapsed_ms=latency_ms,
        )
        _log_request_completed(response)
        return response
    except Exception as exc:
        latency_ms = int((perf_counter() - started_at) * 1000)
        request_id = (
            exc.request_id
            if isinstance(exc, LegalQAServiceError) and exc.request_id is not None
            else LegalQAService.create_request_id()
        )
        exception_class = (
            exc.exception_class if isinstance(exc, LegalQAServiceError) else type(exc).__name__
        )
        failure_stage = (
            exc.failure_stage if isinstance(exc, LegalQAServiceError) else "route_handler"
        )
        _log_request_failed(
            request=request,
            request_id=request_id,
            exception_class=exception_class,
            failure_stage=failure_stage,
            latency_ms=latency_ms,
        )
        _log_request_timing(
            request=request,
            stage="request_failed",
            request_id=request_id,
            elapsed_ms=latency_ms,
            total_elapsed_ms=latency_ms,
            exception_class=exception_class,
        )
        return LegalQAResponse(
            request_id=request_id,
            decision=LegalQADecision.ERROR,
            answer=SAFE_ERROR_ANSWER,
            citations=[],
            evidence=[],
            warnings=["internal_error"],
            metadata=ResponseMetadataDTO(
                retrieval_strategy="coverage_aware_quota",
                model=None,
                reranking_used=False,
                latency_ms=latency_ms,
            ),
        )


def _answer_with_optional_timing(
    service: Any,
    request: LegalQARequest,
    timing_logger: LegalQATimingLogger,
) -> LegalQAResponse:
    if isinstance(service, LegalQAService):
        return service.answer(request, timing_logger=timing_logger)
    return service.answer(request)


def _build_timing_logger(request: LegalQARequest) -> LegalQATimingLogger:
    def log_timing(
        stage: str,
        request_id: str | None,
        elapsed_ms: int,
        total_elapsed_ms: int,
        exception_class: str | None,
    ) -> None:
        _log_request_timing(
            request=request,
            stage=stage,
            request_id=request_id,
            elapsed_ms=elapsed_ms,
            total_elapsed_ms=total_elapsed_ms,
            exception_class=exception_class,
        )

    return log_timing


def _log_request_completed(response: LegalQAResponse) -> None:
    logger.info(
        "legal_qa_request_completed",
        extra={
            "request_id": response.request_id,
            "decision": response.decision,
            "latency_ms": response.metadata.latency_ms,
            "retrieval_strategy": response.metadata.retrieval_strategy,
            "warning_count": len(response.warnings),
            "citation_count": len(response.citations),
            "evidence_count": len(response.evidence),
        },
    )


def _log_request_failed(
    *,
    request: LegalQARequest,
    request_id: str,
    exception_class: str,
    failure_stage: str,
    latency_ms: int,
) -> None:
    logger.warning(
        "legal_qa_request_failed failure_stage=%s exception_class=%s",
        failure_stage,
        exception_class,
        extra={
            "request_id": request_id,
            "exception_class": exception_class,
            "failure_stage": failure_stage,
            "latency_ms": latency_ms,
            "top_k": request.top_k,
            "include_evidence": request.include_evidence,
            "include_debug": request.include_debug,
            "has_conversation_id": request.conversation_id is not None,
            "context_message_count": len(request.conversation_context),
        },
    )


def _log_request_timing(
    *,
    request: LegalQARequest,
    stage: str,
    request_id: str | None,
    elapsed_ms: int,
    total_elapsed_ms: int,
    exception_class: str | None = None,
) -> None:
    logger.info(
        "legal_qa_request_timing stage=%s",
        stage,
        extra={
            "request_id": request_id,
            "stage": stage,
            "elapsed_ms": elapsed_ms,
            "total_elapsed_ms": total_elapsed_ms,
            "exception_class": exception_class,
            "top_k": request.top_k,
            "include_evidence": request.include_evidence,
            "include_debug": request.include_debug,
            "has_conversation_id": request.conversation_id is not None,
            "context_message_count": len(request.conversation_context),
            "service_mode": _safe_service_mode(),
        },
    )


def _safe_service_mode() -> str:
    raw_mode = os.getenv("LEGAL_QA_SERVICE_MODE")
    if raw_mode in {"fake", "real"}:
        return raw_mode
    return "unknown"
