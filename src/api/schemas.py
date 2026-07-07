"""Pydantic schemas for the VnLaw-QA product API."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator

MAX_QUESTION_LENGTH = 4000
MAX_LEGAL_QA_CONTEXT_MESSAGES = 8
MAX_LEGAL_QA_CONTEXT_MESSAGE_LENGTH = 2000
MAX_CONVERSATION_TITLE_LENGTH = 120
MAX_MESSAGE_CONTENT_LENGTH = 20_000
DEFAULT_CONVERSATION_TITLE = "Cuộc trò chuyện mới"


class LegalQADecision(StrEnum):
    """Legal QA decision values returned by the API."""

    ANSWERED = "answered"
    ANSWERED_WITH_CAUTION = "answered_with_caution"
    FALLBACK = "fallback"
    ERROR = "error"


class ReadinessCheckDTO(BaseModel):
    """Sanitized result for one backend readiness check."""

    name: str
    ready: bool
    detail: str


class ReadinessResponse(BaseModel):
    """Backend readiness response with no credentials or sensitive context."""

    ready: bool
    service_mode: str
    checks: list[ReadinessCheckDTO]


class LegalQAContextRole(StrEnum):
    """Client roles accepted in recent Legal QA conversation context."""

    USER = "user"
    ASSISTANT = "assistant"


class LegalQAContextMessage(BaseModel):
    """One untrusted conversational message supplied for follow-up context.

    Conversation messages are never legal evidence and cannot be cited as such.
    Blank content is accepted at the API boundary and removed during preparation.
    """

    role: LegalQAContextRole
    content: str = Field(max_length=MAX_LEGAL_QA_CONTEXT_MESSAGE_LENGTH)
    created_at: AwareDatetime | None = None


class ConversationMessageRole(StrEnum):
    """Roles supported by stored conversation messages."""

    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage(BaseModel):
    """Public representation of one stored conversation message."""

    id: str = Field(min_length=1)
    role: ConversationMessageRole
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CONTENT_LENGTH)
    created_at: AwareDatetime


class Conversation(BaseModel):
    """Internal typed conversation record used by the conversation service."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=MAX_CONVERSATION_TITLE_LENGTH)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    messages: list[ConversationMessage] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    """Compact conversation representation returned by list and create routes."""

    id: str
    title: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    message_count: int = Field(ge=0)


class ConversationCreateRequest(BaseModel):
    """Request body for creating a conversation.

    A missing or blank title is normalized to the product's default title by
    the service.
    """

    title: str | None = Field(default=None, max_length=MAX_CONVERSATION_TITLE_LENGTH)

    @field_validator("title")
    @classmethod
    def strip_optional_title(cls, value: str | None) -> str | None:
        """Strip a supplied title and convert blank input to no title."""
        if value is None:
            return None
        return value.strip() or None


class ConversationUpdateRequest(BaseModel):
    """Request body for renaming an existing conversation."""

    title: str = Field(min_length=1, max_length=MAX_CONVERSATION_TITLE_LENGTH)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        """Strip and reject a blank replacement title."""
        title = value.strip()
        if not title:
            raise ValueError("title must not be empty")
        return title


class ConversationMessageCreateRequest(BaseModel):
    """Request body for adding a user or assistant message."""

    role: ConversationMessageRole
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CONTENT_LENGTH)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        """Strip and reject blank message content."""
        content = value.strip()
        if not content:
            raise ValueError("content must not be empty")
        return content


class ConversationDetail(BaseModel):
    """Full conversation representation including ordered messages."""

    id: str
    title: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    messages: list[ConversationMessage]


class LegalQARequest(BaseModel):
    """Request body for legal QA questions.

    Attributes:
        question: Vietnamese legal question. It is stripped and must be non-empty.
        conversation_id: Optional opaque conversation correlation identifier.
        conversation_context: Optional bounded recent user/assistant messages.
        top_k: Requested maximum evidence count for future retrieval integration.
        include_evidence: Whether evidence DTOs should be returned.
        include_debug: Reserved for future debug/admin behavior; ignored by the stub.
    """

    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_LENGTH)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=200)
    conversation_context: list[LegalQAContextMessage] = Field(
        default_factory=list,
        max_length=MAX_LEGAL_QA_CONTEXT_MESSAGES,
    )
    top_k: int = Field(default=10, ge=1, le=20)
    include_evidence: bool = True
    include_debug: bool = False

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        """Strip and validate the legal question.

        Args:
            value: Raw question text.

        Returns:
            Stripped question text.

        Raises:
            ValueError: If the stripped question is empty.
        """
        question = value.strip()
        if not question:
            raise ValueError("question must not be empty")
        return question

    @field_validator("conversation_id")
    @classmethod
    def strip_conversation_id(cls, value: str | None) -> str | None:
        """Strip an optional conversation identifier."""
        if value is None:
            return None
        conversation_id = value.strip()
        if not conversation_id:
            raise ValueError("conversation_id must not be empty")
        return conversation_id


class CitationDTO(BaseModel):
    """Citation returned for a citable child evidence unit."""

    evidence_id: str
    chunk_id: str
    law_id: str
    law_name: str
    citation: str
    source_url: HttpUrl
    hierarchy_path: str


class EvidenceDTO(BaseModel):
    """Selected citable evidence returned by the legal QA API."""

    evidence_id: str
    chunk_id: str
    law_id: str
    law_name: str
    citation: str
    text: str
    source_url: HttpUrl
    score: float


class ResponseMetadataDTO(BaseModel):
    """Metadata describing the API response and current stub workflow assumptions."""

    retrieval_strategy: str
    model: str | None
    reranking_used: bool
    latency_ms: int = Field(ge=0)
    conversation_context_used: bool = False
    conversation_context_message_count: int = Field(default=0, ge=0)
    follow_up_detected: bool = False
    retrieval_question_prepared: bool = False


class LegalQAResponse(BaseModel):
    """Stable response contract for legal QA answers.

    The API must only expose citable child evidence in `citations` and `evidence`.
    Parent article context is auxiliary in the future RAG workflow and is not part
    of this response contract unless represented by selected child evidence.
    """

    model_config = ConfigDict(use_enum_values=True)

    request_id: str
    decision: LegalQADecision
    answer: str
    citations: list[CitationDTO]
    evidence: list[EvidenceDTO]
    warnings: list[str]
    metadata: ResponseMetadataDTO
