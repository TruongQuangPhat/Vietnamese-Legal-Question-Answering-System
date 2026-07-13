"""Legal QA API routes."""

from __future__ import annotations

import logging
from time import perf_counter

import anyio
from fastapi import APIRouter, Depends

from src.api.dependencies import get_legal_qa_service
from src.api.rate_limit import enforce_ask_rate_limit
from src.api.schemas import LegalQADecision, LegalQARequest, LegalQAResponse, ResponseMetadataDTO
from src.services.legal_qa_api_service import LegalQAService, LegalQAServiceError

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
    try:
        response = await anyio.to_thread.run_sync(service.answer, request)
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
