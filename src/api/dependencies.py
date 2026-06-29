"""Dependency providers for API route handlers."""

from __future__ import annotations

from src.services.legal_qa_api_service import LegalQAService


def get_legal_qa_service() -> LegalQAService:
    """Return the legal QA service used by request handlers.

    Returns:
        Deterministic stub service. Real retrieval and generation are intentionally
        not wired into the API skeleton yet.
    """
    return LegalQAService()
