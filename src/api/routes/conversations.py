"""Conversation contract routes for the Legal QA chat product."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.api.dependencies import get_conversation_service
from src.api.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationMessage,
    ConversationMessageCreateRequest,
    ConversationSummary,
    ConversationUpdateRequest,
)
from src.api.session_identity import SessionIdentity, get_session_identity
from src.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])
ConversationServiceDependency = Annotated[
    ConversationService,
    Depends(get_conversation_service),
]
SessionIdentityDependency = Annotated[
    SessionIdentity,
    Depends(get_session_identity),
]


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    service: ConversationServiceDependency,
    session: SessionIdentityDependency,
) -> list[ConversationSummary]:
    """Return conversation summaries ordered by most recent update."""
    return service.list(owner_id=session.owner_id)


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreateRequest,
    service: ConversationServiceDependency,
    session: SessionIdentityDependency,
) -> ConversationSummary:
    """Create a conversation without invoking legal QA."""
    return service.create(request, owner_id=session.owner_id)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    service: ConversationServiceDependency,
    session: SessionIdentityDependency,
) -> ConversationDetail:
    """Return a conversation and its stored messages.

    Raises:
        HTTPException: If the conversation identifier is unknown.
    """
    try:
        return service.get(conversation_id, owner_id=session.owner_id)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc


@router.patch("/{conversation_id}", response_model=ConversationSummary)
async def rename_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
    service: ConversationServiceDependency,
    session: SessionIdentityDependency,
) -> ConversationSummary:
    """Rename a conversation.

    Raises:
        HTTPException: If the conversation identifier is unknown.
    """
    try:
        return service.rename(conversation_id, request, owner_id=session.owner_id)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    service: ConversationServiceDependency,
    session: SessionIdentityDependency,
) -> Response:
    """Delete a conversation.

    Raises:
        HTTPException: If the conversation identifier is unknown.
    """
    try:
        service.delete(conversation_id, owner_id=session.owner_id)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationMessage,
    status_code=status.HTTP_201_CREATED,
)
async def add_conversation_message(
    conversation_id: str,
    request: ConversationMessageCreateRequest,
    service: ConversationServiceDependency,
    session: SessionIdentityDependency,
) -> ConversationMessage:
    """Store a message without invoking retrieval, generation, or legal QA.

    Raises:
        HTTPException: If the conversation identifier is unknown.
    """
    try:
        return service.add_message(conversation_id, request, owner_id=session.owner_id)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Conversation not found.",
    )
