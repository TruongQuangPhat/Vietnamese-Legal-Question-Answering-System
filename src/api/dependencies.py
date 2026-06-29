"""Dependency providers for API route handlers."""

from __future__ import annotations

from functools import lru_cache

from src.services.legal_qa_api_service import LegalQAService
from src.services.legal_qa_workflow import build_legal_qa_service


@lru_cache(maxsize=1)
def get_legal_qa_service() -> LegalQAService:
    """Return the legal QA service used by request handlers.

    Returns:
        Cached Legal QA service. Fake mode is the default; real mode is selected
        only through runtime settings.
    """
    return build_legal_qa_service()
