"""Deterministic preparation of untrusted conversation context for Legal QA."""

from __future__ import annotations

from dataclasses import dataclass

from src.api.schemas import (
    MAX_LEGAL_QA_CONTEXT_MESSAGES,
    LegalQAContextMessage,
    LegalQAContextRole,
    LegalQARequest,
)


@dataclass(frozen=True)
class PreparedLegalQAContextMessage:
    """Compact internal conversation message that is never citable evidence."""

    role: LegalQAContextRole
    content: str


@dataclass(frozen=True)
class PreparedLegalQAContext:
    """Prepared follow-up context passed through the Legal QA service boundary.

    `effective_question` remains the current user question. `compact_text` is
    reserved for future safe query processing and must not be treated as legal
    evidence or passed to citation validation as evidence.
    """

    effective_question: str
    conversation_id: str | None
    messages: tuple[PreparedLegalQAContextMessage, ...]
    compact_text: str

    @property
    def message_count(self) -> int:
        """Return the number of retained non-empty context messages."""
        return len(self.messages)


class LegalQAContextPreparer:
    """Trim and normalize recent user/assistant context deterministically."""

    def __init__(self, *, max_messages: int = MAX_LEGAL_QA_CONTEXT_MESSAGES) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be at least 1")
        self._max_messages = max_messages

    def prepare(self, request: LegalQARequest) -> PreparedLegalQAContext:
        """Prepare bounded context without rewriting the legal question.

        Args:
            request: Validated Legal QA API request.

        Returns:
            Prepared context containing only recent non-empty user/assistant
            messages. Context remains auxiliary and non-citable.
        """
        retained_messages = request.conversation_context[-self._max_messages :]
        messages = tuple(
            PreparedLegalQAContextMessage(
                role=message.role,
                content=content,
            )
            for message in retained_messages
            if (content := _normalize_content(message))
        )
        compact_text = "\n".join(f"{message.role.value}: {message.content}" for message in messages)
        return PreparedLegalQAContext(
            effective_question=request.question,
            conversation_id=request.conversation_id,
            messages=messages,
            compact_text=compact_text,
        )


def _normalize_content(message: LegalQAContextMessage) -> str:
    return message.content.strip()
