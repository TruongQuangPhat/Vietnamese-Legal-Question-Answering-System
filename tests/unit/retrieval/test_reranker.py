"""Unit tests for deterministic reranking utilities."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from src.retrieval.models import RetrievedChunk
from src.retrieval.reranker import (
    RerankerError,
    deduplicate_candidates,
    min_max_normalize,
    rerank_candidates,
)


class DeterministicMockReranker:
    """Small query-document scorer used without a real model."""

    model_name = "deterministic-mock"

    def score(self, query: str, candidates: Sequence[RetrievedChunk]) -> list[float]:
        """Score by text length and preserve input cardinality."""
        return [float(len(candidate.text or "")) for candidate in candidates]


def _candidate(
    chunk_id: str,
    *,
    rank: int,
    fused_score: float,
    dense_rank: int | None = None,
    sparse_rank: int | None = None,
    text: str = "legal text",
    metadata: dict[str, object] | None = None,
) -> RetrievedChunk:
    fusion = {
        "fused_score": fused_score,
        "dense_rank": dense_rank,
        "sparse_rank": sparse_rank,
    }
    return RetrievedChunk(
        rank=rank,
        score=fused_score,
        chunk_id=chunk_id,
        text=text,
        metadata={"fusion": fusion, **(metadata or {})},
    )


def test_mock_reranker_interface_is_deterministic() -> None:
    reranker = DeterministicMockReranker()
    candidates = [
        _candidate("a", rank=1, fused_score=0.2, text="a"),
        _candidate("b", rank=2, fused_score=0.1, text="bbbb"),
    ]

    assert reranker.score("query", candidates) == [1.0, 4.0]
    assert reranker.score("query", candidates) == [1.0, 4.0]


def test_empty_candidate_pool_is_safe() -> None:
    assert DeterministicMockReranker().score("query", []) == []
    assert (
        rerank_candidates(
            candidates=[],
            reranker_scores=[],
            final_top_k=10,
            reranker_weight=1.0,
            g3_weight=0.0,
            model_name="mock",
        )
        == []
    )


def test_candidate_deduplication_preserves_first_rank() -> None:
    candidates = [
        _candidate("same", rank=1, fused_score=0.3),
        _candidate("same", rank=2, fused_score=0.2),
        _candidate("other", rank=3, fused_score=0.1),
    ]

    deduplicated = deduplicate_candidates(candidates)

    assert [candidate.chunk_id for candidate in deduplicated] == ["same", "other"]
    assert deduplicated[0].rank == 1


def test_min_max_normalization_handles_equal_and_missing_scores() -> None:
    assert min_max_normalize([1.0, 2.0, 3.0]) == pytest.approx([0.0, 0.5, 1.0])
    assert min_max_normalize([2.0, 2.0, None]) == [1.0, 1.0, 0.0]
    assert min_max_normalize([None, None]) == [0.0, 0.0]


def test_mixed_reranker_and_g3_scoring() -> None:
    candidates = [
        _candidate("g3_top", rank=1, fused_score=3.0),
        _candidate("reranker_top", rank=2, fused_score=1.0),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[0.0, 10.0],
        final_top_k=2,
        reranker_weight=0.7,
        g3_weight=0.3,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["reranker_top", "g3_top"]
    assert reranked[0].metadata["reranking"]["final_score"] == pytest.approx(0.7)
    assert reranked[1].metadata["reranking"]["final_score"] == pytest.approx(0.3)


def test_tie_breaking_uses_reranker_g3_source_ranks_and_chunk_id() -> None:
    candidates = [
        _candidate("b", rank=1, fused_score=1.0, dense_rank=2, sparse_rank=1),
        _candidate("a", rank=2, fused_score=1.0, dense_rank=1, sparse_rank=2),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[1.0, 1.0],
        final_top_k=2,
        reranker_weight=1.0,
        g3_weight=0.0,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["a", "b"]


def test_candidate_pool_can_be_larger_than_final_top_k() -> None:
    candidates = [
        _candidate(f"chunk_{index}", rank=index, fused_score=float(10 - index))
        for index in range(1, 6)
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[1.0, 2.0, 3.0, 4.0, 5.0],
        final_top_k=2,
        reranker_weight=1.0,
        g3_weight=0.0,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["chunk_5", "chunk_4"]


def test_quota_preserving_rerank_keeps_sparse_and_dense_origins() -> None:
    candidates = [
        _candidate("shared", rank=1, fused_score=5.0, dense_rank=1, sparse_rank=1),
        _candidate("dense_only", rank=2, fused_score=4.0, dense_rank=2),
        _candidate("sparse_2", rank=3, fused_score=3.0, sparse_rank=2),
        _candidate("sparse_3", rank=4, fused_score=2.0, sparse_rank=3),
        _candidate("sparse_4", rank=5, fused_score=1.0, sparse_rank=4),
        _candidate("neither", rank=6, fused_score=0.5),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[6.0, 5.0, 1.0, 2.0, 3.0, 4.0],
        final_top_k=5,
        reranker_weight=1.0,
        g3_weight=0.0,
        preserve_source_quota=True,
        sparse_quota=4,
        dense_quota=1,
        model_name="mock",
    )

    sparse_count = sum(
        candidate.metadata["fusion"]["sparse_rank"] is not None for candidate in reranked
    )
    dense_count = sum(
        candidate.metadata["fusion"]["dense_rank"] is not None for candidate in reranked
    )
    assert sparse_count >= 4
    assert dense_count >= 1


def test_gold_metadata_does_not_change_ranking() -> None:
    candidates = [
        _candidate(
            "first",
            rank=1,
            fused_score=2.0,
            metadata={"relevance": "irrelevant", "evidence_group_ids": []},
        ),
        _candidate(
            "second",
            rank=2,
            fused_score=1.0,
            metadata={"relevance": "required_direct", "evidence_group_ids": ["gold"]},
        ),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[2.0, 1.0],
        final_top_k=2,
        reranker_weight=1.0,
        g3_weight=0.0,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["first", "second"]


def test_score_count_mismatch_is_rejected() -> None:
    with pytest.raises(RerankerError, match="score count"):
        rerank_candidates(
            candidates=[_candidate("a", rank=1, fused_score=1.0)],
            reranker_scores=[],
            final_top_k=1,
            reranker_weight=1.0,
            g3_weight=0.0,
            model_name="mock",
        )
