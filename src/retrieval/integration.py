"""Integration smoke pipeline for dense retrieval baseline retrieval-side components.

The smoke pipeline composes dense retrieval, evidence assembly, and evidence
selection. It is read-only and does not call LLMs, generate answers, mutate
Qdrant, or mutate corpus files.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.retrieval.evaluation import (
    DEFAULT_EVAL_CUTOFFS,
    ManualRetrievalQuery,
    RetrievedHitSummary,
    evaluate_retrieval_result,
)
from src.retrieval.evidence import (
    ContextAssemblyConfig,
    EvidenceBundle,
    build_evidence_bundle,
)
from src.retrieval.models import DEFAULT_DENSE_VECTOR_NAME, RetrievalResult
from src.retrieval.selection import (
    AnswerabilityDecision,
    EvidenceSelectionConfig,
    EvidenceSelectionResult,
    select_evidence_for_answer,
)

DEFAULT_CONTEXT_PREVIEW_CHARS = 1200


class SmokeRetrieverProtocol(Protocol):
    """Minimal retriever/service surface used by the selection smoke pipeline."""

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        """Run one read-only retrieval query."""
        ...


EvidenceBuilder = Callable[[RetrievalResult, ContextAssemblyConfig | None], EvidenceBundle]
EvidenceSelector = Callable[
    [EvidenceBundle, EvidenceSelectionConfig | None, Sequence[Any], Sequence[Any]],
    EvidenceSelectionResult,
]


class SelectionSmokeError(ValueError):
    """Raised when smoke-test settings or inputs are invalid."""


class SelectionSmokeEvidenceSummary(BaseModel):
    """Compact selected/rejected evidence summary for smoke reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    rank: int = Field(..., ge=1)
    score: float | None = None
    chunk_id: str | None = None
    citation: str | None = None
    law_id: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    safety_level: str | None = None
    citation_scope: str | None = None
    has_auxiliary_context: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)


class SelectionSmokeQueryResult(BaseModel):
    """Per-query smoke result for retrieval, evidence, and selection."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    result_count: int = Field(0, ge=0)
    retrieval_elapsed_ms: float = Field(0.0, ge=0.0)
    elapsed_ms: float = Field(0.0, ge=0.0)
    evidence_packet_count: int = Field(0, ge=0)
    safe_count: int = Field(0, ge=0)
    caution_count: int = Field(0, ge=0)
    unsafe_count: int = Field(0, ge=0)
    selected_count: int = Field(0, ge=0)
    rejected_count: int = Field(0, ge=0)
    decision: AnswerabilityDecision | None = None
    allowed_decisions: list[AnswerabilityDecision] = Field(default_factory=list)
    decision_passed: bool = False
    fallback_reasons: list[str] = Field(default_factory=list)
    selection_warnings: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    top_result: RetrievedHitSummary | None = None
    selected_evidence: list[SelectionSmokeEvidenceSummary] = Field(default_factory=list)
    rejected_evidence: list[SelectionSmokeEvidenceSummary] = Field(default_factory=list)
    rendered_context_preview: str | None = None
    errors: list[str] = Field(default_factory=list)


class SelectionSmokeAggregate(BaseModel):
    """Aggregate smoke summary counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_allowed_count: int = Field(0, ge=0)
    answer_with_caution_allowed_count: int = Field(0, ge=0)
    fallback_required_count: int = Field(0, ge=0)
    needs_review_count: int = Field(0, ge=0)
    decision_pass_count: int = Field(0, ge=0)
    decision_fail_count: int = Field(0, ge=0)
    error_count: int = Field(0, ge=0)
    unsafe_evidence_count: int = Field(0, ge=0)
    selected_evidence_count: int = Field(0, ge=0)
    mean_retrieval_latency_ms: float = Field(0.0, ge=0.0)


class SelectionSmokeReport(BaseModel):
    """JSON-serializable selection smoke report."""

    model_config = ConfigDict(extra="forbid")

    report_type: str = "selection_smoke_report"
    run_type: str = "manual_selection_smoke"
    workflow_name: str = "retrieval_selection_smoke"
    started_at: datetime
    finished_at: datetime
    collection_name: str = Field(..., min_length=1)
    vector_name: str = Field(DEFAULT_DENSE_VECTOR_NAME, min_length=1)
    top_k: int = Field(..., gt=0)
    query_count: int = Field(..., ge=0)
    error_count: int = Field(0, ge=0)
    aggregate_decision_counts: dict[str, int] = Field(default_factory=dict)
    aggregate_pass_fail_counts: dict[str, int] = Field(default_factory=dict)
    aggregate_summary: SelectionSmokeAggregate
    selection_config: dict[str, Any]
    evidence_config: dict[str, Any]
    per_query: list[SelectionSmokeQueryResult] = Field(default_factory=list)


async def run_selection_smoke_for_query(
    query_record: ManualRetrievalQuery,
    retriever: SmokeRetrieverProtocol,
    *,
    collection_name: str,
    top_k: int = 20,
    evidence_config: ContextAssemblyConfig | None = None,
    selection_config: EvidenceSelectionConfig | None = None,
    enforce_risk_flags_in_selection: bool = False,
    context_preview_chars: int = DEFAULT_CONTEXT_PREVIEW_CHARS,
    evidence_builder: EvidenceBuilder = build_evidence_bundle,
    evidence_selector: EvidenceSelector | None = None,
) -> SelectionSmokeQueryResult:
    """Run retrieval, evidence assembly, and selection for one manual query."""
    if not collection_name.strip():
        raise SelectionSmokeError("collection_name must not be blank")
    if top_k <= 0:
        raise SelectionSmokeError("top_k must be positive")
    if context_preview_chars <= 0:
        raise SelectionSmokeError("context_preview_chars must be positive")

    selector = evidence_selector or _select_evidence_adapter
    started = time.perf_counter()
    try:
        retrieval_result = await retriever.retrieve(
            query=query_record.query,
            top_k=top_k,
            collection_name=collection_name,
        )
        evaluation = evaluate_retrieval_result(
            query_record,
            retrieval_result,
            top_k=top_k,
            cutoffs=DEFAULT_EVAL_CUTOFFS,
        )
        evidence_bundle = evidence_builder(retrieval_result, evidence_config)
        selector_risk_flags = evaluation.risk_flags if enforce_risk_flags_in_selection else ()
        selection = selector(
            evidence_bundle,
            selection_config,
            query_record.expected,
            selector_risk_flags,
        )
        allowed_decisions = _allowed_decisions(query_record)
        decision_passed = selection.decision in allowed_decisions
        return SelectionSmokeQueryResult(
            query_id=query_record.query_id,
            query=query_record.query,
            result_count=len(retrieval_result.results),
            retrieval_elapsed_ms=retrieval_result.elapsed_ms,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            evidence_packet_count=evidence_bundle.total_packets,
            safe_count=evidence_bundle.safe_count,
            caution_count=evidence_bundle.caution_count,
            unsafe_count=evidence_bundle.unsafe_count,
            selected_count=selection.selected_count,
            rejected_count=selection.rejected_count,
            decision=selection.decision,
            allowed_decisions=allowed_decisions,
            decision_passed=decision_passed,
            fallback_reasons=[reason.code for reason in selection.fallback_reasons],
            selection_warnings=[warning.code for warning in selection.warnings],
            risk_flags=[flag.code for flag in evaluation.risk_flags],
            top_result=evaluation.top_result,
            selected_evidence=[
                _selected_summary(item.packet) for item in selection.selected_evidence
            ],
            rejected_evidence=[
                _rejected_summary(item.packet, list(item.reasons))
                for item in selection.rejected_evidence
            ],
            rendered_context_preview=preview(selection.rendered_context, context_preview_chars),
        )
    except Exception as exc:
        return SelectionSmokeQueryResult(
            query_id=query_record.query_id,
            query=query_record.query,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            allowed_decisions=_allowed_decisions(query_record),
            errors=[str(exc)],
        )


async def run_selection_smoke_suite(
    query_records: Sequence[ManualRetrievalQuery],
    retriever: SmokeRetrieverProtocol,
    *,
    collection_name: str,
    vector_name: str = DEFAULT_DENSE_VECTOR_NAME,
    top_k: int = 20,
    evidence_config: ContextAssemblyConfig | None = None,
    selection_config: EvidenceSelectionConfig | None = None,
    enforce_risk_flags_in_selection: bool = False,
    context_preview_chars: int = DEFAULT_CONTEXT_PREVIEW_CHARS,
    evidence_builder: EvidenceBuilder = build_evidence_bundle,
    evidence_selector: EvidenceSelector | None = None,
) -> SelectionSmokeReport:
    """Run the selection smoke suite over manual query records."""
    if not query_records:
        raise SelectionSmokeError("query_records must not be empty")
    if not collection_name.strip():
        raise SelectionSmokeError("collection_name must not be blank")
    if not vector_name.strip():
        raise SelectionSmokeError("vector_name must not be blank")
    if top_k <= 0:
        raise SelectionSmokeError("top_k must be positive")

    started_at = datetime.now(UTC)
    per_query: list[SelectionSmokeQueryResult] = []
    for record in query_records:
        per_query.append(
            await run_selection_smoke_for_query(
                record,
                retriever,
                collection_name=collection_name,
                top_k=top_k,
                evidence_config=evidence_config,
                selection_config=selection_config,
                enforce_risk_flags_in_selection=enforce_risk_flags_in_selection,
                context_preview_chars=context_preview_chars,
                evidence_builder=evidence_builder,
                evidence_selector=evidence_selector,
            )
        )
    finished_at = datetime.now(UTC)
    aggregate = aggregate_smoke_results(per_query)
    return SelectionSmokeReport(
        started_at=started_at,
        finished_at=finished_at,
        collection_name=collection_name,
        vector_name=vector_name,
        top_k=top_k,
        query_count=len(query_records),
        error_count=aggregate.error_count,
        aggregate_decision_counts={
            AnswerabilityDecision.ANSWER_ALLOWED.value: aggregate.answer_allowed_count,
            AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED.value: (
                aggregate.answer_with_caution_allowed_count
            ),
            AnswerabilityDecision.FALLBACK_REQUIRED.value: aggregate.fallback_required_count,
            AnswerabilityDecision.NEEDS_REVIEW.value: aggregate.needs_review_count,
        },
        aggregate_pass_fail_counts={
            "decision_pass_count": aggregate.decision_pass_count,
            "decision_fail_count": aggregate.decision_fail_count,
        },
        aggregate_summary=aggregate,
        selection_config=(selection_config or EvidenceSelectionConfig()).model_dump(mode="json"),
        evidence_config=(evidence_config or ContextAssemblyConfig()).model_dump(mode="json"),
        per_query=per_query,
    )


def aggregate_smoke_results(
    results: Sequence[SelectionSmokeQueryResult],
) -> SelectionSmokeAggregate:
    """Aggregate smoke decisions, pass/fail counts, evidence counts, and latency."""
    return SelectionSmokeAggregate(
        answer_allowed_count=sum(
            1 for item in results if item.decision == AnswerabilityDecision.ANSWER_ALLOWED
        ),
        answer_with_caution_allowed_count=sum(
            1
            for item in results
            if item.decision == AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED
        ),
        fallback_required_count=sum(
            1 for item in results if item.decision == AnswerabilityDecision.FALLBACK_REQUIRED
        ),
        needs_review_count=sum(
            1 for item in results if item.decision == AnswerabilityDecision.NEEDS_REVIEW
        ),
        decision_pass_count=sum(1 for item in results if item.decision_passed),
        decision_fail_count=sum(
            1 for item in results if not item.decision_passed and not item.errors
        ),
        error_count=sum(1 for item in results if item.errors),
        unsafe_evidence_count=sum(item.unsafe_count for item in results),
        selected_evidence_count=sum(item.selected_count for item in results),
        mean_retrieval_latency_ms=_mean(
            item.retrieval_elapsed_ms for item in results if not item.errors
        ),
    )


def filter_query_records(
    records: Sequence[ManualRetrievalQuery],
    *,
    case_id: str | None,
) -> list[ManualRetrievalQuery]:
    """Filter manual records by query_id when requested."""
    if case_id is None:
        return list(records)
    filtered = [record for record in records if record.query_id == case_id]
    if not filtered:
        raise SelectionSmokeError(f"query_id not found in manual dataset: {case_id}")
    return filtered


def preview(text: str | None, max_chars: int) -> str | None:
    """Return a bounded whitespace-normalized preview."""
    if text is None:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _select_evidence_adapter(
    evidence_bundle: EvidenceBundle,
    selection_config: EvidenceSelectionConfig | None,
    expected_targets: Sequence[Any],
    risk_flags: Sequence[Any],
) -> EvidenceSelectionResult:
    return select_evidence_for_answer(
        evidence_bundle,
        selection_config,
        expected_targets=expected_targets,
        risk_flags=risk_flags,
    )


def _allowed_decisions(record: ManualRetrievalQuery) -> list[AnswerabilityDecision]:
    raw_decisions = record.allowed_decisions
    if raw_decisions is None:
        raw_decisions = [record.expected_decision] if record.expected_decision is not None else None
    if raw_decisions is None:
        return [
            AnswerabilityDecision.ANSWER_ALLOWED,
            AnswerabilityDecision.FALLBACK_REQUIRED,
            AnswerabilityDecision.NEEDS_REVIEW,
        ]
    return [AnswerabilityDecision(value) for value in raw_decisions]


def _selected_summary(packet: Any) -> SelectionSmokeEvidenceSummary:
    return SelectionSmokeEvidenceSummary(
        packet_id=packet.packet_id,
        rank=packet.rank,
        score=packet.score,
        chunk_id=packet.chunk_id,
        citation=packet.citation,
        law_id=packet.law_id,
        article_number=packet.article_number,
        clause_number=packet.clause_number,
        point_label=packet.point_label,
        safety_level=_enum_value(packet.safety_level),
        citation_scope=_enum_value(packet.citation_scope),
        has_auxiliary_context=packet.auxiliary_context is not None,
    )


def _rejected_summary(
    packet: Any,
    rejection_reasons: Sequence[Any],
) -> SelectionSmokeEvidenceSummary:
    summary = _selected_summary(packet)
    return summary.model_copy(
        update={"rejection_reasons": [_enum_value(reason) for reason in rejection_reasons]}
    )


def _mean(values: Sequence[float] | Any) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _enum_value(value: Any) -> str | None:
    """Serialize enum-like values as stable report strings."""
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return str(value)
