"""Health and version routes for the VnLaw-QA API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from src.api.dependencies import get_runtime_readiness_service
from src.api.schemas import ReadinessCheckDTO, ReadinessResponse
from src.services.runtime_readiness import RuntimeReadinessService

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a deterministic health response.

    Returns:
        Stable status payload for liveness checks.
    """
    return {"status": "ok"}


@router.get("/api/v1/readiness", response_model=ReadinessResponse)
async def readiness(
    response: Response,
    service: RuntimeReadinessService = Depends(get_runtime_readiness_service),
) -> ReadinessResponse:
    """Report safe runtime readiness without generation or heavy model loading.

    Args:
        response: FastAPI response used to select 200 or 503.
        service: Injected readiness service.

    Returns:
        Sanitized configuration and optional read-only Qdrant check results.
    """
    result = await service.check()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        ready=result.ready,
        service_mode=result.service_mode.value,
        checks=[
            ReadinessCheckDTO(
                name=check.name,
                ready=check.ready,
                detail=check.detail,
            )
            for check in result.checks
        ],
    )


@router.get("/version")
async def version() -> dict[str, str]:
    """Return deterministic application metadata.

    Returns:
        API name and semantic version.
    """
    return {"name": "VnLaw-QA API", "version": "0.1.0"}
