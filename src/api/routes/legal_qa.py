"""Legal QA API routes."""

from __future__ import annotations

from time import perf_counter

import anyio
from fastapi import APIRouter, Depends

from src.api.dependencies import get_legal_qa_service
from src.api.schemas import LegalQADecision, LegalQARequest, LegalQAResponse, ResponseMetadataDTO
from src.services.legal_qa_api_service import LegalQAService

router = APIRouter(prefix="/legal-qa", tags=["legal-qa"])

SAFE_ERROR_ANSWER = "Không thể xử lý yêu cầu lúc này. Vui lòng thử lại sau."


@router.post("/ask", response_model=LegalQAResponse)
async def ask_legal_question(
    request: LegalQARequest,
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
        return await anyio.to_thread.run_sync(service.answer, request)
    except Exception:
        latency_ms = int((perf_counter() - started_at) * 1000)
        return LegalQAResponse(
            request_id=LegalQAService.create_request_id(),
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
