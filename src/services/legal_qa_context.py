"""Deterministic preparation of untrusted conversation context for Legal QA."""

from __future__ import annotations

from dataclasses import dataclass

from src.api.schemas import (
    MAX_LEGAL_QA_CONTEXT_MESSAGES,
    MAX_QUESTION_LENGTH,
    LegalQAContextMessage,
    LegalQAContextRole,
    LegalQARequest,
)

CONTEXT_REFERENCE_PHRASES = (
    "cái đó",
    "điều đó",
    "việc đó",
    "quy định đó",
    "trường hợp đó",
    "trường hợp này",
    "đối với trường hợp này",
    "người đó",
    "bên đó",
    "hợp đồng này",
    "như trên",
    "như vậy",
    "nếu vậy",
)
FOLLOW_UP_PREFIXES = (
    "vậy",
    "còn",
    "còn nếu",
    "thế có",
    "thế còn",
    "thế thì",
    "như trên",
)
FOLLOW_UP_SUFFIXES = (
    "thì sao",
    "được không",
    "áp dụng cho ai",
)
STANDALONE_LEGAL_TOPIC_TERMS = (
    "bảo hiểm xã hội",
    "bảo hiểm y tế",
    "bị phạt",
    "bồi thường",
    "cấp thẻ",
    "đất đai",
    "điều kiện",
    "hợp đồng",
    "khởi kiện",
    "kết hôn",
    "ly hôn",
    "nghỉ hằng năm",
    "nghỉ phép",
    "nghĩa vụ",
    "người lao động",
    "quyền",
    "thời hiệu",
    "thuế",
    "trẻ em",
    "trợ cấp",
    "xử phạt",
)


@dataclass(frozen=True)
class PreparedLegalQAContextMessage:
    """Compact internal conversation message that is never citable evidence."""

    role: LegalQAContextRole
    content: str


@dataclass(frozen=True)
class PreparedLegalQAContext:
    """Prepared follow-up context passed through the Legal QA service boundary.

    `original_question` remains the user-facing question. `retrieval_question`
    may include one recent user topic anchor, but neither the anchor nor
    `compact_text` is legal evidence or citable material.
    """

    original_question: str
    retrieval_question: str
    conversation_id: str | None
    messages: tuple[PreparedLegalQAContextMessage, ...]
    compact_text: str
    context_used: bool
    follow_up_detected: bool

    @property
    def effective_question(self) -> str:
        """Return the original question used for answer generation."""
        return self.original_question

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
        """Prepare a bounded retrieval question without changing answer intent.

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
        follow_up_detected = _is_follow_up_question(request.question)
        retrieval_question, context_used = _prepare_retrieval_question(
            question=request.question,
            messages=messages,
            follow_up_detected=follow_up_detected,
        )
        return PreparedLegalQAContext(
            original_question=request.question,
            retrieval_question=retrieval_question,
            conversation_id=request.conversation_id,
            messages=messages,
            compact_text=compact_text,
            context_used=context_used,
            follow_up_detected=follow_up_detected,
        )


def _normalize_content(message: LegalQAContextMessage) -> str:
    return message.content.strip()


def _is_follow_up_question(question: str) -> bool:
    normalized_question = " ".join(question.casefold().split())
    if _has_context_reference(normalized_question):
        return True
    if _has_follow_up_prefix(normalized_question):
        return True
    if _has_standalone_legal_topic(normalized_question):
        return False
    return _has_follow_up_suffix(normalized_question)


def _has_context_reference(question: str) -> bool:
    return any(phrase in question for phrase in CONTEXT_REFERENCE_PHRASES)


def _has_follow_up_prefix(question: str) -> bool:
    return any(
        question == prefix or question.startswith(f"{prefix} ") for prefix in FOLLOW_UP_PREFIXES
    )


def _has_standalone_legal_topic(question: str) -> bool:
    return any(term in question for term in STANDALONE_LEGAL_TOPIC_TERMS)


def _has_follow_up_suffix(question: str) -> bool:
    return any(question.endswith(suffix) for suffix in FOLLOW_UP_SUFFIXES)


def _prepare_retrieval_question(
    *,
    question: str,
    messages: tuple[PreparedLegalQAContextMessage, ...],
    follow_up_detected: bool,
) -> tuple[str, bool]:
    if not follow_up_detected:
        return question, False

    prior_user_message = next(
        (message.content for message in reversed(messages) if message.role == "user"),
        None,
    )
    if not prior_user_message:
        return question, False

    available_anchor_length = MAX_QUESTION_LENGTH - len(question) - 1
    if available_anchor_length <= 0:
        return question, False

    topic_anchor = prior_user_message[:available_anchor_length].rstrip()
    if not topic_anchor:
        return question, False
    return f"{topic_anchor} {question}", True
