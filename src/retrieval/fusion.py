"""Rank-fusion utilities for retrieval candidates."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from src.retrieval.models import RetrievedChunk

RetrievalSource = Literal["dense", "sparse"]


@dataclass(frozen=True)
class FusionSourceRank:
    """Rank and score contributed by one retrieval source."""

    rank: int
    score: float


@dataclass(frozen=True)
class FusedCandidate:
    """One deterministic Reciprocal Rank Fusion candidate."""

    chunk: RetrievedChunk
    fused_score: float
    dense: FusionSourceRank | None
    sparse: FusionSourceRank | None


@dataclass(frozen=True)
class QuotaSelectionConfig:
    """Final top-k quota settings for coverage-aware hybrid selection."""

    fused_best: int
    sparse_quota: int
    dense_quota: int


@dataclass(frozen=True)
class DiversitySelectionConfig:
    """Metadata diversity settings for final top-k hybrid selection."""

    penalty: float
    prefer_distinct_clause_point: bool = False


def reciprocal_rank_fusion(
    *,
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
    final_top_k: int,
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
    quota_config: QuotaSelectionConfig | None = None,
    diversity_config: DiversitySelectionConfig | None = None,
) -> list[RetrievedChunk]:
    """Fuse dense and sparse retrieval results with deterministic RRF.

    Args:
        dense_results: Ranked dense candidates with one-based ranks.
        sparse_results: Ranked sparse candidates with one-based ranks.
        final_top_k: Number of fused candidates returned.
        rrf_k: RRF rank-offset constant.
        dense_weight: Weight applied to dense RRF contributions.
        sparse_weight: Weight applied to sparse RRF contributions.
        quota_config: Optional quota-based final selector.
        diversity_config: Optional metadata-diversity final selector.

    Returns:
        Fused candidates as `RetrievedChunk` values. The `score` field stores
        the fused score and `metadata["fusion"]` records per-source ranks and
        scores for debugging.

    Raises:
        ValueError: If `final_top_k` or `rrf_k` is not positive.
    """
    if final_top_k <= 0:
        raise ValueError("final_top_k must be positive")
    _validate_fusion_settings(
        final_top_k=final_top_k,
        rrf_k=rrf_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )

    fused = _collect_candidates(
        dense_results=dense_results,
        sparse_results=sparse_results,
        rrf_k=rrf_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )
    ordered = _sort_by_fused_score(fused.values())
    if quota_config is not None and diversity_config is not None:
        raise ValueError("quota_config and diversity_config cannot both be set")
    if quota_config is not None:
        ordered = select_with_source_quotas(
            candidates=ordered,
            dense_results=dense_results,
            sparse_results=sparse_results,
            final_top_k=final_top_k,
            quota_config=quota_config,
        )
    elif diversity_config is not None:
        ordered = select_with_metadata_diversity(
            candidates=ordered,
            final_top_k=final_top_k,
            diversity_config=diversity_config,
        )
    return [
        _with_fusion_metadata(candidate, rank=rank)
        for rank, candidate in enumerate(ordered[:final_top_k], start=1)
    ]


def select_with_source_quotas(
    *,
    candidates: list[FusedCandidate],
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
    final_top_k: int,
    quota_config: QuotaSelectionConfig,
) -> list[FusedCandidate]:
    """Select final candidates with fused, sparse, and dense source quotas.

    Selection uses only retrieval ranks/scores and candidate metadata. It never
    reads qrels, relevance labels, or evidence group annotations.
    """
    if final_top_k <= 0:
        raise ValueError("final_top_k must be positive")
    if min(quota_config.fused_best, quota_config.sparse_quota, quota_config.dense_quota) < 0:
        raise ValueError("quota values must be non-negative")

    by_id = {
        candidate.chunk.chunk_id: candidate for candidate in candidates if candidate.chunk.chunk_id
    }
    selected: list[FusedCandidate] = []
    seen: set[str] = set()

    _append_from_candidates(selected, seen, candidates, quota_config.fused_best)
    sparse_order = [
        by_id[result.chunk_id]
        for result in sorted(sparse_results, key=lambda chunk: (chunk.rank, chunk.chunk_id or ""))
        if result.chunk_id in by_id
    ]
    _append_from_candidates(selected, seen, sparse_order, quota_config.sparse_quota)
    dense_order = [
        by_id[result.chunk_id]
        for result in sorted(dense_results, key=lambda chunk: (chunk.rank, chunk.chunk_id or ""))
        if result.chunk_id in by_id
    ]
    _append_from_candidates(selected, seen, dense_order, quota_config.dense_quota)
    _append_from_candidates(selected, seen, candidates, final_top_k - len(selected))
    return selected[:final_top_k]


def select_with_metadata_diversity(
    *,
    candidates: list[FusedCandidate],
    final_top_k: int,
    diversity_config: DiversitySelectionConfig,
) -> list[FusedCandidate]:
    """Select final candidates with a deterministic metadata diversity penalty.

    The penalty is based on repeated ``law_id`` + ``article_number`` metadata
    among already selected candidates. It does not use benchmark qrels,
    relevance labels, or evidence group annotations.
    """
    if final_top_k <= 0:
        raise ValueError("final_top_k must be positive")
    if diversity_config.penalty < 0:
        raise ValueError("diversity penalty must be non-negative")

    selected: list[FusedCandidate] = []
    remaining = list(candidates)
    while remaining and len(selected) < final_top_k:
        best = min(
            remaining,
            key=lambda candidate: _diversity_sort_key(candidate, selected, diversity_config),
        )
        selected.append(best)
        remaining.remove(best)
    return selected


def _collect_candidates(
    *,
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
    rrf_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> dict[str, FusedCandidate]:
    by_chunk_id: dict[str, FusedCandidate] = {}
    for source, results in (("dense", dense_results), ("sparse", sparse_results)):
        for candidate in results:
            if candidate.chunk_id is None:
                continue
            source_rank = FusionSourceRank(rank=candidate.rank, score=candidate.score)
            existing = by_chunk_id.get(candidate.chunk_id)
            if existing is None:
                by_chunk_id[candidate.chunk_id] = FusedCandidate(
                    chunk=candidate,
                    fused_score=_weighted_rrf_score(
                        candidate.rank, rrf_k, source, dense_weight, sparse_weight
                    ),
                    dense=source_rank if source == "dense" else None,
                    sparse=source_rank if source == "sparse" else None,
                )
                continue
            by_chunk_id[candidate.chunk_id] = _merge_candidate(
                existing=existing,
                source=source,
                source_rank=source_rank,
                fallback_chunk=candidate,
                rrf_k=rrf_k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
            )
    return by_chunk_id


def _merge_candidate(
    *,
    existing: FusedCandidate,
    source: RetrievalSource,
    source_rank: FusionSourceRank,
    fallback_chunk: RetrievedChunk,
    rrf_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> FusedCandidate:
    dense = existing.dense
    sparse = existing.sparse
    chunk = existing.chunk
    score_delta = 0.0
    if source == "dense" and (dense is None or source_rank.rank < dense.rank):
        if dense is not None:
            score_delta -= _weighted_rrf_score(
                dense.rank, rrf_k, source, dense_weight, sparse_weight
            )
        dense = source_rank
        score_delta += _weighted_rrf_score(
            source_rank.rank, rrf_k, source, dense_weight, sparse_weight
        )
        chunk = fallback_chunk
    elif source == "sparse" and (sparse is None or source_rank.rank < sparse.rank):
        if sparse is not None:
            score_delta -= _weighted_rrf_score(
                sparse.rank, rrf_k, source, dense_weight, sparse_weight
            )
        sparse = source_rank
        score_delta += _weighted_rrf_score(
            source_rank.rank, rrf_k, source, dense_weight, sparse_weight
        )
        if dense is None:
            chunk = fallback_chunk
    return FusedCandidate(
        chunk=chunk,
        fused_score=existing.fused_score + score_delta,
        dense=dense,
        sparse=sparse,
    )


def _rrf_score(rank: int, rrf_k: int) -> float:
    return 1.0 / (rrf_k + rank)


def _weighted_rrf_score(
    rank: int,
    rrf_k: int,
    source: RetrievalSource,
    dense_weight: float,
    sparse_weight: float,
) -> float:
    weight = dense_weight if source == "dense" else sparse_weight
    return weight * _rrf_score(rank, rrf_k)


def _validate_fusion_settings(
    *,
    final_top_k: int,
    rrf_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> None:
    if final_top_k <= 0:
        raise ValueError("final_top_k must be positive")
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    if dense_weight < 0:
        raise ValueError("dense_weight must be non-negative")
    if sparse_weight < 0:
        raise ValueError("sparse_weight must be non-negative")
    if dense_weight == 0 and sparse_weight == 0:
        raise ValueError("at least one fusion weight must be positive")


def _sort_by_fused_score(candidates: Iterable[FusedCandidate]) -> list[FusedCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.fused_score,
            _rank_or_infinity(candidate.dense),
            _rank_or_infinity(candidate.sparse),
            candidate.chunk.chunk_id or "",
        ),
    )


def _rank_or_infinity(source_rank: FusionSourceRank | None) -> float:
    return float(source_rank.rank) if source_rank is not None else math.inf


def _append_from_candidates(
    selected: list[FusedCandidate],
    seen: set[str],
    candidates: list[FusedCandidate],
    limit: int,
) -> None:
    if limit <= 0:
        return
    added = 0
    for candidate in candidates:
        chunk_id = candidate.chunk.chunk_id
        if chunk_id is None or chunk_id in seen:
            continue
        selected.append(candidate)
        seen.add(chunk_id)
        added += 1
        if added >= limit:
            return


def _diversity_sort_key(
    candidate: FusedCandidate,
    selected: list[FusedCandidate],
    config: DiversitySelectionConfig,
) -> tuple[float, float, float, str]:
    duplicate_count = sum(
        1
        for selected_candidate in selected
        if _article_key(selected_candidate) == _article_key(candidate)
    )
    diversity_penalty = config.penalty * duplicate_count
    if config.prefer_distinct_clause_point and duplicate_count:
        candidate_detail = _detail_key(candidate)
        if candidate_detail and all(
            _detail_key(selected_candidate) != candidate_detail for selected_candidate in selected
        ):
            diversity_penalty = max(0.0, diversity_penalty - (config.penalty / 2.0))
    adjusted_score = candidate.fused_score - diversity_penalty
    return (
        -adjusted_score,
        _rank_or_infinity(candidate.dense),
        _rank_or_infinity(candidate.sparse),
        candidate.chunk.chunk_id or "",
    )


def _article_key(candidate: FusedCandidate) -> tuple[str | None, str | None]:
    return (candidate.chunk.law_id, candidate.chunk.article_number)


def _detail_key(candidate: FusedCandidate) -> tuple[str | None, str | None, str | None, str | None]:
    return (
        candidate.chunk.law_id,
        candidate.chunk.article_number,
        candidate.chunk.clause_number,
        candidate.chunk.point_label,
    )


def _with_fusion_metadata(candidate: FusedCandidate, *, rank: int) -> RetrievedChunk:
    fusion_metadata = {
        "retrieval_method": "hybrid_dense_sparse_rrf",
        "fused_score": candidate.fused_score,
        "dense_rank": candidate.dense.rank if candidate.dense is not None else None,
        "dense_score": candidate.dense.score if candidate.dense is not None else None,
        "sparse_rank": candidate.sparse.rank if candidate.sparse is not None else None,
        "sparse_score": candidate.sparse.score if candidate.sparse is not None else None,
    }
    metadata = dict(candidate.chunk.metadata)
    metadata["fusion"] = fusion_metadata
    return candidate.chunk.model_copy(
        update={
            "rank": rank,
            "score": candidate.fused_score,
            "metadata": metadata,
        },
        deep=True,
    )
