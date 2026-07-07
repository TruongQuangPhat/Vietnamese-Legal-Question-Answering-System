"""FastAPI application factory for the VnLaw-QA product API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.rate_limit import build_rate_limiter
from src.api.routes.conversations import router as conversations_router
from src.api.routes.health import router as health_router
from src.api.routes.legal_qa import router as legal_qa_router
from src.api.settings import AppSettings, get_settings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create the VnLaw-QA FastAPI application.

    Args:
        settings: Optional explicit runtime settings for tests or custom
            bootstrap.

    Returns:
        Configured FastAPI application with health and legal QA routes.
    """
    runtime_settings = settings or get_settings()
    app = FastAPI(title="VnLaw-QA API", version="0.1.0")
    app.state.ask_rate_limiter = build_rate_limiter(runtime_settings)
    app.include_router(health_router)
    app.include_router(legal_qa_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    configure_cors(app, runtime_settings)
    return app


def configure_cors(app: FastAPI, settings: AppSettings) -> None:
    """Configure browser CORS for the API frontend."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )


app = create_app()
