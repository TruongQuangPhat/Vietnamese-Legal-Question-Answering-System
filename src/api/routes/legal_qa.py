"""Legal QA API routes."""

from __future__ import annotations

import logging
from time import perf_counter

import anyio
from fastapi import APIRouter, Depends

from src.api.dependencies import get_legal_qa_service
from src.api.rate_limit import enforce_ask_rate_limit
from src.api.schemas import LegalQADecision, LegalQARequest, LegalQAResponse, ResponseMetadataDTO
from src.services.legal_qa_api_service import LegalQAService

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
        request_id = LegalQAService.create_request_id()
        _log_request_failed(
            request_id=request_id,
            error_type=type(exc).__name__,
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


def _log_request_failed(*, request_id: str, error_type: str, latency_ms: int) -> None:
    logger.warning(
        "legal_qa_request_failed",
        extra={
            "request_id": request_id,
            "error_type": error_type,
            "latency_ms": latency_ms,
        },
    )
