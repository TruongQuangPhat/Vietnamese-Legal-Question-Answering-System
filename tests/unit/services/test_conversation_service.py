from __future__ import annotations

import builtins
from datetime import UTC, datetime
from typing import Any

import pytest

from src.api.schemas import (
    Conversation,
    ConversationCreateRequest,
    ConversationMessage,
    ConversationMessageRole,
)
from src.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
    InMemoryConversationRepository,
)
from src.services.postgres_conversation_repository import PostgresConversationRepository


def test_memory_conversation_repository_instances_are_isolated() -> None:
    first_service = ConversationService(
        InMemoryConversationRepository(),
        clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
        id_factory=lambda: "conversation-1",
    )
    second_service = ConversationService(InMemoryConversationRepository())

    first_service.create(ConversationCreateRequest(title="Stored only once"))

    assert len(first_service.list()) == 1
    assert second_service.list() == []


def test_memory_conversation_repository_returns_defensive_copies() -> None:
    repository = InMemoryConversationRepository()
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    conversation = Conversation(
        id="conversation-1",
        title="Original",
        created_at=timestamp,
        updated_at=timestamp,
    )

    stored = repository.create(conversation)
    stored.messages.append(
        ConversationMessage(
            id="message-1",
            role=ConversationMessageRole.USER,
            content="Mutated outside repository",
            created_at=timestamp,
        )
    )

    assert repository.get("conversation-1").messages == []


def test_memory_conversation_repository_filters_by_owner() -> None:
    repository = InMemoryConversationRepository()
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    repository.create(
        Conversation(
            id="conversation-a",
            owner_id="owner-a",
            title="Owner A",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    repository.create(
        Conversation(
            id="conversation-b",
            owner_id="owner-b",
            title="Owner B",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    assert [conversation.id for conversation in repository.list(owner_id="owner-a")] == [
        "conversation-a"
    ]
    with pytest.raises(ConversationNotFoundError):
        repository.get("conversation-a", owner_id="owner-b")
    with pytest.raises(ConversationNotFoundError):
        repository.update_title(
            "conversation-a",
            "Blocked",
            timestamp,
            owner_id="owner-b",
        )
    with pytest.raises(ConversationNotFoundError):
        repository.delete("conversation-a", owner_id="owner-b")


def test_memory_conversation_repository_hides_null_owner_records_from_owner_scope() -> None:
    repository = InMemoryConversationRepository()
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    repository.create(
        Conversation(
            id="legacy-conversation",
            owner_id=None,
            title="Legacy",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    assert [conversation.id for conversation in repository.list()] == ["legacy-conversation"]
    assert repository.list(owner_id="owner-a") == []
    with pytest.raises(ConversationNotFoundError):
        repository.get("legacy-conversation", owner_id="owner-a")


def test_postgres_conversation_repository_constructor_is_lazy() -> None:
    connect_called = False

    def fail_if_connected():
        nonlocal connect_called
        connect_called = True
        raise AssertionError("constructor must not connect to PostgreSQL")

    PostgresConversationRepository(
        "postgresql://user:secret@db.example/vnlaw",
        connect_factory=fail_if_connected,
    )

    assert connect_called is False


def test_postgres_conversation_repository_lifecycle_with_fake_connection() -> None:
    state = _FakePostgresState()
    repository = PostgresConversationRepository(
        "postgresql://unused",
        connect_factory=lambda: _FakePostgresConnection(state),
    )
    created_at = datetime(2025, 1, 1, tzinfo=UTC)
    message_at = datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC)
    renamed_at = datetime(2025, 1, 1, 0, 0, 2, tzinfo=UTC)

    created = repository.create(
        Conversation(
            id="conversation-1",
            owner_id="owner-a",
            title="Original",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    message = repository.add_message(
        "conversation-1",
        ConversationMessage(
            id="message-1",
            role=ConversationMessageRole.USER,
            content="Xin chào",
            created_at=message_at,
        ),
        message_at,
        owner_id="owner-a",
    )
    renamed = repository.update_title("conversation-1", "Renamed", renamed_at)
    listed = repository.list(owner_id="owner-a")
    blocked_list = repository.list(owner_id="owner-b")
    detail = repository.get("conversation-1", owner_id="owner-a")
    with pytest.raises(ConversationNotFoundError):
        repository.get("conversation-1", owner_id="owner-b")
    with pytest.raises(ConversationNotFoundError):
        repository.update_title("conversation-1", "Blocked", renamed_at, owner_id="owner-b")
    with pytest.raises(ConversationNotFoundError):
        repository.add_message(
            "conversation-1",
            ConversationMessage(
                id="message-2",
                role=ConversationMessageRole.USER,
                content="Blocked",
                created_at=message_at,
            ),
            message_at,
            owner_id="owner-b",
        )
    with pytest.raises(ConversationNotFoundError):
        repository.delete("conversation-1", owner_id="owner-b")
    repository.delete("conversation-1", owner_id="owner-a")

    assert created.title == "Original"
    assert message.content == "Xin chào"
    assert renamed.title == "Renamed"
    assert renamed.updated_at == renamed_at
    assert listed[0].messages[0].id == "message-1"
    assert blocked_list == []
    assert detail.messages[0].content == "Xin chào"
    with pytest.raises(ConversationNotFoundError):
        repository.get("conversation-1")


def test_postgres_conversation_repository_hides_null_owner_records_from_owner_scope() -> None:
    state = _FakePostgresState()
    repository = PostgresConversationRepository(
        "postgresql://unused",
        connect_factory=lambda: _FakePostgresConnection(state),
    )
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)

    repository.create(
        Conversation(
            id="legacy-conversation",
            owner_id=None,
            title="Legacy",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    assert [conversation.id for conversation in repository.list()] == ["legacy-conversation"]
    assert repository.list(owner_id="owner-a") == []
    with pytest.raises(ConversationNotFoundError):
        repository.get("legacy-conversation", owner_id="owner-a")


def test_postgres_conversation_repository_reports_missing_optional_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psycopg":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    repository = PostgresConversationRepository("postgresql://user:secret@db.example/vnlaw")

    with pytest.raises(RuntimeError, match="postgres"):
        repository.list()


class _FakePostgresState:
    def __init__(self) -> None:
        self.conversations: dict[str, tuple[str, str | None, str, datetime, datetime]] = {}
        self.messages: dict[str, tuple[str, str, str | None, str, str, datetime]] = {}


class _FakePostgresCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class _FakePostgresConnection:
    def __init__(self, state: _FakePostgresState) -> None:
        self._state = state

    def __enter__(self) -> _FakePostgresConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(
        self,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> _FakePostgresCursor:
        normalized = " ".join(query.split())
        if normalized.startswith("INSERT INTO conversations"):
            conversation_id, owner_id, title, created_at, updated_at = params
            self._state.conversations[conversation_id] = (
                conversation_id,
                owner_id,
                title,
                created_at,
                updated_at,
            )
            return _FakePostgresCursor([])
        if normalized.startswith(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER"
        ) or normalized.startswith(
            "SELECT id, owner_id, title, created_at, updated_at FROM conversations ORDER"
        ):
            rows = sorted(
                self._state.conversations.values(),
                key=lambda row: (row[4], row[3], row[0]),
                reverse=True,
            )
            return _FakePostgresCursor(rows)
        if normalized.startswith(
            "SELECT id, owner_id, title, created_at, updated_at FROM conversations WHERE owner_id"
        ):
            owner_id = params[0]
            rows = [row for row in self._state.conversations.values() if row[1] == owner_id]
            return _FakePostgresCursor(
                sorted(rows, key=lambda row: (row[4], row[3], row[0]), reverse=True)
            )
        if normalized.startswith(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE"
        ) or normalized.startswith(
            "SELECT id, owner_id, title, created_at, updated_at FROM conversations WHERE"
        ):
            conversation_id = params[0]
            row = self._state.conversations.get(conversation_id)
            if len(params) > 1 and row is not None and row[1] != params[1]:
                row = None
            return _FakePostgresCursor([] if row is None else [row])
        if normalized.startswith("UPDATE conversations SET title"):
            title, updated_at, conversation_id = params[:3]
            row = self._state.conversations.get(conversation_id)
            if len(params) > 3 and row is not None and row[1] != params[3]:
                row = None
            if row is None:
                return _FakePostgresCursor([])
            updated = (conversation_id, row[1], title, row[3], updated_at)
            self._state.conversations[conversation_id] = updated
            return _FakePostgresCursor([updated])
        if normalized.startswith("UPDATE conversations SET updated_at"):
            updated_at, conversation_id = params[:2]
            row = self._state.conversations.get(conversation_id)
            if len(params) > 2 and row is not None and row[1] != params[2]:
                row = None
            if row is None:
                return _FakePostgresCursor([])
            self._state.conversations[conversation_id] = (
                conversation_id,
                row[1],
                row[2],
                row[3],
                updated_at,
            )
            return _FakePostgresCursor([(conversation_id,)])
        if normalized.startswith("DELETE FROM conversations"):
            conversation_id = params[0]
            row = self._state.conversations.get(conversation_id)
            if len(params) > 1 and row is not None and row[1] != params[1]:
                row = None
            if row is None:
                return _FakePostgresCursor([])
            del self._state.conversations[conversation_id]
            self._state.messages = {
                message_id: message
                for message_id, message in self._state.messages.items()
                if message[1] != conversation_id
            }
            return _FakePostgresCursor([(conversation_id,)])
        if normalized.startswith("INSERT INTO conversation_messages"):
            message_id, conversation_id, owner_id, role, content, created_at = params
            self._state.messages[message_id] = (
                message_id,
                conversation_id,
                owner_id,
                role,
                content,
                created_at,
            )
            return _FakePostgresCursor([])
        if normalized.startswith("SELECT id, role, content, created_at FROM conversation_messages"):
            conversation_id = params[0]
            rows = [
                (message_id, role, content, created_at)
                for message_id, stored_conversation_id, _owner_id, role, content, created_at in (
                    self._state.messages.values()
                )
                if stored_conversation_id == conversation_id
            ]
            return _FakePostgresCursor(
                sorted(rows, key=lambda row: (row[3], row[0])),
            )
        raise AssertionError(f"Unexpected SQL: {normalized}")
