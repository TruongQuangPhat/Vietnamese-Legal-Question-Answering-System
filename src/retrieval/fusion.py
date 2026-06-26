"""Rank-fusion utilities for retrieval candidates."""

from __future__ import annotations

import math
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


def reciprocal_rank_fusion(
    *,
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
    final_top_k: int,
    rrf_k: int = 60,
) -> list[RetrievedChunk]:
    """Fuse dense and sparse retrieval results with deterministic RRF.

    Args:
        dense_results: Ranked dense candidates with one-based ranks.
        sparse_results: Ranked sparse candidates with one-based ranks.
        final_top_k: Number of fused candidates returned.
        rrf_k: RRF rank-offset constant.

    Returns:
        Fused candidates as `RetrievedChunk` values. The `score` field stores
        the fused score and `metadata["fusion"]` records per-source ranks and
        scores for debugging.

    Raises:
        ValueError: If `final_top_k` or `rrf_k` is not positive.
    """
    if final_top_k <= 0:
        raise ValueError("final_top_k must be positive")
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")

    fused = _collect_candidates(
        dense_results=dense_results, sparse_results=sparse_results, rrf_k=rrf_k
    )
    ordered = sorted(
        fused.values(),
        key=lambda candidate: (
            -candidate.fused_score,
            _rank_or_infinity(candidate.dense),
            _rank_or_infinity(candidate.sparse),
            candidate.chunk.chunk_id or "",
        ),
    )
    return [
        _with_fusion_metadata(candidate, rank=rank)
        for rank, candidate in enumerate(ordered[:final_top_k], start=1)
    ]


def _collect_candidates(
    *,
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
    rrf_k: int,
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
                    fused_score=_rrf_score(candidate.rank, rrf_k),
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
            )
    return by_chunk_id


def _merge_candidate(
    *,
    existing: FusedCandidate,
    source: RetrievalSource,
    source_rank: FusionSourceRank,
    fallback_chunk: RetrievedChunk,
    rrf_k: int,
) -> FusedCandidate:
    dense = existing.dense
    sparse = existing.sparse
    chunk = existing.chunk
    score_delta = 0.0
    if source == "dense" and (dense is None or source_rank.rank < dense.rank):
        if dense is not None:
            score_delta -= _rrf_score(dense.rank, rrf_k)
        dense = source_rank
        score_delta += _rrf_score(source_rank.rank, rrf_k)
        chunk = fallback_chunk
    elif source == "sparse" and (sparse is None or source_rank.rank < sparse.rank):
        if sparse is not None:
            score_delta -= _rrf_score(sparse.rank, rrf_k)
        sparse = source_rank
        score_delta += _rrf_score(source_rank.rank, rrf_k)
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


def _rank_or_infinity(source_rank: FusionSourceRank | None) -> float:
    return float(source_rank.rank) if source_rank is not None else math.inf


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
