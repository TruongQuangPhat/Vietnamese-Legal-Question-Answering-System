"""Generation result models, fallback policy, and citation guard for Phase 9B."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.retrieval.openrouter_config import FALLBACK_OPENROUTER_MODEL
from src.retrieval.prompting import PromptEvidence
from src.retrieval.selection import AnswerabilityDecision, EvidenceSelectionResult

FALLBACK_ANSWER_VI = (
    "Hiện tại hệ thống chưa tìm được căn cứ pháp lý đủ an toàn để trả lời chắc chắn. "
    "Các kết quả truy xuất có thể liên quan nhưng chưa đủ chính xác hoặc chưa đủ an "
    "toàn về điều/khoản/điểm để đưa ra câu trả lời có trích dẫn đáng tin cậy."
)
_CITATION_ID_PATTERN = re.compile(r"\[E([1-9][0-9]*)\]")


class CitationIssueSeverity(StrEnum):
    """Severity for lightweight citation guard diagnostics."""

    WARNING = "warning"
    ERROR = "error"


class RagCitation(BaseModel):
    """A real source citation mapped from an internal model citation ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    packet_id: str
    chunk_id: str | None = None
    citation: str | None = None
    law_id: str | None = None
    law_title: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    source_url: str | None = None


class UsedEvidence(BaseModel):
    """Selected evidence exposed to the LLM and available for citation mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    packet_id: str
    chunk_id: str | None = None
    citation: str | None = None
    source_url: str | None = None


class CitationIssue(BaseModel):
    """Citation issue found in generated model output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(..., min_length=1)
    severity: CitationIssueSeverity
    message: str = Field(..., min_length=1)
    evidence_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CitationCheckResult(BaseModel):
    """Result of lightweight citation ID validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cited_ids: list[str] = Field(default_factory=list)
    valid_citations: list[RagCitation] = Field(default_factory=list)
    issues: list[CitationIssue] = Field(default_factory=list)


class RagGenerationConfig(BaseModel):
    """Configuration for fallback-aware Naive RAG generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(FALLBACK_OPENROUTER_MODEL, min_length=1)
    provider: str = Field("openrouter", min_length=1)
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, gt=0)
    timeout_s: float = Field(30.0, gt=0.0)
    include_auxiliary_context: bool = True
    fail_on_invalid_citation: bool = False


class RagAnswerResult(BaseModel):
    """Structured result from the fallback-aware Naive RAG pipeline."""

    model_config = ConfigDict(extra="forbid")

    query: str
    decision: AnswerabilityDecision
    answer: str
    citations: list[RagCitation] = Field(default_factory=list)
    used_evidence: list[UsedEvidence] = Field(default_factory=list)
    fallback_reasons: list[str] = Field(default_factory=list)
    selection_warnings: list[str] = Field(default_factory=list)
    citation_issues: list[CitationIssue] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
    selection_metadata: dict[str, Any] = Field(default_factory=dict)
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
    llm_called: bool = False
    model: str | None = None
    provider: str | None = None
    errors: list[str] = Field(default_factory=list)


def build_fallback_result(
    *,
    query: str,
    decision: AnswerabilityDecision,
    selection_result: EvidenceSelectionResult | None = None,
    retrieval_metadata: dict[str, Any] | None = None,
    generation_config: RagGenerationConfig | None = None,
    errors: list[str] | None = None,
) -> RagAnswerResult:
    """Build a deterministic fallback result without calling an LLM."""
    config = generation_config or RagGenerationConfig()
    return RagAnswerResult(
        query=query,
        decision=decision,
        answer=FALLBACK_ANSWER_VI,
        citations=[],
        used_evidence=[],
        fallback_reasons=_fallback_reason_codes(selection_result),
        selection_warnings=_selection_warning_codes(selection_result),
        citation_issues=[],
        retrieval_metadata=retrieval_metadata or {},
        selection_metadata=_selection_metadata(selection_result),
        generation_metadata={"fallback": True},
        llm_called=False,
        model=config.model,
        provider=config.provider,
        errors=errors or [],
    )


def check_generated_citations(
    *,
    answer: str,
    prompt_evidence: list[PromptEvidence],
) -> CitationCheckResult:
    """Validate that model citation IDs exist in selected prompt evidence."""
    evidence_by_id = {item.evidence_id: item for item in prompt_evidence}
    cited_ids = list(dict.fromkeys(f"E{match}" for match in _CITATION_ID_PATTERN.findall(answer)))
    issues: list[CitationIssue] = []
    valid: list[RagCitation] = []

    for evidence_id in cited_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            issues.append(
                CitationIssue(
                    code="unknown_citation_id",
                    severity=CitationIssueSeverity.ERROR,
                    message=f"generated answer cited unknown evidence ID [{evidence_id}]",
                    evidence_id=evidence_id,
                )
            )
            continue
        valid.append(_citation_from_prompt_evidence(evidence))

    if answer.strip() and not cited_ids:
        issues.append(
            CitationIssue(
                code="missing_citation_id",
                severity=CitationIssueSeverity.WARNING,
                message="generated answer did not include any [E#] citation IDs",
            )
        )

    return CitationCheckResult(cited_ids=cited_ids, valid_citations=valid, issues=issues)


def used_evidence_from_prompt(prompt_evidence: list[PromptEvidence]) -> list[UsedEvidence]:
    """Return compact selected evidence metadata included in the prompt."""
    return [
        UsedEvidence(
            evidence_id=item.evidence_id,
            packet_id=item.packet_id,
            chunk_id=item.chunk_id,
            citation=item.citation,
            source_url=item.source_url,
        )
        for item in prompt_evidence
    ]


def _citation_from_prompt_evidence(evidence: PromptEvidence) -> RagCitation:
    return RagCitation(
        evidence_id=evidence.evidence_id,
        packet_id=evidence.packet_id,
        chunk_id=evidence.chunk_id,
        citation=evidence.citation,
        law_id=evidence.law_id,
        law_title=evidence.law_title,
        article_number=evidence.article_number,
        clause_number=evidence.clause_number,
        point_label=evidence.point_label,
        source_url=evidence.source_url,
    )


def _fallback_reason_codes(selection_result: EvidenceSelectionResult | None) -> list[str]:
    if selection_result is None:
        return []
    return [reason.code.value for reason in selection_result.fallback_reasons]


def _selection_warning_codes(selection_result: EvidenceSelectionResult | None) -> list[str]:
    if selection_result is None:
        return []
    return [warning.code.value for warning in selection_result.warnings]


def _selection_metadata(selection_result: EvidenceSelectionResult | None) -> dict[str, Any]:
    if selection_result is None:
        return {}
    return {
        "decision": selection_result.decision.value,
        "selected_count": selection_result.selected_count,
        "rejected_count": selection_result.rejected_count,
        "caution_selected_count": selection_result.caution_selected_count,
        "unsafe_rejected_count": selection_result.unsafe_rejected_count,
    }
