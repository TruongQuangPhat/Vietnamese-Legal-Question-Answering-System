"""Conversation lifecycle service and process-local repository."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import uuid4

from src.api.schemas import (
    DEFAULT_CONVERSATION_TITLE,
    Conversation,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationMessage,
    ConversationMessageCreateRequest,
    ConversationSummary,
    ConversationUpdateRequest,
)

IdFactory = Callable[[], str]
Clock = Callable[[], datetime]


class ConversationNotFoundError(LookupError):
    """Raised when a conversation identifier is not present in the repository."""


class ConversationRepository(Protocol):
    """Storage operations required by the conversation service."""

    def create(self, conversation: Conversation) -> Conversation:
        """Store and return a new conversation."""
        ...

    def list(self) -> list[Conversation]:
        """Return all stored conversations."""
        ...

    def get(self, conversation_id: str) -> Conversation:
        """Return a conversation or raise `ConversationNotFoundError`."""
        ...

    def update_title(
        self,
        conversation_id: str,
        title: str,
        updated_at: datetime,
    ) -> Conversation:
        """Update a conversation title and timestamp atomically."""
        ...

    def delete(self, conversation_id: str) -> None:
        """Delete a conversation or raise `ConversationNotFoundError`."""
        ...

    def add_message(
        self,
        conversation_id: str,
        message: ConversationMessage,
        updated_at: datetime,
    ) -> ConversationMessage:
        """Append and return a message while updating the conversation timestamp."""
        ...


class InMemoryConversationRepository:
    """Thread-safe process-local conversation repository.

    This implementation is a development/runtime placeholder. Its data is not
    shared across workers and is discarded when the process exits.
    """

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._lock = RLock()

    def create(self, conversation: Conversation) -> Conversation:
        """Store and return a defensive copy of a conversation."""
        with self._lock:
            self._conversations[conversation.id] = conversation.model_copy(deep=True)
            return conversation.model_copy(deep=True)

    def list(self) -> list[Conversation]:
        """Return defensive copies of all conversations."""
        with self._lock:
            return [
                conversation.model_copy(deep=True) for conversation in self._conversations.values()
            ]

    def get(self, conversation_id: str) -> Conversation:
        """Return a defensive copy of a conversation.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._lock:
            return self._require(conversation_id).model_copy(deep=True)

    def update_title(
        self,
        conversation_id: str,
        title: str,
        updated_at: datetime,
    ) -> Conversation:
        """Update title and timestamp atomically.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._lock:
            conversation = self._require(conversation_id)
            updated = conversation.model_copy(
                update={"title": title, "updated_at": updated_at},
                deep=True,
            )
            self._conversations[conversation_id] = updated
            return updated.model_copy(deep=True)

    def delete(self, conversation_id: str) -> None:
        """Delete a conversation.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._lock:
            self._require(conversation_id)
            del self._conversations[conversation_id]

    def add_message(
        self,
        conversation_id: str,
        message: ConversationMessage,
        updated_at: datetime,
    ) -> ConversationMessage:
        """Append a message and update the parent timestamp atomically.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        with self._lock:
            conversation = self._require(conversation_id)
            stored_message = message.model_copy(deep=True)
            updated = conversation.model_copy(
                update={
                    "messages": [*conversation.messages, stored_message],
                    "updated_at": updated_at,
                },
                deep=True,
            )
            self._conversations[conversation_id] = updated
            return stored_message.model_copy(deep=True)

    def _require(self, conversation_id: str) -> Conversation:
        try:
            return self._conversations[conversation_id]
        except KeyError as exc:
            raise ConversationNotFoundError(conversation_id) from exc


class ConversationService:
    """Coordinates validated conversation use cases without invoking legal QA."""

    def __init__(
        self,
        repository: ConversationRepository,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or _utc_now
        self._id_factory = id_factory or _new_id

    def create(self, request: ConversationCreateRequest) -> ConversationSummary:
        """Create a conversation and return its summary."""
        timestamp = self._timestamp()
        conversation = Conversation(
            id=self._id_factory(),
            title=request.title or DEFAULT_CONVERSATION_TITLE,
            created_at=timestamp,
            updated_at=timestamp,
            messages=[],
        )
        return _to_summary(self._repository.create(conversation))

    def list(self) -> list[ConversationSummary]:
        """Return summaries sorted by most recent update first."""
        conversations = sorted(
            self._repository.list(),
            key=lambda conversation: conversation.updated_at,
            reverse=True,
        )
        return [_to_summary(conversation) for conversation in conversations]

    def get(self, conversation_id: str) -> ConversationDetail:
        """Return full conversation detail.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        return _to_detail(self._repository.get(conversation_id))

    def rename(
        self,
        conversation_id: str,
        request: ConversationUpdateRequest,
    ) -> ConversationSummary:
        """Rename a conversation and return its updated summary.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        conversation = self._repository.update_title(
            conversation_id,
            request.title,
            self._timestamp(),
        )
        return _to_summary(conversation)

    def delete(self, conversation_id: str) -> None:
        """Delete a conversation.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        self._repository.delete(conversation_id)

    def add_message(
        self,
        conversation_id: str,
        request: ConversationMessageCreateRequest,
    ) -> ConversationMessage:
        """Store a message without invoking retrieval or generation.

        Raises:
            ConversationNotFoundError: If the identifier is unknown.
        """
        timestamp = self._timestamp()
        message = ConversationMessage(
            id=self._id_factory(),
            role=request.role,
            content=request.content,
            created_at=timestamp,
        )
        return self._repository.add_message(conversation_id, message, timestamp)

    def _timestamp(self) -> datetime:
        timestamp = self._clock()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("conversation clock must return a timezone-aware datetime")
        return timestamp.astimezone(UTC)


def _to_summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages),
    )


def _to_detail(conversation: Conversation) -> ConversationDetail:
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=conversation.messages,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid4())
