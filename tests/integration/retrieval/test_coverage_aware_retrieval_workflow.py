"""Integration tests for coverage-aware retrieval workflow."""

from __future__ import annotations

from src.retrieval.fusion import QuotaSelectionConfig, reciprocal_rank_fusion
from src.retrieval.models import RetrievedChunk


def test_coverage_aware_retrieval_workflow_respects_source_quotas() -> None:
    """Coverage-aware quota selection combines fused, sparse, and dense candidates."""
    dense_results = [
        _retrieved("both-top", rank=1, score=0.95, article_number="1"),
        _retrieved("dense-only", rank=2, score=0.88, article_number="2"),
        _retrieved("shared-lower", rank=3, score=0.80, article_number="3"),
        _retrieved("dense-extra", rank=4, score=0.70, article_number="4"),
    ]
    sparse_results = [
        _retrieved("both-top", rank=1, score=5.0, article_number="1"),
        _retrieved("sparse-only", rank=2, score=4.5, article_number="5"),
        _retrieved("shared-lower", rank=3, score=3.0, article_number="3"),
        _retrieved("sparse-extra", rank=4, score=2.0, article_number="6"),
    ]

    results = reciprocal_rank_fusion(
        dense_results=dense_results[:5],
        sparse_results=sparse_results[:5],
        final_top_k=4,
        rrf_k=60,
        dense_weight=1.0,
        sparse_weight=1.5,
        quota_config=QuotaSelectionConfig(fused_best=2, sparse_quota=1, dense_quota=1),
    )

    assert [chunk.chunk_id for chunk in results] == [
        "both-top",
        "shared-lower",
        "sparse-only",
        "dense-only",
    ]
    assert len(results) == 4
    assert len({chunk.chunk_id for chunk in results}) == 4
    by_id = {chunk.chunk_id: chunk for chunk in results}
    assert results[0].metadata["fusion"]["dense_rank"] == 1
    assert results[0].metadata["fusion"]["sparse_rank"] == 1
    assert by_id["sparse-only"].metadata["fusion"]["sparse_rank"] == 2
    assert by_id["dense-only"].metadata["fusion"]["dense_rank"] == 2
    assert all(chunk.law_id == "LAW_TEST" for chunk in results)
    assert all(chunk.source_url for chunk in results)
    assert all(chunk.citation for chunk in results)
    assert all(chunk.text for chunk in results)


def _retrieved(
    chunk_id: str,
    *,
    rank: int,
    score: float,
    article_number: str,
) -> RetrievedChunk:
    """Build one citable fake retrieval candidate."""
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
