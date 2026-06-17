"""Manual dense retrieval evaluation and evidence-risk audit utilities.

This module measures dense retrieval baseline dense retrieval behavior. It does not call LLMs,
modify retrieval ranking, mutate Qdrant, or write corpus artifacts.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.retrieval.models import (
    DEFAULT_DENSE_VECTOR_NAME,
    RetrievalResult,
    RetrievedChunk,
)

DEFAULT_EVAL_CUTOFFS = (5, 10, 20)
REQUIRED_METADATA_FIELDS = ("law_id", "citation", "source_url")
MATCH_LEVELS = ("article", "clause", "point")
MatchLevel = Literal["article", "clause", "point"]
DecisionExpectation = Literal["answer_allowed", "fallback_required", "needs_review"]


class RetrievalEvaluationError(ValueError):
    """Raised when evaluation input files or settings are invalid."""


class ExpectedTarget(BaseModel):
    """Expected legal target for one manual retrieval query.

    Attributes:
        law_id: Stable law identifier expected in retrieval results.
        article_number: Expected legal Article number.
        clause_number: Optional expected Clause number.
        point_label: Optional expected Point label.
        match_level: Expected legal depth used for exact-hit matching.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    law_id: str = Field(..., min_length=1)
    article_number: str = Field(..., min_length=1)
    clause_number: str | None = None
    point_label: str | None = None
    match_level: MatchLevel

    @field_validator("law_id", "article_number", "clause_number", "point_label", "match_level")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Trim target fields and reject blank strings."""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("target fields must be non-blank when provided")
        return stripped

    @model_validator(mode="after")
    def validate_match_level_fields(self) -> ExpectedTarget:
        """Ensure the declared expected depth has enough hierarchy fields."""
        if self.match_level == "clause" and self.clause_number is None:
            raise ValueError("clause match_level requires clause_number")
        if self.match_level == "point":
            if self.clause_number is None:
                raise ValueError("point match_level requires clause_number")
            if self.point_label is None:
                raise ValueError("point match_level requires point_label")
        return self


class ManualRetrievalQuery(BaseModel):
    """One manual dense-retrieval evaluation query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    expected: list[ExpectedTarget] = Field(..., min_length=1)
    expected_decision: DecisionExpectation | None = None
    allowed_decisions: list[DecisionExpectation] | None = None
    notes: str | None = None

    @field_validator("query_id", "query", "notes")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim query text fields and reject blanks where values are present."""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("text fields must be non-blank when provided")
        return stripped

    @field_validator("allowed_decisions")
    @classmethod
    def validate_allowed_decisions(
        cls,
        value: list[DecisionExpectation] | None,
    ) -> list[DecisionExpectation] | None:
        """Require non-empty, de-duplicated allowed decision lists when present."""
        if value is None:
            return None
        if not value:
            raise ValueError("allowed_decisions must not be empty when provided")
        deduplicated = list(dict.fromkeys(value))
        return deduplicated


class TargetMatchResult(BaseModel):
    """Best observed ranks for one expected target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: ExpectedTarget
    article_match_rank: int | None = Field(None, ge=1)
    clause_match_rank: int | None = Field(None, ge=1)
    point_match_rank: int | None = Field(None, ge=1)
    best_exact_rank: int | None = Field(None, ge=1)
    exact_match_depth: MatchLevel | None = None


class RetrievedHitSummary(BaseModel):
    """Compact retrieved chunk summary included in evaluation reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(..., ge=1)
    score: float
    chunk_id: str | None = None
    law_id: str | None = None
    law_name: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    citation: str | None = None
    source_url: str | None = None
    text_preview: str | None = None
    parent_text_preview: str | None = None
    issue_count: int = Field(0, ge=0)


class EvidenceRiskFlag(BaseModel):
    """Conservative structural risk flag for retrieval evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    severity: str = Field("warning", min_length=1)
    rank: int | None = Field(None, ge=1)
    chunk_id: str | None = None
    target: ExpectedTarget | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PerQueryEvaluationResult(BaseModel):
    """Metrics and evidence-risk audit result for one manual query."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    notes: str | None = None
    expected: list[ExpectedTarget]
    top_k: int = Field(..., gt=0)
    result_count: int = Field(..., ge=0)
    empty_result: bool = False
    retrieval_error: str | None = None
    elapsed_ms: float = Field(..., ge=0.0)
    retriever_elapsed_ms: float | None = Field(None, ge=0.0)
    issue_count: int = Field(0, ge=0)
    metadata_completeness_rate: float = Field(..., ge=0.0, le=1.0)
    best_article_rank: int | None = Field(None, ge=1)
    article_match_rank: int | None = Field(None, ge=1)
    clause_match_rank: int | None = Field(None, ge=1)
    point_match_rank: int | None = Field(None, ge=1)
    best_rank_by_match_level: dict[str, int | None] = Field(default_factory=dict)
    best_exact_rank: int | None = Field(None, ge=1)
    exact_match_depth: MatchLevel | None = None
    reciprocal_rank_at_20: float = Field(0.0, ge=0.0, le=1.0)
    article_hit_at: dict[str, bool] = Field(default_factory=dict)
    exact_hit_at: dict[str, bool] = Field(default_factory=dict)
    target_matches: list[TargetMatchResult] = Field(default_factory=list)
    top_result: RetrievedHitSummary | None = None
    retrieved: list[RetrievedHitSummary] = Field(default_factory=list)
    risk_flags: list[EvidenceRiskFlag] = Field(default_factory=list)


class AggregateRetrievalMetrics(BaseModel):
    """Aggregate metrics for a manual dense retrieval evaluation run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_count: int = Field(..., ge=0)
    evaluated_query_count: int = Field(..., ge=0)
    error_count: int = Field(0, ge=0)
    empty_result_count: int = Field(0, ge=0)
    issue_count: int = Field(0, ge=0)
    risk_flag_count: int = Field(0, ge=0)
    metadata_completeness_rate: float = Field(0.0, ge=0.0, le=1.0)
    mean_latency_ms: float = Field(0.0, ge=0.0)
    recall_at_5: float = Field(0.0, ge=0.0, le=1.0)
    recall_at_10: float = Field(0.0, ge=0.0, le=1.0)
    recall_at_20: float = Field(0.0, ge=0.0, le=1.0)
    mrr_at_20: float = Field(0.0, ge=0.0, le=1.0)
    article_hit_at_5: float = Field(0.0, ge=0.0, le=1.0)
    article_hit_at_10: float = Field(0.0, ge=0.0, le=1.0)
    article_hit_at_20: float = Field(0.0, ge=0.0, le=1.0)
    exact_hit_at_5: float = Field(0.0, ge=0.0, le=1.0)
    exact_hit_at_10: float = Field(0.0, ge=0.0, le=1.0)
    exact_hit_at_20: float = Field(0.0, ge=0.0, le=1.0)


class DenseRetrievalEvaluationReport(BaseModel):
    """JSON-serializable dense retrieval evaluation report."""

    model_config = ConfigDict(extra="forbid")

    report_type: str = "dense_retrieval_evaluation_report"
    run_type: str = "manual_dense_retrieval_sanity"
    pipeline_stage: str = "retrieval_evaluation"
    started_at: datetime
    finished_at: datetime
    collection_name: str = Field(..., min_length=1)
    vector_name: str = Field(DEFAULT_DENSE_VECTOR_NAME, min_length=1)
    top_k: int = Field(..., gt=0)
    cutoffs: list[int]
    query_count: int = Field(..., ge=0)
    aggregate_metrics: AggregateRetrievalMetrics
    per_query: list[PerQueryEvaluationResult]


class DenseRetrieverProtocol(Protocol):
    """Minimal retriever surface required by the evaluator."""

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        """Run one read-only retrieval query."""
        ...


def load_manual_retrieval_queries(path: Path | str) -> list[ManualRetrievalQuery]:
    """Load manual retrieval queries from a UTF-8 JSONL file.

    Args:
        path: JSONL file path.

    Returns:
        Validated manual query records in file order.

    Raises:
        RetrievalEvaluationError: If any line is invalid JSON or fails schema
            validation.
    """
    input_path = Path(path)
    records: list[ManualRetrievalQuery] = []
    try:
        with input_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    records.append(ManualRetrievalQuery.model_validate(payload))
                except json.JSONDecodeError as exc:
                    raise RetrievalEvaluationError(
                        f"{input_path}:{line_number}: invalid JSON: {exc.msg}"
                    ) from exc
                except ValidationError as exc:
                    raise RetrievalEvaluationError(
                        f"{input_path}:{line_number}: invalid query record: {exc}"
                    ) from exc
    except OSError as exc:
        raise RetrievalEvaluationError(f"unable to read query dataset {input_path}: {exc}") from exc
    except UnicodeError as exc:
        raise RetrievalEvaluationError(f"query dataset is not valid UTF-8: {exc}") from exc

    if not records:
        raise RetrievalEvaluationError(f"query dataset is empty: {input_path}")
    return records


async def evaluate_dense_retrieval(
    retriever: DenseRetrieverProtocol,
    queries: Sequence[ManualRetrievalQuery],
    *,
    collection_name: str,
    vector_name: str = DEFAULT_DENSE_VECTOR_NAME,
    top_k: int = 20,
    cutoffs: Sequence[int] = DEFAULT_EVAL_CUTOFFS,
) -> DenseRetrievalEvaluationReport:
    """Evaluate read-only dense retrieval over manual expected targets.

    Args:
        retriever: Injected retriever or service.
        queries: Manual query records.
        collection_name: Existing Qdrant collection queried by the retriever.
        vector_name: Dense vector name used by the retriever.
        top_k: Number of results requested per query.
        cutoffs: Metric cutoffs. Values above ``top_k`` are ignored.

    Returns:
        Typed evaluation report with per-query and aggregate metrics.

    Raises:
        RetrievalEvaluationError: If settings are invalid.
    """
    if not collection_name.strip():
        raise RetrievalEvaluationError("collection_name must not be blank")
    if not vector_name.strip():
        raise RetrievalEvaluationError("vector_name must not be blank")
    if top_k <= 0:
        raise RetrievalEvaluationError("top_k must be positive")
    normalized_cutoffs = sorted({cutoff for cutoff in cutoffs if 0 < cutoff <= top_k})
    if not normalized_cutoffs:
        raise RetrievalEvaluationError("at least one positive cutoff within top_k is required")

    started_at = datetime.now(UTC)
    per_query: list[PerQueryEvaluationResult] = []
    for record in queries:
        started = time.perf_counter()
        try:
            result = await retriever.retrieve(
                query=record.query,
                top_k=top_k,
                collection_name=collection_name,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            per_query.append(
                evaluate_retrieval_result(
                    record,
                    result,
                    top_k=top_k,
                    cutoffs=normalized_cutoffs,
                    elapsed_ms=elapsed_ms,
                )
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            per_query.append(
                build_error_result(
                    record,
                    top_k=top_k,
                    cutoffs=normalized_cutoffs,
                    elapsed_ms=elapsed_ms,
                    error=str(exc),
                )
            )
    finished_at = datetime.now(UTC)
    aggregate = aggregate_metrics(per_query, cutoffs=normalized_cutoffs)
    return DenseRetrievalEvaluationReport(
        started_at=started_at,
        finished_at=finished_at,
        collection_name=collection_name,
        vector_name=vector_name,
        top_k=top_k,
        cutoffs=list(normalized_cutoffs),
        query_count=len(queries),
        aggregate_metrics=aggregate,
        per_query=per_query,
    )


def evaluate_retrieval_result(
    record: ManualRetrievalQuery,
    result: RetrievalResult,
    *,
    top_k: int,
    cutoffs: Sequence[int],
    elapsed_ms: float | None = None,
) -> PerQueryEvaluationResult:
    """Evaluate one retrieval result against manual expected targets."""
    hits = list(result.results[:top_k])
    target_matches = [target_match_result(target, hits) for target in record.expected]
    best_article = _min_rank(match.article_match_rank for match in target_matches)
    best_clause = _min_rank(match.clause_match_rank for match in target_matches)
    best_point = _min_rank(match.point_match_rank for match in target_matches)
    best_exact = _min_rank(match.best_exact_rank for match in target_matches)
    best_by_level = best_rank_by_match_level(target_matches)
    exact_depth = exact_match_depth(target_matches)
    article_hit_at = {str(cutoff): _rank_within(best_article, cutoff) for cutoff in cutoffs}
    exact_hit_at = {str(cutoff): _rank_within(best_exact, cutoff) for cutoff in cutoffs}
    retrieved = [summarize_hit(hit) for hit in hits]
    issue_count = len(result.issues) + sum(len(hit.issues) for hit in hits)
    metadata_rate = metadata_completeness_rate(hits)
    risk_flags = build_risk_flags(record.expected, hits, target_matches)
    effective_elapsed = elapsed_ms if elapsed_ms is not None else result.elapsed_ms

    return PerQueryEvaluationResult(
        query_id=record.query_id,
        query=record.query,
        notes=record.notes,
        expected=record.expected,
        top_k=top_k,
        result_count=len(hits),
        empty_result=not hits,
        elapsed_ms=effective_elapsed,
        retriever_elapsed_ms=result.elapsed_ms,
        issue_count=issue_count,
        metadata_completeness_rate=metadata_rate,
        best_article_rank=best_article,
        article_match_rank=best_article,
        clause_match_rank=best_clause,
        point_match_rank=best_point,
        best_rank_by_match_level=best_by_level,
        best_exact_rank=best_exact,
        exact_match_depth=exact_depth,
        reciprocal_rank_at_20=reciprocal_rank(best_exact, cutoff=20),
        article_hit_at=article_hit_at,
        exact_hit_at=exact_hit_at,
        target_matches=target_matches,
        top_result=retrieved[0] if retrieved else None,
        retrieved=retrieved,
        risk_flags=risk_flags,
    )


def target_match_result(
    target: ExpectedTarget,
    hits: Sequence[RetrievedChunk],
) -> TargetMatchResult:
    """Compute best Article, Clause, Point, and exact-depth ranks for a target."""
    exact_rank = best_exact_rank(target, hits)
    return TargetMatchResult(
        target=target,
        article_match_rank=best_article_rank(target, hits),
        clause_match_rank=best_clause_rank(target, hits),
        point_match_rank=best_point_rank(target, hits),
        best_exact_rank=exact_rank,
        exact_match_depth=target.match_level if exact_rank is not None else None,
    )


def build_error_result(
    record: ManualRetrievalQuery,
    *,
    top_k: int,
    cutoffs: Sequence[int],
    elapsed_ms: float,
    error: str,
) -> PerQueryEvaluationResult:
    """Build a per-query result for a retrieval exception."""
    return PerQueryEvaluationResult(
        query_id=record.query_id,
        query=record.query,
        notes=record.notes,
        expected=record.expected,
        top_k=top_k,
        result_count=0,
        empty_result=True,
        retrieval_error=error,
        elapsed_ms=elapsed_ms,
        issue_count=1,
        metadata_completeness_rate=0.0,
        reciprocal_rank_at_20=0.0,
        article_hit_at={str(cutoff): False for cutoff in cutoffs},
        exact_hit_at={str(cutoff): False for cutoff in cutoffs},
        target_matches=[
            TargetMatchResult(
                target=target,
                article_match_rank=None,
                clause_match_rank=None,
                point_match_rank=None,
                best_exact_rank=None,
                exact_match_depth=None,
            )
            for target in record.expected
        ],
        risk_flags=[
            EvidenceRiskFlag(
                code="retrieval_error",
                severity="error",
                message=error,
            )
        ],
    )


def matches_article(target: ExpectedTarget, chunk: RetrievedChunk) -> bool:
    """Return whether a chunk matches the expected law and Article."""
    return _same(target.law_id, chunk.law_id) and _same(target.article_number, chunk.article_number)


def matches_clause(target: ExpectedTarget, chunk: RetrievedChunk) -> bool:
    """Return whether a chunk matches the expected law, Article, and Clause."""
    return matches_article(target, chunk) and _same(target.clause_number, chunk.clause_number)


def matches_point(target: ExpectedTarget, chunk: RetrievedChunk) -> bool:
    """Return whether a chunk matches the expected law, Article, Clause, and Point."""
    return matches_clause(target, chunk) and _same(target.point_label, chunk.point_label)


def matches_expected_target(target: ExpectedTarget, chunk: RetrievedChunk) -> bool:
    """Return whether a chunk matches the expected target at its declared depth."""
    if target.match_level == "article":
        return matches_article(target, chunk)
    if target.match_level == "clause":
        return matches_clause(target, chunk)
    return matches_point(target, chunk)


def article_level_match(target: ExpectedTarget, chunk: RetrievedChunk) -> bool:
    """Compatibility alias for Article-depth matching."""
    return matches_article(target, chunk)


def exact_provision_match(target: ExpectedTarget, chunk: RetrievedChunk) -> bool:
    """Return whether a chunk matches the target's declared exact match level."""
    return matches_expected_target(target, chunk)


def best_article_rank(target: ExpectedTarget, hits: Sequence[RetrievedChunk]) -> int | None:
    """Return the first rank with a law+Article match."""
    return _first_rank(hit for hit in hits if matches_article(target, hit))


def best_clause_rank(target: ExpectedTarget, hits: Sequence[RetrievedChunk]) -> int | None:
    """Return the first rank with a law+Article+Clause match, when constrained."""
    if target.clause_number is None:
        return None
    return _first_rank(hit for hit in hits if matches_clause(target, hit))


def best_point_rank(target: ExpectedTarget, hits: Sequence[RetrievedChunk]) -> int | None:
    """Return the first rank with a law+Article+Clause+Point match, when constrained."""
    if target.clause_number is None or target.point_label is None:
        return None
    return _first_rank(hit for hit in hits if matches_point(target, hit))


def best_exact_rank(target: ExpectedTarget, hits: Sequence[RetrievedChunk]) -> int | None:
    """Return the first rank matching the target's declared exact depth."""
    return _first_rank(hit for hit in hits if matches_expected_target(target, hit))


def best_rank_by_match_level(
    target_matches: Sequence[TargetMatchResult],
) -> dict[str, int | None]:
    """Return the best exact rank among targets grouped by expected match level."""
    return {
        level: _min_rank(
            match.best_exact_rank for match in target_matches if match.target.match_level == level
        )
        for level in MATCH_LEVELS
    }


def exact_match_depth(target_matches: Sequence[TargetMatchResult]) -> MatchLevel | None:
    """Return the match level that produced the best exact rank."""
    ranked = [
        match
        for match in target_matches
        if match.best_exact_rank is not None and match.exact_match_depth is not None
    ]
    if not ranked:
        return None
    return min(ranked, key=lambda match: match.best_exact_rank or 0).exact_match_depth


def reciprocal_rank(rank: int | None, *, cutoff: int) -> float:
    """Return reciprocal rank at cutoff."""
    if rank is None or rank > cutoff:
        return 0.0
    return 1.0 / rank


def metadata_completeness_rate(hits: Sequence[RetrievedChunk]) -> float:
    """Compute completeness for law ID, citation, and source URL metadata."""
    if not hits:
        return 0.0
    present = 0
    total = len(hits) * len(REQUIRED_METADATA_FIELDS)
    for hit in hits:
        for field_name in REQUIRED_METADATA_FIELDS:
            if getattr(hit, field_name):
                present += 1
    return present / total


def build_risk_flags(
    expected: Sequence[ExpectedTarget],
    hits: Sequence[RetrievedChunk],
    target_matches: Sequence[TargetMatchResult],
) -> list[EvidenceRiskFlag]:
    """Build conservative evidence/citation risk flags from structure only."""
    flags: list[EvidenceRiskFlag] = []
    if not hits:
        return [
            EvidenceRiskFlag(
                code="empty_results",
                severity="error",
                message="retrieval returned no results",
            )
        ]

    expected_laws = {target.law_id for target in expected}
    top = hits[0]
    if top.law_id not in expected_laws:
        flags.append(
            EvidenceRiskFlag(
                code="top_result_from_wrong_law",
                message="top result law_id does not match any expected target law_id",
                rank=top.rank,
                chunk_id=top.chunk_id,
                details={
                    "expected_targets": [_target_details(target) for target in expected],
                    "top_result": _hit_details(top),
                    "top_law_id": top.law_id,
                    "expected_law_ids": sorted(expected_laws),
                },
            )
        )

    best_article = _min_rank(match.article_match_rank for match in target_matches)
    best_exact = _min_rank(match.best_exact_rank for match in target_matches)
    best_article_hit = _hit_at_rank(hits, best_article)
    if (
        best_article is not None
        and best_article > 1
        and not any(matches_article(target, top) for target in expected)
    ):
        flags.append(
            EvidenceRiskFlag(
                code="top_result_wrong_article_when_expected_article_exists_lower",
                message="top result is not an expected Article, but an expected Article appears lower",
                rank=top.rank,
                chunk_id=top.chunk_id,
                details={
                    "expected_targets": [_target_details(target) for target in expected],
                    "best_article_rank": best_article,
                    "best_exact_rank": best_exact,
                    "top_result": _hit_details(top),
                    "matched_lower_result": _hit_details(best_article_hit),
                },
            )
        )

    for match in target_matches:
        target = match.target
        if target.match_level == "article":
            continue
        if match.article_match_rank is not None and match.best_exact_rank is None:
            matched_article = _hit_at_rank(hits, match.article_match_rank)
            flags.append(
                EvidenceRiskFlag(
                    code="expected_article_hit_without_exact_clause_hit",
                    message=(
                        "an expected Article was retrieved, but the required "
                        "clause/point target was not retrieved"
                    ),
                    rank=match.article_match_rank,
                    chunk_id=matched_article.chunk_id if matched_article else None,
                    target=target,
                    details={
                        "expected_target": _target_details(target),
                        "expected_match_level": target.match_level,
                        "best_article_rank": match.article_match_rank,
                        "best_exact_rank": match.best_exact_rank,
                        "top_result": _hit_details(top),
                        "matched_lower_result": _hit_details(matched_article),
                    },
                )
            )

    for hit in hits:
        if not hit.citation:
            flags.append(
                EvidenceRiskFlag(
                    code="metadata_missing_citation",
                    severity="error",
                    message="retrieved chunk is missing citation metadata",
                    rank=hit.rank,
                    chunk_id=hit.chunk_id,
                )
            )
        if not hit.source_url:
            flags.append(
                EvidenceRiskFlag(
                    code="metadata_missing_source_url",
                    severity="error",
                    message="retrieved chunk is missing source_url metadata",
                    rank=hit.rank,
                    chunk_id=hit.chunk_id,
                )
            )
        if not hit.law_id:
            flags.append(
                EvidenceRiskFlag(
                    code="metadata_missing_law_id",
                    severity="error",
                    message="retrieved chunk is missing law_id metadata",
                    rank=hit.rank,
                    chunk_id=hit.chunk_id,
                )
            )

    for match in target_matches:
        target = match.target
        if target.match_level == "article" or match.best_exact_rank is not None:
            continue
        for hit in hits:
            if matches_article(target, hit) and not matches_expected_target(target, hit):
                flags.append(
                    EvidenceRiskFlag(
                        code="child_provision_mismatch_under_expected_article",
                        message=(
                            "retrieved child chunk is under an expected Article, "
                            "but does not match the required clause/point depth"
                        ),
                        rank=hit.rank,
                        chunk_id=hit.chunk_id,
                        target=target,
                        details={
                            "expected_target": _target_details(target),
                            "expected_match_level": target.match_level,
                            "best_article_rank": match.article_match_rank,
                            "best_exact_rank": match.best_exact_rank,
                            "top_result": _hit_details(top),
                            "matched_lower_result": _hit_details(hit),
                        },
                    )
                )
                break

        if match.article_match_rank is None:
            for hit in hits:
                if _parent_text_mentions_expected_article(target, hit):
                    flags.append(
                        EvidenceRiskFlag(
                            code="parent_text_mentions_expected_article_but_chunk_metadata_mismatch",
                            message=(
                                "retrieved parent_text mentions the expected Article, "
                                "but chunk metadata is not under that expected Article"
                            ),
                            rank=hit.rank,
                            chunk_id=hit.chunk_id,
                            target=target,
                            details={
                                "expected_target": _target_details(target),
                                "expected_match_level": target.match_level,
                                "best_article_rank": match.article_match_rank,
                                "best_exact_rank": match.best_exact_rank,
                                "top_result": _hit_details(top),
                                "matched_lower_result": _hit_details(hit),
                            },
                        )
                    )
                    break
    return flags


def aggregate_metrics(
    per_query: Sequence[PerQueryEvaluationResult],
    *,
    cutoffs: Sequence[int],
) -> AggregateRetrievalMetrics:
    """Aggregate per-query dense retrieval metrics."""
    query_count = len(per_query)
    evaluated = [item for item in per_query if item.retrieval_error is None]
    evaluated_count = len(evaluated)
    denominator = query_count or 1
    metrics: dict[str, Any] = {
        "query_count": query_count,
        "evaluated_query_count": evaluated_count,
        "error_count": sum(1 for item in per_query if item.retrieval_error is not None),
        "empty_result_count": sum(1 for item in per_query if item.empty_result),
        "issue_count": sum(item.issue_count for item in per_query),
        "risk_flag_count": sum(len(item.risk_flags) for item in per_query),
        "metadata_completeness_rate": _mean(item.metadata_completeness_rate for item in evaluated),
        "mean_latency_ms": _mean(item.elapsed_ms for item in per_query),
        "mrr_at_20": _mean(item.reciprocal_rank_at_20 for item in per_query),
    }
    for cutoff in cutoffs:
        key = str(cutoff)
        metrics[f"recall_at_{cutoff}"] = (
            sum(1 for item in per_query if item.exact_hit_at.get(key, False)) / denominator
        )
        metrics[f"article_hit_at_{cutoff}"] = (
            sum(1 for item in per_query if item.article_hit_at.get(key, False)) / denominator
        )
        metrics[f"exact_hit_at_{cutoff}"] = metrics[f"recall_at_{cutoff}"]
    return AggregateRetrievalMetrics(**metrics)


def summarize_hit(hit: RetrievedChunk, *, preview_chars: int = 240) -> RetrievedHitSummary:
    """Build a compact JSON-friendly hit summary."""
    return RetrievedHitSummary(
        rank=hit.rank,
        score=hit.score,
        chunk_id=hit.chunk_id,
        law_id=hit.law_id,
        law_name=hit.law_name,
        article_number=hit.article_number,
        clause_number=hit.clause_number,
        point_label=hit.point_label,
        citation=hit.citation,
        source_url=hit.source_url,
        text_preview=preview(hit.text, preview_chars),
        parent_text_preview=preview(hit.parent_text, preview_chars),
        issue_count=len(hit.issues),
    )


def preview(text: str | None, max_chars: int) -> str | None:
    """Return a whitespace-normalized preview."""
    if text is None:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def run_async_evaluation(coro: Any) -> DenseRetrievalEvaluationReport:
    """Run an evaluation coroutine from synchronous call sites."""
    return asyncio.run(coro)


def _parent_text_mentions_expected_article(
    target: ExpectedTarget,
    hit: RetrievedChunk,
) -> bool:
    if matches_article(target, hit):
        return False
    if not hit.parent_text or not _same(target.law_id, hit.law_id):
        return False
    pattern = rf"\bĐiều\s+{re.escape(target.article_number)}\b"
    return re.search(pattern, hit.parent_text, flags=re.IGNORECASE) is not None


def _target_details(target: ExpectedTarget) -> dict[str, str | None]:
    return {
        "law_id": target.law_id,
        "article_number": target.article_number,
        "clause_number": target.clause_number,
        "point_label": target.point_label,
        "match_level": target.match_level,
    }


def _hit_details(hit: RetrievedChunk | None) -> dict[str, Any] | None:
    if hit is None:
        return None
    return {
        "rank": hit.rank,
        "chunk_id": hit.chunk_id,
        "law_id": hit.law_id,
        "article_number": hit.article_number,
        "clause_number": hit.clause_number,
        "point_label": hit.point_label,
        "citation": hit.citation,
        "source_url": hit.source_url,
    }


def _hit_at_rank(hits: Sequence[RetrievedChunk], rank: int | None) -> RetrievedChunk | None:
    if rank is None:
        return None
    return next((hit for hit in hits if hit.rank == rank), None)


def _first_rank(items: Sequence[RetrievedChunk] | Any) -> int | None:
    for item in items:
        return item.rank
    return None


def _min_rank(ranks: Any) -> int | None:
    values = [rank for rank in ranks if rank is not None]
    return min(values) if values else None


def _rank_within(rank: int | None, cutoff: int) -> bool:
    return rank is not None and rank <= cutoff


def _mean(values: Any) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _same(expected: str | None, actual: str | None) -> bool:
    if expected is None or actual is None:
        return False
    return expected.strip().casefold() == actual.strip().casefold()
