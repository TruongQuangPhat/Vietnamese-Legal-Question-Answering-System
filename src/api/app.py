"""FastAPI application factory for the VnLaw-QA product API."""

from __future__ import annotations

import asyncio
import logging
import sys

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import warmup_cached_legal_qa_service
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
    configure_logging(runtime_settings)
    app = FastAPI(title="VnLaw-QA API", version="0.1.0")
    app.state.settings = runtime_settings
    app.state.ask_rate_limiter = build_rate_limiter(runtime_settings)
    app.include_router(health_router)
    app.include_router(legal_qa_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    configure_cors(app, runtime_settings)
    configure_embedding_warmup(app, runtime_settings)
    return app


def configure_embedding_warmup(app: FastAPI, settings: AppSettings) -> None:
    """Schedule optional background embedding warmup without blocking readiness."""
    if not settings.legal_qa_embedding_warmup_enabled:
        return

    @app.on_event("startup")
    async def _background_embedding_warmup() -> None:
        asyncio.create_task(_run_background_embedding_warmup(settings))


async def _run_background_embedding_warmup(settings: AppSettings) -> None:
    logger = logging.getLogger(__name__)
    try:
        with anyio.fail_after(settings.legal_qa_warmup_timeout_seconds):
            result = await anyio.to_thread.run_sync(
                warmup_cached_legal_qa_service,
                abandon_on_cancel=True,
            )
    except TimeoutError:
        logger.warning(
            "legal_qa_embedding_warmup_failed",
            extra={"exception_class": "TimeoutError"},
        )
        return
    except Exception as exc:
        logger.warning(
            "legal_qa_embedding_warmup_failed",
            extra={"exception_class": type(exc).__name__},
        )
        return
    logger.info(
        "legal_qa_embedding_warmup_completed",
        extra={
            "warmed": getattr(result, "warmed", False),
            "elapsed_ms": getattr(result, "elapsed_ms", 0),
        },
    )


def configure_cors(app: FastAPI, settings: AppSettings) -> None:
    """Configure browser CORS for the API frontend."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )


def configure_logging(settings: AppSettings) -> None:
    """Ensure application logs are emitted to stdout in container runtimes."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        root_logger.addHandler(handler)
    root_logger.setLevel(level)
    logging.getLogger("src.api.routes.legal_qa").setLevel(level)


app = create_app()
