from __future__ import annotations

import pytest

from src.api.dependencies import clear_conversation_service_cache, get_conversation_service
from src.api.schemas import ConversationCreateRequest
from src.api.settings import AppSettings, RuntimeConfigurationError
from src.services.conversation_service import InMemoryConversationRepository


async def test_conversation_dependency_uses_memory_store_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings.from_env({"LEGAL_QA_CONVERSATION_STORE": "memory"})
    postgres_constructed = False

    def fail_if_postgres_is_constructed(*args, **kwargs):
        nonlocal postgres_constructed
        postgres_constructed = True
        raise AssertionError("postgres repository must not be constructed")

    monkeypatch.setattr("src.api.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr(
        "src.api.dependencies.PostgresConversationRepository",
        fail_if_postgres_is_constructed,
    )
    clear_conversation_service_cache()

    service = await get_conversation_service()
    conversation = service.create(ConversationCreateRequest(title="Memory"))

    assert conversation.title == "Memory"
    assert postgres_constructed is False


async def test_conversation_dependency_selects_postgres_store_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_CONVERSATION_STORE": "postgres",
            "LEGAL_QA_DATABASE_URL": "postgresql://user:secret@db.example/vnlaw",
        }
    )
    constructed_urls: list[str] = []

    def build_fake_postgres_repository(database_url: str) -> InMemoryConversationRepository:
        constructed_urls.append(database_url)
        return InMemoryConversationRepository()

    monkeypatch.setattr("src.api.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr(
        "src.api.dependencies.PostgresConversationRepository",
        build_fake_postgres_repository,
    )
    clear_conversation_service_cache()

    service = await get_conversation_service()
    conversation = service.create(ConversationCreateRequest(title="Postgres"))

    assert conversation.title == "Postgres"
    assert constructed_urls == ["postgresql://user:secret@db.example/vnlaw"]


async def test_conversation_dependency_rejects_postgres_store_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings.from_env({"LEGAL_QA_CONVERSATION_STORE": "postgres"})

    monkeypatch.setattr("src.api.dependencies.get_settings", lambda: settings)
    clear_conversation_service_cache()

    with pytest.raises(RuntimeConfigurationError, match="missing_database_url"):
        await get_conversation_service()
