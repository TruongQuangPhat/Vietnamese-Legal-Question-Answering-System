"""Health and version routes for the VnLaw-QA API."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a deterministic health response.

    Returns:
        Stable status payload for liveness checks.
    """
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, str]:
    """Return deterministic application metadata.

    Returns:
        API name and semantic version.
    """
    return {"name": "VnLaw-QA API", "version": "0.1.0"}
