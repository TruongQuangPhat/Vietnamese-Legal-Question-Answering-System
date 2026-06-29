"""FastAPI application factory for the VnLaw-QA product API."""

from __future__ import annotations

from fastapi import FastAPI

from src.api.routes.health import router as health_router
from src.api.routes.legal_qa import router as legal_qa_router


def create_app() -> FastAPI:
    """Create the VnLaw-QA FastAPI application.

    Returns:
        Configured FastAPI application with health and legal QA routes.
    """
    app = FastAPI(title="VnLaw-QA API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(legal_qa_router, prefix="/api/v1")
    return app


app = create_app()
