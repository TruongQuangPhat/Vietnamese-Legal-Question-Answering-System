"""Unit tests for Reciprocal Rank Fusion."""

from __future__ import annotations

import pytest

from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.models import RetrievedChunk


def _hit(chunk_id: str, *, rank: int, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        law_id="LAW_A",
        article_number="1",
        text="Synthetic legal text.",
    )


def test_rrf_fuses_duplicate_chunk_ids_and_preserves_source_ranks() -> None:
    fused = reciprocal_rank_fusion(
        dense_results=[_hit("chunk_a", rank=1, score=0.9)],
        sparse_results=[_hit("chunk_a", rank=2, score=3.0)],
        final_top_k=10,
        rrf_k=60,
    )

    assert len(fused) == 1
    expected_score = 1 / 61 + 1 / 62
    assert fused[0].score == pytest.approx(expected_score)
    assert fused[0].metadata["fusion"]["fused_score"] == pytest.approx(expected_score)
    assert fused[0].metadata["fusion"]["dense_rank"] == 1
    assert fused[0].metadata["fusion"]["dense_score"] == pytest.approx(0.9)
    assert fused[0].metadata["fusion"]["sparse_rank"] == 2
    assert fused[0].metadata["fusion"]["sparse_score"] == pytest.approx(3.0)


def test_rrf_includes_dense_only_and_sparse_only_candidates() -> None:
    fused = reciprocal_rank_fusion(
        dense_results=[_hit("dense_only", rank=1)],
        sparse_results=[_hit("sparse_only", rank=1)],
        final_top_k=10,
        rrf_k=60,
    )

    assert {candidate.chunk_id for candidate in fused} == {"dense_only", "sparse_only"}
    by_id = {candidate.chunk_id: candidate for candidate in fused}
    assert by_id["dense_only"].metadata["fusion"]["dense_rank"] == 1
    assert by_id["dense_only"].metadata["fusion"]["sparse_rank"] is None
    assert by_id["sparse_only"].metadata["fusion"]["dense_rank"] is None
    assert by_id["sparse_only"].metadata["fusion"]["sparse_rank"] == 1


def test_rrf_tie_breaks_by_dense_rank_then_sparse_rank_then_chunk_id() -> None:
    fused = reciprocal_rank_fusion(
        dense_results=[
            _hit("chunk_b", rank=1),
            _hit("chunk_a", rank=2),
        ],
        sparse_results=[
            _hit("chunk_a", rank=1),
            _hit("chunk_b", rank=2),
        ],
        final_top_k=10,
        rrf_k=60,
    )

    assert [candidate.chunk_id for candidate in fused] == ["chunk_b", "chunk_a"]


def test_rrf_tie_breaks_by_chunk_id_when_source_ranks_match() -> None:
    fused = reciprocal_rank_fusion(
        dense_results=[],
        sparse_results=[
            _hit("chunk_b", rank=1),
            _hit("chunk_a", rank=1),
        ],
        final_top_k=10,
        rrf_k=60,
    )

    assert [candidate.chunk_id for candidate in fused] == ["chunk_a", "chunk_b"]


def test_rrf_rejects_invalid_settings() -> None:
    with pytest.raises(ValueError, match="final_top_k"):
        reciprocal_rank_fusion(
            dense_results=[],
            sparse_results=[],
            final_top_k=0,
        )

    with pytest.raises(ValueError, match="rrf_k"):
        reciprocal_rank_fusion(
            dense_results=[],
            sparse_results=[],
            final_top_k=10,
            rrf_k=0,
        )
