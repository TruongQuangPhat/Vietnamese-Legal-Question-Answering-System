"""Integration tests for dense-sparse fusion workflow."""

from __future__ import annotations

import pytest

from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.models import RetrievedChunk


def test_fusion_workflow_deduplicates_and_preserves_source_metadata() -> None:
    """RRF fuses fake dense/sparse results with deterministic ranking and metadata."""
    dense_results = [
        _retrieved("chunk-a", rank=1, score=0.92, article_number="1"),
        _retrieved("chunk-b", rank=2, score=0.88, article_number="2"),
        _retrieved("chunk-c", rank=3, score=0.70, article_number="3"),
    ]
    sparse_results = [
        _retrieved("chunk-b", rank=1, score=4.0, article_number="2"),
        _retrieved("chunk-d", rank=2, score=3.5, article_number="4"),
        _retrieved("chunk-a", rank=3, score=2.0, article_number="1"),
    ]

    fused = reciprocal_rank_fusion(
        dense_results=dense_results,
        sparse_results=sparse_results,
        final_top_k=3,
        rrf_k=60,
    )

    assert [chunk.chunk_id for chunk in fused] == ["chunk-b", "chunk-a", "chunk-d"]
    assert len({chunk.chunk_id for chunk in fused}) == 3
    assert len(fused) == 3
    assert fused[0].rank == 1
    assert fused[0].score == pytest.approx((1 / 62) + (1 / 61))
    assert fused[0].metadata["fusion"]["dense_rank"] == 2
    assert fused[0].metadata["fusion"]["sparse_rank"] == 1
    assert fused[1].metadata["fusion"]["dense_rank"] == 1
    assert fused[1].metadata["fusion"]["sparse_rank"] == 3
    assert fused[2].metadata["fusion"]["dense_rank"] is None
    assert fused[2].metadata["fusion"]["sparse_rank"] == 2
    assert fused[0].citation == "Luật Kiểm thử, Khoản 1, Điều 2"
    assert fused[0].source_url == "https://thuvienphapluat.vn/LAW_TEST"


def _retrieved(
    chunk_id: str,
    *,
    rank: int,
    score: float,
    article_number: str,
) -> RetrievedChunk:
    """Build one in-memory retrieval candidate with legal metadata."""
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        law_id="LAW_TEST",
        law_name="Luật Kiểm thử",
        level="clause",
        chunk_kind="clause_level",
        article_number=article_number,
        clause_number="1",
        citation=f"Luật Kiểm thử, Khoản 1, Điều {article_number}",
        hierarchy_path=f"Luật Kiểm thử / Điều {article_number} / Khoản 1",
        text=f"Khoản 1 Điều {article_number} quy định nội dung kiểm thử.",
        parent_text=f"Điều {article_number}. Quy định kiểm thử.",
        source_url="https://thuvienphapluat.vn/LAW_TEST",
        source_domain="thuvienphapluat.vn",
        metadata={"source": "fixture"},
    )
