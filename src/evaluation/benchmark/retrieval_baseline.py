"""Retrieval-only benchmark metrics for frozen legal QA baselines."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    RelevanceLevel,
)
from src.evaluation.benchmark.loader import LoadedBenchmarkDataset
from src.evaluation.benchmark.schemas import BenchmarkQuery, EvidenceGroup, EvidenceJudgment
from src.retrieval.models import RetrievedChunk

DEFAULT_RETRIEVAL_CUTOFFS = (1, 3, 5, 10)
DIRECT_RELEVANCE = {RelevanceLevel.REQUIRED_DIRECT, RelevanceLevel.ALTERNATIVE_DIRECT}
RELEVANCE_GAIN = {
    RelevanceLevel.REQUIRED_DIRECT: 3.0,
    RelevanceLevel.ALTERNATIVE_DIRECT: 2.0,
    RelevanceLevel.SUPPORTING: 1.0,
    RelevanceLevel.NEAR_MISS: 0.0,
    RelevanceLevel.IRRELEVANT: 0.0,
}


class BenchmarkRetrievalMetricError(RuntimeError):
    """Raised when benchmark retrieval metrics cannot be computed safely."""


def evaluate_case_retrieval(
    *,
    query: BenchmarkQuery,
    split: BenchmarkSplit,
    retrieved: list[RetrievedChunk],
    judgments: list[EvidenceJudgment],
    groups: list[EvidenceGroup],
    cutoffs: tuple[int, ...] = DEFAULT_RETRIEVAL_CUTOFFS,
    retrieval_error: str | None = None,
    elapsed_ms: float | None = None,
) -> dict[str, Any]:
    """Evaluate one query's dense retrieval result against benchmark qrels.

    Args:
        query: Frozen benchmark query metadata.
        split: Canonical split assignment from the split manifest.
        retrieved: Ranked dense retrieval chunks.
        judgments: Chunk-level qrels for the query.
        groups: Evidence groups for the query.
        cutoffs: Retrieval cutoffs to evaluate.
        retrieval_error: Optional retrieval failure text.
        elapsed_ms: Optional retriever latency in milliseconds.

    Returns:
        JSON-compatible per-case retrieval metrics and retrieved hit summaries.
    """
    if not cutoffs:
        raise BenchmarkRetrievalMetricError("cutoffs must not be empty")
    if any(cutoff <= 0 for cutoff in cutoffs):
        raise BenchmarkRetrievalMetricError("cutoffs must be positive")

    relevance_by_chunk = {judgment.chunk_id: judgment.relevance for judgment in judgments}
    group_ids_by_chunk = {
        judgment.chunk_id: list(judgment.evidence_group_ids) for judgment in judgments
    }
    required_direct_ids = {
        judgment.chunk_id
        for judgment in judgments
        if judgment.relevance == RelevanceLevel.REQUIRED_DIRECT
    }
    acceptable_direct_ids = {
        judgment.chunk_id for judgment in judgments if judgment.relevance in DIRECT_RELEVANCE
    }
    required_groups = [
        group for group in groups if group.requirement == EvidenceGroupRequirement.REQUIRED
    ]
    group_direct_ids = {
        group.evidence_group_id: set(group.acceptable_chunk_ids) & acceptable_direct_ids
        for group in required_groups
    }
    retrieved_ids = [chunk.chunk_id for chunk in retrieved if chunk.chunk_id is not None]

    cutoff_metrics: dict[str, dict[str, Any]] = {}
    for cutoff in cutoffs:
        top_ids = set(retrieved_ids[:cutoff])
        direct_hits = top_ids & acceptable_direct_ids
        required_hits = top_ids & required_direct_ids
        covered_groups = {
            group_id
            for group_id, direct_ids in group_direct_ids.items()
            if direct_ids and top_ids.intersection(direct_ids)
        }
        cutoff_metrics[str(cutoff)] = {
            "direct_hit": bool(direct_hits),
            "direct_hit_count": len(direct_hits),
            "required_direct_hit_count": len(required_hits),
            "required_direct_total": len(required_direct_ids),
            "required_direct_coverage": _fraction(len(required_hits), len(required_direct_ids)),
            "evidence_group_hit_count": len(covered_groups),
            "evidence_group_total": len(required_groups),
            "evidence_group_coverage": _fraction(len(covered_groups), len(required_groups)),
            "fallback_near_miss_hit": any(
                relevance_by_chunk.get(chunk_id) == RelevanceLevel.NEAR_MISS for chunk_id in top_ids
            ),
            "fallback_supporting_hit": any(
                relevance_by_chunk.get(chunk_id) == RelevanceLevel.SUPPORTING
                for chunk_id in top_ids
            ),
            "fallback_direct_hit": bool(direct_hits),
        }

    first_direct_rank = _first_rank(retrieved_ids, acceptable_direct_ids, max(cutoffs))
    case_metrics = {
        "query_id": query.id,
        "split": split.value,
        "expected_decision": query.expected_decision.value,
        "primary_domain": query.primary_domain.value,
        "question_types": [question_type.value for question_type in query.question_types],
        "complete_evidence_required": query.complete_evidence_required,
        "blocking": query.blocking,
        "retrieval_error": retrieval_error,
        "elapsed_ms": elapsed_ms,
        "retrieved_count": len(retrieved),
        "first_direct_rank": first_direct_rank,
        "reciprocal_rank_at_10": (1.0 / first_direct_rank)
        if first_direct_rank is not None and first_direct_rank <= 10
        else 0.0,
        "ndcg_at_10": _ndcg_at_k(retrieved_ids, relevance_by_chunk, 10),
        "cutoffs": cutoff_metrics,
        "retrieved": [
            _summarize_chunk(chunk, relevance_by_chunk, group_ids_by_chunk) for chunk in retrieved
        ],
    }
    return case_metrics


def aggregate_case_metrics(
    case_results: list[dict[str, Any]],
    *,
    cutoffs: tuple[int, ...] = DEFAULT_RETRIEVAL_CUTOFFS,
) -> dict[str, Any]:
    """Aggregate per-case benchmark retrieval metrics.

    Args:
        case_results: Per-query result dictionaries from
            `evaluate_case_retrieval`.
        cutoffs: Retrieval cutoffs to aggregate.

    Returns:
        JSON-compatible aggregate metrics.
    """
    evaluated = [case for case in case_results if case.get("retrieval_error") is None]
    answer_allowed = [
        case
        for case in evaluated
        if case["expected_decision"] == ExpectedDecision.ANSWER_ALLOWED.value
    ]
    fallback = [
        case
        for case in evaluated
        if case["expected_decision"] == ExpectedDecision.FALLBACK_REQUIRED.value
    ]

    metrics: dict[str, Any] = {
        "query_count": len(case_results),
        "evaluated_query_count": len(evaluated),
        "retrieval_error_count": len(case_results) - len(evaluated),
        "answer_allowed_count": len(answer_allowed),
        "fallback_required_count": len(fallback),
        "mean_retrieval_latency_ms": _mean(
            case["elapsed_ms"] for case in evaluated if case.get("elapsed_ms") is not None
        ),
        "mrr_at_10": _mean(case["reciprocal_rank_at_10"] for case in answer_allowed),
        "ndcg_at_10": _mean(case["ndcg_at_10"] for case in evaluated),
        "fallback_diagnostics": {
            "fallback_case_count": len(fallback),
        },
    }

    for cutoff in cutoffs:
        key = str(cutoff)
        metrics[f"recall_at_{cutoff}"] = _mean(
            1.0 if case["cutoffs"][key]["direct_hit"] else 0.0 for case in answer_allowed
        )
        required_hits = sum(
            case["cutoffs"][key]["required_direct_hit_count"] for case in answer_allowed
        )
        required_total = sum(
            case["cutoffs"][key]["required_direct_total"] for case in answer_allowed
        )
        metrics[f"required_direct_coverage_at_{cutoff}"] = _fraction(
            required_hits,
            required_total,
        )
        group_hits = sum(
            case["cutoffs"][key]["evidence_group_hit_count"] for case in answer_allowed
        )
        group_total = sum(case["cutoffs"][key]["evidence_group_total"] for case in answer_allowed)
        metrics[f"evidence_group_coverage_at_{cutoff}"] = _fraction(group_hits, group_total)
        metrics["fallback_diagnostics"][f"near_miss_retrieved_at_{cutoff}"] = _count_and_rate(
            fallback,
            lambda case, key=key: bool(case["cutoffs"][key]["fallback_near_miss_hit"]),
        )
        metrics["fallback_diagnostics"][f"supporting_retrieved_at_{cutoff}"] = _count_and_rate(
            fallback,
            lambda case, key=key: bool(case["cutoffs"][key]["fallback_supporting_hit"]),
        )
        metrics["fallback_diagnostics"][f"direct_evidence_retrieved_at_{cutoff}"] = _count_and_rate(
            fallback,
            lambda case, key=key: bool(case["cutoffs"][key]["fallback_direct_hit"]),
        )
    return metrics


def build_breakdowns(
    case_results: list[dict[str, Any]],
    *,
    cutoffs: tuple[int, ...] = DEFAULT_RETRIEVAL_CUTOFFS,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Build metric breakdowns by benchmark metadata dimensions."""
    return {
        "split": _breakdown(case_results, "split", cutoffs=cutoffs),
        "primary_domain": _breakdown(case_results, "primary_domain", cutoffs=cutoffs),
        "expected_decision": _breakdown(case_results, "expected_decision", cutoffs=cutoffs),
        "question_types": _breakdown_multivalue(
            case_results,
            "question_types",
            cutoffs=cutoffs,
        ),
        "complete_evidence_required": _breakdown(
            case_results,
            "complete_evidence_required",
            cutoffs=cutoffs,
        ),
        "blocking": _breakdown(case_results, "blocking", cutoffs=cutoffs),
    }


def build_benchmark_case_inputs(
    dataset: LoadedBenchmarkDataset,
) -> tuple[dict[str, list[EvidenceJudgment]], dict[str, list[EvidenceGroup]]]:
    """Index qrels and evidence groups by query ID."""
    judgments_by_query: dict[str, list[EvidenceJudgment]] = defaultdict(list)
    groups_by_query: dict[str, list[EvidenceGroup]] = defaultdict(list)
    for judgment in dataset.evidence_judgments:
        judgments_by_query[judgment.query_id].append(judgment)
    for group in dataset.evidence_groups:
        groups_by_query[group.query_id].append(group)
    return dict(judgments_by_query), dict(groups_by_query)


def _breakdown(
    case_results: list[dict[str, Any]],
    field_name: str,
    *,
    cutoffs: tuple[int, ...],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in case_results:
        buckets[str(case[field_name])].append(case)
    return {
        bucket: aggregate_case_metrics(cases, cutoffs=cutoffs)
        for bucket, cases in sorted(buckets.items())
    }


def _breakdown_multivalue(
    case_results: list[dict[str, Any]],
    field_name: str,
    *,
    cutoffs: tuple[int, ...],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in case_results:
        for value in case[field_name]:
            buckets[str(value)].append(case)
    return {
        bucket: aggregate_case_metrics(cases, cutoffs=cutoffs)
        for bucket, cases in sorted(buckets.items())
    }


def _first_rank(
    retrieved_ids: list[str],
    acceptable_direct_ids: set[str],
    max_rank: int,
) -> int | None:
    for index, chunk_id in enumerate(retrieved_ids[:max_rank], start=1):
        if chunk_id in acceptable_direct_ids:
            return index
    return None


def _ndcg_at_k(
    retrieved_ids: list[str],
    relevance_by_chunk: dict[str, RelevanceLevel],
    cutoff: int,
) -> float:
    gains = [
        RELEVANCE_GAIN.get(relevance_by_chunk.get(chunk_id), 0.0) for chunk_id in retrieved_ids
    ]
    dcg = _discounted_gain(gains[:cutoff])
    ideal = sorted(
        (RELEVANCE_GAIN[relevance] for relevance in relevance_by_chunk.values()),
        reverse=True,
    )
    idcg = _discounted_gain(ideal[:cutoff])
    return dcg / idcg if idcg > 0 else 0.0


def _discounted_gain(gains: Iterable[float]) -> float:
    return sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))


def _summarize_chunk(
    chunk: RetrievedChunk,
    relevance_by_chunk: dict[str, RelevanceLevel],
    group_ids_by_chunk: dict[str, list[str]],
) -> dict[str, Any]:
    relevance = relevance_by_chunk.get(chunk.chunk_id or "")
    return {
        "rank": chunk.rank,
        "chunk_id": chunk.chunk_id,
        "score": chunk.score,
        "law_id": chunk.law_id,
        "article_number": chunk.article_number,
        "clause_number": chunk.clause_number,
        "point_label": chunk.point_label,
        "relevance": relevance.value if relevance is not None else None,
        "evidence_group_ids": group_ids_by_chunk.get(chunk.chunk_id or "", []),
    }


def _fraction(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _mean(values: Iterable[float | int]) -> float:
    collected = [float(value) for value in values]
    return sum(collected) / len(collected) if collected else 0.0


def _count_and_rate(
    cases: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, float | int]:
    count = sum(1 for case in cases if predicate(case))
    return {"count": count, "rate": _fraction(count, len(cases))}
