"""Opt-in integration tests for the PostgreSQL conversation repository."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.api.schemas import (
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
    ConversationMessageRole,
    ConversationUpdateRequest,
)
from src.services.conversation_service import ConversationNotFoundError, ConversationService
from src.services.postgres_conversation_repository import PostgresConversationRepository

ALLOW_DB_TESTS_ENV = "LEGAL_QA_ALLOW_DB_TESTS"
APPLY_SCHEMA_ENV = "LEGAL_QA_APPLY_DB_SCHEMA"
DATABASE_URL_ENV = "LEGAL_QA_DATABASE_URL"
SCHEMA_PATH = Path("scripts/database/postgres_conversation_store.sql")
TEST_PREFIX = "postgres_integration"


pytestmark = pytest.mark.skipif(
    os.environ.get(ALLOW_DB_TESTS_ENV) != "1" or not os.environ.get(DATABASE_URL_ENV, "").strip(),
    reason=(
        f"requires {ALLOW_DB_TESTS_ENV}=1 and {DATABASE_URL_ENV}; "
        "use a dedicated dev/staging PostgreSQL database"
    ),
)


def test_postgres_conversation_repository_real_db_lifecycle() -> None:
    """Validate durable conversation lifecycle behavior against a real DB."""
    database_url = os.environ[DATABASE_URL_ENV].strip()
    psycopg = pytest.importorskip("psycopg")

    if os.environ.get(APPLY_SCHEMA_ENV) == "1":
        _apply_schema(psycopg, database_url)

    test_id = _test_id()
    service = ConversationService(
        PostgresConversationRepository(database_url),
        clock=lambda: datetime.now(UTC),
        id_factory=_id_factory(test_id),
    )

    conversation = service.create(ConversationCreateRequest(title=f"{test_id} original"))
    try:
        first = service.add_message(
            conversation.id,
            ConversationMessageCreateRequest(
                role=ConversationMessageRole.USER,
                content=f"{test_id} user message",
            ),
        )
        second = service.add_message(
            conversation.id,
            ConversationMessageCreateRequest(
                role=ConversationMessageRole.ASSISTANT,
                content=f"{test_id} assistant message",
            ),
        )

        detail = service.get(conversation.id)
        assert detail.title == f"{test_id} original"
        assert [message.id for message in detail.messages] == [first.id, second.id]
        assert [message.content for message in detail.messages] == [
            f"{test_id} user message",
            f"{test_id} assistant message",
        ]

        renamed = service.rename(
            conversation.id,
            ConversationUpdateRequest(title=f"{test_id} renamed"),
        )
        assert renamed.title == f"{test_id} renamed"
        assert conversation.id in [item.id for item in service.list()]

        service.delete(conversation.id)
        with pytest.raises(ConversationNotFoundError):
            service.get(conversation.id)
        assert _message_count(psycopg, database_url, conversation.id) == 0
    finally:
        _cleanup(psycopg, database_url, test_id)


def _apply_schema(psycopg: object, database_url: str) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(schema_sql)


def _message_count(psycopg: object, database_url: str, conversation_id: str) -> int:
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()[0]


def _cleanup(psycopg: object, database_url: str, test_id: str) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM conversations WHERE id LIKE %s OR title LIKE %s",
            (f"{test_id}%", f"{test_id}%"),
        )


def _id_factory(test_id: str) -> Callable[[], str]:
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"{test_id}_{counter}"

    return next_id


def _test_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{TEST_PREFIX}_{timestamp}_{secrets.token_hex(4)}"
