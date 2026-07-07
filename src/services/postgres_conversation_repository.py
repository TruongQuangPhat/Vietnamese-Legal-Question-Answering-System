"""PostgreSQL-backed conversation repository."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.api.schemas import Conversation, ConversationMessage
from src.services.conversation_service import ConversationNotFoundError

ConnectFactory = Callable[[], Any]


class PostgresConversationRepository:
    """Durable PostgreSQL implementation of the conversation repository.

    The repository opens database connections lazily when an operation is
    executed. Constructing it does not import psycopg or contact PostgreSQL, so
    default tests and memory-mode API usage remain independent of database
    infrastructure.
    """

    def __init__(
        self,
        database_url: str,
        *,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        """Initialize a lazy PostgreSQL conversation repository.

        Args:
            database_url: PostgreSQL connection URL from runtime configuration.
            connect_factory: Optional test hook for deterministic unit tests.
        """
        self._database_url = database_url
        self._connect_factory = connect_factory or self._connect

    def create(self, conversation: Conversation) -> Conversation:
        """Store and return a conversation without messages."""
        with self._connect_factory() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    conversation.id,
                    conversation.title,
                    conversation.created_at,
                    conversation.updated_at,
                ),
            )
        return conversation.model_copy(deep=True)

    def list(self) -> list[Conversation]:
        """Return all conversations with ordered messages."""
        with self._connect_factory() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC, created_at DESC, id DESC
                """
            ).fetchall()
            return [
                _conversation_from_row(
                    row,
                    messages=_fetch_messages(connection, conversation_id=row[0]),
                )
                for row in rows
            ]

    def get(self, conversation_id: str) -> Conversation:
        """Return one conversation.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._connect_factory() as connection:
            return _fetch_conversation(connection, conversation_id)

    def update_title(
        self,
        conversation_id: str,
        title: str,
        updated_at: datetime,
    ) -> Conversation:
        """Update a conversation title and timestamp.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._connect_factory() as connection:
            row = connection.execute(
                """
                UPDATE conversations
                SET title = %s, updated_at = %s
                WHERE id = %s
                RETURNING id, title, created_at, updated_at
                """,
                (title, updated_at, conversation_id),
            ).fetchone()
            if row is None:
                raise ConversationNotFoundError(conversation_id)
            return _conversation_from_row(
                row,
                messages=_fetch_messages(connection, conversation_id=conversation_id),
            )

    def delete(self, conversation_id: str) -> None:
        """Delete a conversation and its messages.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._connect_factory() as connection:
            row = connection.execute(
                "DELETE FROM conversations WHERE id = %s RETURNING id",
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise ConversationNotFoundError(conversation_id)

    def add_message(
        self,
        conversation_id: str,
        message: ConversationMessage,
        updated_at: datetime,
    ) -> ConversationMessage:
        """Append a message and update the parent conversation timestamp.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._connect_factory() as connection:
            row = connection.execute(
                """
                UPDATE conversations
                SET updated_at = %s
                WHERE id = %s
                RETURNING id
                """,
                (updated_at, conversation_id),
            ).fetchone()
            if row is None:
                raise ConversationNotFoundError(conversation_id)
            connection.execute(
                """
                INSERT INTO conversation_messages
                    (id, conversation_id, role, content, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    message.id,
                    conversation_id,
                    message.role.value,
                    message.content,
                    message.created_at,
                ),
            )
        return message.model_copy(deep=True)

    def _connect(self) -> Any:
        try:
            import psycopg
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "PostgreSQL conversation storage requires the 'postgres' optional extra."
            ) from exc
        return psycopg.connect(self._database_url)


def _fetch_conversation(connection: Any, conversation_id: str) -> Conversation:
    row = connection.execute(
        """
        SELECT id, title, created_at, updated_at
        FROM conversations
        WHERE id = %s
        """,
        (conversation_id,),
    ).fetchone()
    if row is None:
        raise ConversationNotFoundError(conversation_id)
    return _conversation_from_row(
        row,
        messages=_fetch_messages(connection, conversation_id=conversation_id),
    )


def _fetch_messages(connection: Any, *, conversation_id: str) -> list[ConversationMessage]:
    rows = connection.execute(
        """
        SELECT id, role, content, created_at
        FROM conversation_messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_id,),
    ).fetchall()
    return [
        ConversationMessage(
            id=row[0],
            role=row[1],
            content=row[2],
            created_at=row[3],
        )
        for row in rows
    ]


def _conversation_from_row(
    row: tuple[Any, ...],
    *,
    messages: list[ConversationMessage],
) -> Conversation:
    return Conversation(
        id=row[0],
        title=row[1],
        created_at=row[2],
        updated_at=row[3],
        messages=messages,
    )
