"""Pydantic schemas for the VnLaw-QA product API."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

MAX_QUESTION_LENGTH = 4000


class LegalQADecision(StrEnum):
    """Legal QA decision values returned by the API."""

    ANSWERED = "answered"
    FALLBACK = "fallback"
    ERROR = "error"


class LegalQARequest(BaseModel):
    """Request body for legal QA questions.

    Attributes:
        question: Vietnamese legal question. It is stripped and must be non-empty.
        top_k: Requested maximum evidence count for future retrieval integration.
        include_evidence: Whether evidence DTOs should be returned.
        include_debug: Reserved for future debug/admin behavior; ignored by the stub.
    """

    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_LENGTH)
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
