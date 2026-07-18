"""Legal QA API routes."""

from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import get_legal_qa_service
from src.api.rate_limit import enforce_ask_rate_limit
from src.api.schemas import LegalQADecision, LegalQARequest, LegalQAResponse, ResponseMetadataDTO
from src.api.settings import AppSettings, get_settings
from src.services.legal_qa_api_service import (
    LegalQAService,
    LegalQAServiceError,
    LegalQATimingLogger,
)

router = APIRouter(prefix="/legal-qa", tags=["legal-qa"])
logger = logging.getLogger(__name__)

SAFE_ERROR_ANSWER = "Không thể xử lý yêu cầu lúc này. Vui lòng thử lại sau."
SAFE_TIMEOUT_ANSWER = "Yêu cầu xử lý quá lâu. Vui lòng thử lại sau."


@router.post("/ask", response_model=LegalQAResponse)
async def ask_legal_question(
    request: LegalQARequest,
    http_request: Request,
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
    settings = _request_settings(http_request)
    request = _cap_request_top_k(request, settings)
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
        with anyio.fail_after(settings.legal_qa_ask_timeout_seconds):
            response = await anyio.to_thread.run_sync(
                _answer_with_optional_timing,
                service,
                request,
                timing_logger,
                abandon_on_cancel=True,
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
    except TimeoutError:
        latency_ms = int((perf_counter() - started_at) * 1000)
        request_id = LegalQAService.create_request_id()
        _log_request_failed(
            request=request,
            request_id=request_id,
            exception_class="TimeoutError",
            failure_stage="ask_timeout",
            latency_ms=latency_ms,
        )
        _log_request_timing(
            request=request,
            stage="request_failed",
            request_id=request_id,
            elapsed_ms=latency_ms,
            total_elapsed_ms=latency_ms,
            exception_class="TimeoutError",
        )
        return LegalQAResponse(
            request_id=request_id,
            decision=LegalQADecision.ERROR,
            answer=SAFE_TIMEOUT_ANSWER,
            citations=[],
            evidence=[],
            warnings=["ask_timeout"],
            metadata=ResponseMetadataDTO(
                retrieval_strategy="coverage_aware_quota",
                model=None,
                reranking_used=False,
                latency_ms=latency_ms,
            ),
        )
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
        timeout_failure = _is_timeout_failure(
            exception_class=exception_class,
            failure_stage=failure_stage,
        )
        warning = _warning_for_failure(
            exception_class=exception_class,
            failure_stage=failure_stage,
        )
        return LegalQAResponse(
            request_id=request_id,
            decision=LegalQADecision.ERROR,
            answer=SAFE_TIMEOUT_ANSWER if timeout_failure else SAFE_ERROR_ANSWER,
            citations=[],
            evidence=[],
            warnings=[warning],
            metadata=ResponseMetadataDTO(
                retrieval_strategy="coverage_aware_quota",
                model=None,
                reranking_used=False,
                latency_ms=latency_ms,
            ),
        )


@router.get("/warmup")
async def warmup_legal_qa(
    http_request: Request,
    service: LegalQAService = Depends(get_legal_qa_service),
) -> dict[str, object]:
    """Explicitly warm the embedding model without running retrieval or generation."""
    settings = _request_settings(http_request)
    if not settings.legal_qa_warmup_endpoint_enabled:
        raise HTTPException(status_code=404, detail="not_found")
    started_at = perf_counter()
    model_status = _warmup_model_status(service)
    try:
        with anyio.fail_after(settings.legal_qa_warmup_timeout_seconds):
            result = await anyio.to_thread.run_sync(
                service.warmup_embedding,
                abandon_on_cancel=True,
            )
    except TimeoutError:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        model_status_after = _warmup_model_status(service)
        cache_hit_before = bool(model_status.get("embedding_model_cache_hit", False))
        return {
            "warmed": False,
            "elapsed_ms": elapsed_ms,
            "exception_class": "TimeoutError",
            "model_path_configured": bool(model_status.get("model_path_configured", False)),
            "model_path_exists": bool(model_status.get("model_path_exists", False)),
            "required_files_present": bool(model_status.get("required_files_present", False)),
            "model_load_started": not cache_hit_before,
            "model_load_completed": cache_hit_before,
            "model_load_timeout": not cache_hit_before,
            "encode_started": cache_hit_before,
            "encode_completed": False,
            "encode_timeout": cache_hit_before,
            "cache_hit_before": cache_hit_before,
            "cache_hit_after": bool(model_status_after.get("embedding_model_cache_hit", False)),
            "model_cache_key": _safe_model_cache_key(
                model_status_after.get("model_cache_key") or model_status.get("model_cache_key")
            ),
        }
    return {
        "warmed": result.warmed,
        "elapsed_ms": result.elapsed_ms,
        "exception_class": result.exception_class,
        "model_path_configured": bool(getattr(result, "model_path_configured", False)),
        "model_path_exists": bool(getattr(result, "model_path_exists", False)),
        "required_files_present": bool(getattr(result, "required_files_present", False)),
        "model_load_started": bool(getattr(result, "model_load_started", False)),
        "model_load_completed": bool(getattr(result, "model_load_completed", False)),
        "model_load_timeout": bool(getattr(result, "model_load_timeout", False)),
        "encode_started": bool(getattr(result, "encode_started", False)),
        "encode_completed": bool(getattr(result, "encode_completed", False)),
        "encode_timeout": bool(getattr(result, "encode_timeout", False)),
        "cache_hit_before": bool(getattr(result, "cache_hit_before", False)),
        "cache_hit_after": bool(getattr(result, "cache_hit_after", False)),
        "model_cache_key": _safe_model_cache_key(getattr(result, "model_cache_key", None)),
    }


def _answer_with_optional_timing(
    service: Any,
    request: LegalQARequest,
    timing_logger: LegalQATimingLogger,
) -> LegalQAResponse:
    if isinstance(service, LegalQAService):
        return service.answer(request, timing_logger=timing_logger)
    return service.answer(request)


def _request_settings(request: Request) -> AppSettings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, AppSettings):
        return settings
    return get_settings()


def _warmup_model_status(service: Any) -> dict[str, object]:
    status = getattr(service, "embedding_model_status", None)
    if status is None or not callable(status):
        return {
            "model_path_configured": False,
            "model_path_exists": False,
            "required_files_present": False,
            "embedding_model_cache_hit": False,
            "model_cache_key": None,
        }
    raw_status = status()
    return {
        "model_path_configured": bool(raw_status.get("model_path_configured", False)),
        "model_path_exists": bool(raw_status.get("model_path_exists", False)),
        "required_files_present": bool(raw_status.get("required_files_present", False)),
        "embedding_model_cache_hit": bool(raw_status.get("embedding_model_cache_hit", False)),
        "model_cache_key": _safe_model_cache_key(raw_status.get("model_cache_key")),
    }


def _cap_request_top_k(request: LegalQARequest, settings: AppSettings) -> LegalQARequest:
    if request.top_k <= settings.legal_qa_max_top_k:
        return request
    return request.model_copy(update={"top_k": settings.legal_qa_max_top_k})


def _is_timeout_failure(*, exception_class: str, failure_stage: str) -> bool:
    return exception_class.endswith("TimeoutError") or failure_stage.endswith("_timeout")


def _warning_for_failure(*, exception_class: str, failure_stage: str) -> str:
    if failure_stage in {
        "embedding_model_load_timeout",
        "query_embedding_timeout",
        "qdrant_retrieval_timeout",
        "retrieval_timeout",
        "llm_generation_provider_call",
        "ask_timeout",
    }:
        return failure_stage
    if failure_stage in {
        "embedding_model_load_error",
        "query_embedding_error",
        "qdrant_retrieval_error",
        "dense_retriever_error",
    }:
        return failure_stage
    if exception_class.endswith("TimeoutError"):
        return "ask_timeout"
    return "internal_error"


def _build_timing_logger(request: LegalQARequest) -> LegalQATimingLogger:
    def log_timing(
        stage: str,
        request_id: str | None,
        elapsed_ms: int,
        total_elapsed_ms: int,
        exception_class: str | None,
        **metadata: Any,
    ) -> None:
        _log_request_timing(
            request=request,
            stage=stage,
            request_id=request_id,
            elapsed_ms=elapsed_ms,
            total_elapsed_ms=total_elapsed_ms,
            exception_class=exception_class,
            timeout_seconds=_safe_optional_float(metadata.get("timeout_seconds")),
            fallback_used=bool(metadata.get("fallback_used", False)),
            top_k_override=_safe_optional_int(metadata.get("top_k")),
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
            "retrieval_mode": response.metadata.retrieval_mode,
            "dense_retrieval_used": response.metadata.dense_retrieval_used,
            "dense_retrieval_fallback_used": response.metadata.dense_retrieval_fallback_used,
            "fallback_used": response.metadata.fallback_used,
            "retriever_stage_failed": response.metadata.retriever_stage_failed,
            "embedding_model_cache_hit": response.metadata.embedding_model_cache_hit,
            "embedding_model_loaded_before_request": (
                response.metadata.embedding_model_loaded_before_request
            ),
            "model_cache_key": response.metadata.model_cache_key,
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
    timeout_seconds: float | None = None,
    fallback_used: bool = False,
    top_k_override: int | None = None,
) -> None:
    payload = {
        "event": "legal_qa_request_timing",
        "level": "INFO",
        "request_id": request_id,
        "stage": stage,
        "elapsed_ms": elapsed_ms,
        "total_elapsed_ms": total_elapsed_ms,
        "exception_class": exception_class,
        "top_k": request.top_k if top_k_override is None else top_k_override,
        "include_evidence": request.include_evidence,
        "include_debug": request.include_debug,
        "has_conversation_id": request.conversation_id is not None,
        "context_message_count": len(request.conversation_context),
        "service_mode": _safe_service_mode(),
        "timeout_seconds": timeout_seconds,
        "fallback_used": fallback_used,
    }
    logger.info(
        "legal_qa_request_timing stage=%s",
        stage,
        extra=payload,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _safe_service_mode() -> str:
    raw_mode = os.getenv("LEGAL_QA_SERVICE_MODE")
    if raw_mode in {"fake", "real"}:
        return raw_mode
    return "unknown"


def _safe_optional_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _safe_optional_int(value: Any) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    return None


def _safe_model_cache_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if not all(character.isalnum() or character in {":", "_", "-"} for character in stripped):
        return None
    return stripped
