"""Dependency providers for API route handlers."""

from __future__ import annotations

from functools import lru_cache

from src.api.settings import get_settings
from src.services.conversation_service import (
    ConversationService,
    InMemoryConversationRepository,
)
from src.services.legal_qa_api_service import LegalQAService
from src.services.legal_qa_workflow import build_legal_qa_service
from src.services.runtime_readiness import (
    QdrantCollectionReadinessProbe,
    RuntimeReadinessService,
)


@lru_cache(maxsize=1)
def _get_cached_legal_qa_service() -> LegalQAService:
    settings = get_settings()
    settings.validate_runtime_configuration()
    return build_legal_qa_service(settings=settings.to_legal_qa_runtime_settings())


async def get_legal_qa_service() -> LegalQAService:
    """Return the legal QA service used by request handlers.

    Returns:
        Cached Legal QA service. Fake mode is the default; real mode is selected
        only through runtime settings.
    """
    return _get_cached_legal_qa_service()


async def get_runtime_readiness_service() -> RuntimeReadinessService:
    """Return readiness evaluation configured without heavy dependencies.

    Returns:
        Service that validates local runtime configuration and, in real mode
        only, performs a read-only Qdrant collection metadata check.
    """
    settings = get_settings()
    qdrant_probe = None
    if settings.legal_qa_qdrant_url is not None:
        qdrant_probe = QdrantCollectionReadinessProbe(
            url=settings.legal_qa_qdrant_url,
            api_key=(
                settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key is not None
                else None
            ),
        )
    return RuntimeReadinessService(
        service_mode=settings.legal_qa_service_mode,
        configuration_issues=settings.runtime_configuration_issues(),
        qdrant_collection=settings.legal_qa_collection_name,
        qdrant_probe=qdrant_probe,
    )


@lru_cache(maxsize=1)
def _get_cached_conversation_service() -> ConversationService:
    return ConversationService(InMemoryConversationRepository())


async def get_conversation_service() -> ConversationService:
    """Return the process-local conversation service.

    Returns:
        Cached service backed by an in-memory development repository. Data is
        discarded on process restart and is not shared across workers.
    """
    return _get_cached_conversation_service()


def clear_legal_qa_service_cache() -> None:
    """Clear the cached Legal QA service for tests and runtime reconfiguration."""
    _get_cached_legal_qa_service.cache_clear()


def clear_conversation_service_cache() -> None:
    """Clear process-local conversation state for tests."""
    _get_cached_conversation_service.cache_clear()
