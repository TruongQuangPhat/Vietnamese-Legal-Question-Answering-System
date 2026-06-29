"""Dependency providers for API route handlers."""

from __future__ import annotations

from functools import lru_cache

from src.api.settings import get_settings
from src.services.legal_qa_api_service import LegalQAService
from src.services.legal_qa_workflow import build_legal_qa_service


@lru_cache(maxsize=1)
def _get_cached_legal_qa_service() -> LegalQAService:
    settings = get_settings()
    return build_legal_qa_service(settings=settings.to_legal_qa_runtime_settings())


async def get_legal_qa_service() -> LegalQAService:
    """Return the legal QA service used by request handlers.

    Returns:
        Cached Legal QA service. Fake mode is the default; real mode is selected
        only through runtime settings.
    """
    return _get_cached_legal_qa_service()


def clear_legal_qa_service_cache() -> None:
    """Clear the cached Legal QA service for tests and runtime reconfiguration."""
    _get_cached_legal_qa_service.cache_clear()
