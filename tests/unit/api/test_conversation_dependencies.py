from __future__ import annotations

import builtins

import pytest

from src.api.dependencies import (
    clear_conversation_service_cache,
    clear_legal_qa_service_cache,
    get_conversation_service,
    get_legal_qa_service,
)
from src.api.schemas import ConversationCreateRequest, LegalQARequest
from src.api.settings import AppSettings, RuntimeConfigurationError
from src.services.conversation_service import InMemoryConversationRepository
from src.services.legal_qa_api_service import LegalQAService


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


async def test_conversation_dependency_memory_store_does_not_import_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_CONVERSATION_STORE": "memory",
            "LEGAL_QA_DATABASE_URL": "postgresql://user:secret@db.example/vnlaw",
        }
    )
    original_import = builtins.__import__

    def fail_if_psycopg_is_imported(name, *args, **kwargs):
        if name == "psycopg":
            raise AssertionError("memory store must not import psycopg")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("src.api.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr(builtins, "__import__", fail_if_psycopg_is_imported)
    clear_conversation_service_cache()

    service = await get_conversation_service()
    conversation = service.create(ConversationCreateRequest(title="Memory"))

    assert conversation.title == "Memory"


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


async def test_legal_qa_dependency_builds_lazily_and_reuses_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings.from_env({"LEGAL_QA_SERVICE_MODE": "fake"})
    build_calls = 0

    def build_fake_service(runtime_settings: AppSettings) -> LegalQAService:
        nonlocal build_calls
        build_calls += 1
        assert runtime_settings is settings
        return LegalQAService()

    monkeypatch.setattr("src.api.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr("src.api.dependencies._build_legal_qa_service", build_fake_service)
    clear_legal_qa_service_cache()

    first = await get_legal_qa_service()
    second = await get_legal_qa_service()

    assert first is second
    assert build_calls == 1
    response = first.answer(LegalQARequest(question="Câu hỏi hợp lệ?"))
    assert response.decision == "answered"


async def test_legal_qa_dependency_sanitizes_invalid_real_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "real",
            "OPENROUTER_API_KEY": "must-not-appear",
        }
    )
    build_called = False

    def fail_if_built(runtime_settings: AppSettings) -> LegalQAService:
        nonlocal build_called
        build_called = True
        raise AssertionError("invalid config must fail before service construction")

    monkeypatch.setattr("src.api.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr("src.api.dependencies._build_legal_qa_service", fail_if_built)
    clear_legal_qa_service_cache()

    with pytest.raises(RuntimeConfigurationError) as exc_info:
        await get_legal_qa_service()

    assert build_called is False
    assert "must-not-appear" not in str(exc_info.value)
