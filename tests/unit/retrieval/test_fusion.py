"""Unit tests for Reciprocal Rank Fusion."""

from __future__ import annotations

import pytest

from src.retrieval.fusion import (
    DiversitySelectionConfig,
    QuotaSelectionConfig,
    reciprocal_rank_fusion,
)
from src.retrieval.models import RetrievedChunk


def _hit(
    chunk_id: str,
    *,
    rank: int,
    score: float = 1.0,
    law_id: str = "LAW_A",
    article_number: str = "1",
    clause_number: str | None = None,
    point_label: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        law_id=law_id,
        article_number=article_number,
        clause_number=clause_number,
        point_label=point_label,
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


def test_weighted_rrf_applies_source_weights() -> None:
    fused = reciprocal_rank_fusion(
        dense_results=[_hit("dense_top", rank=1)],
        sparse_results=[_hit("sparse_top", rank=1)],
        final_top_k=2,
        rrf_k=60,
        dense_weight=1.0,
        sparse_weight=2.0,
    )

    assert [candidate.chunk_id for candidate in fused] == ["sparse_top", "dense_top"]
    assert fused[0].score == pytest.approx(2 / 61)
    assert fused[1].score == pytest.approx(1 / 61)


def test_quota_selection_adds_sparse_and_dense_slots() -> None:
    fused = reciprocal_rank_fusion(
        dense_results=[_hit("dense_a", rank=1), _hit("dense_b", rank=2)],
        sparse_results=[_hit("sparse_a", rank=1), _hit("sparse_b", rank=2)],
        final_top_k=3,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=1, sparse_quota=1, dense_quota=1),
    )

    assert len({candidate.chunk_id for candidate in fused}) == 3
    assert fused[0].metadata["fusion"]["retrieval_method"] == "hybrid_dense_sparse_rrf"
    assert any(candidate.metadata["fusion"]["sparse_rank"] is not None for candidate in fused)
    assert any(candidate.metadata["fusion"]["dense_rank"] is not None for candidate in fused)


def test_source_quota_prefers_distinct_legal_targets_before_sparse_duplicates() -> None:
    """Sparse quota keeps a lower-ranked distinct provision before article duplicates."""
    fused = reciprocal_rank_fusion(
        dense_results=[
            _hit(f"dense_{index}", rank=index, article_number=f"D{index}") for index in range(1, 6)
        ],
        sparse_results=[
            _hit("civil_clause_1", rank=1, law_id="LAW_CIVIL", article_number="569"),
            _hit("civil_clause_2", rank=2, law_id="LAW_CIVIL", article_number="569"),
            _hit("labor_clause_36", rank=3, law_id="LAW_LABOR", article_number="36"),
            _hit("labor_clause_37", rank=4, law_id="LAW_LABOR", article_number="37"),
            _hit("labor_clause_35", rank=5, law_id="LAW_LABOR", article_number="35"),
        ],
        final_top_k=4,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=0, sparse_quota=4, dense_quota=0),
    )

    sparse_ids = [
        candidate.chunk_id
        for candidate in fused
        if candidate.metadata["fusion"]["sparse_rank"] is not None
    ]
    assert "labor_clause_35" in sparse_ids
    assert "civil_clause_2" not in sparse_ids


def test_source_quota_fills_duplicate_legal_targets_when_distinct_targets_are_exhausted() -> None:
    """Legal-target diversity is a preference, not a hard exclusion."""
    fused = reciprocal_rank_fusion(
        dense_results=[],
        sparse_results=[
            _hit("article_1_clause_1", rank=1, article_number="1"),
            _hit("article_1_clause_2", rank=2, article_number="1"),
        ],
        final_top_k=2,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=0, sparse_quota=2, dense_quota=0),
    )

    assert [candidate.chunk_id for candidate in fused] == [
        "article_1_clause_1",
        "article_1_clause_2",
    ]


def test_source_quota_preserves_sibling_clause_and_point_targets() -> None:
    """Source diversity must not collapse distinct legal locators in one article."""
    fused = reciprocal_rank_fusion(
        dense_results=[],
        sparse_results=[
            _hit(
                "article_10_clause_1",
                rank=1,
                law_id="LAW_CIVIL",
                article_number="10",
                clause_number="1",
            ),
            _hit(
                "article_10_clause_2_point_a",
                rank=2,
                law_id="LAW_CIVIL",
                article_number="10",
                clause_number="2",
                point_label="a",
            ),
            _hit(
                "article_10_clause_2_point_b",
                rank=3,
                law_id="LAW_CIVIL",
                article_number="10",
                clause_number="2",
                point_label="b",
            ),
        ],
        final_top_k=3,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=0, sparse_quota=3, dense_quota=0),
    )

    assert [candidate.chunk_id for candidate in fused] == [
        "article_10_clause_1",
        "article_10_clause_2_point_a",
        "article_10_clause_2_point_b",
    ]


def test_source_quota_prefers_dominant_source_law_within_source_top_k() -> None:
    """Source-law expansion is limited to candidates inside the source top-k."""
    fused = reciprocal_rank_fusion(
        dense_results=[],
        sparse_results=[
            _hit("civil_contract", rank=1, law_id="LAW_CIVIL", article_number="1"),
            _hit("labor_rule_a", rank=2, law_id="LAW_LABOR", article_number="10"),
            _hit("labor_rule_b", rank=3, law_id="LAW_LABOR", article_number="11"),
            _hit("labor_rule_c", rank=4, law_id="LAW_LABOR", article_number="12"),
            _hit("labor_rule_d", rank=5, law_id="LAW_LABOR", article_number="13"),
            _hit("labor_direct", rank=6, law_id="LAW_LABOR", article_number="14"),
        ],
        final_top_k=4,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=0, sparse_quota=4, dense_quota=0),
    )

    assert [candidate.chunk_id for candidate in fused] == [
        "labor_rule_a",
        "labor_rule_b",
        "labor_rule_c",
        "civil_contract",
    ]
    assert "labor_rule_d" not in {candidate.chunk_id for candidate in fused}


def test_source_quota_uses_source_rank_limit_when_fused_top_k_is_dense_saturated() -> None:
    """Dense saturation does not let source quotas pull beyond source top-k."""
    fused = reciprocal_rank_fusion(
        dense_results=[
            _hit(f"dense_{index}", rank=index, law_id="LAW_DENSE", article_number=str(index))
            for index in range(1, 5)
        ],
        sparse_results=[
            _hit("civil_contract", rank=1, law_id="LAW_CIVIL", article_number="1"),
            _hit("labor_rule_a", rank=2, law_id="LAW_LABOR", article_number="10"),
            _hit("labor_rule_b", rank=3, law_id="LAW_LABOR", article_number="11"),
            _hit("labor_rule_c", rank=4, law_id="LAW_LABOR", article_number="12"),
            _hit("labor_rule_d", rank=5, law_id="LAW_LABOR", article_number="13"),
        ],
        final_top_k=4,
        rrf_k=60,
        dense_weight=10.0,
        sparse_weight=1.0,
        quota_config=QuotaSelectionConfig(fused_best=0, sparse_quota=4, dense_quota=0),
    )

    assert [candidate.chunk_id for candidate in fused] == [
        "labor_rule_a",
        "labor_rule_b",
        "labor_rule_c",
        "civil_contract",
    ]
    assert "labor_rule_d" not in {candidate.chunk_id for candidate in fused}


def test_source_quota_keeps_base_top_k_target_before_dominant_law_expansion() -> None:
    """Dominant-law expansion must not evict an existing base top-k locator."""
    shared = [
        _hit(
            f"shared_{index}",
            rank=index,
            law_id="LAW_DOMINANT",
            article_number=str(index),
        )
        for index in range(1, 10)
    ]
    target = _hit("base_rank_10_target", rank=10, law_id="LAW_OTHER", article_number="10")
    beyond = _hit("dominant_rank_11", rank=11, law_id="LAW_DOMINANT", article_number="11")

    fused = reciprocal_rank_fusion(
        dense_results=[*shared, target, beyond],
        sparse_results=[*shared, target, beyond],
        final_top_k=10,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=5, sparse_quota=4, dense_quota=1),
    )

    assert [candidate.chunk_id for candidate in fused][-1] == "base_rank_10_target"
    assert "dominant_rank_11" not in {candidate.chunk_id for candidate in fused}


def test_source_quota_is_stable_when_input_order_changes() -> None:
    """Quota diversity depends on source ranks, not caller list order."""
    sparse_results = [
        _hit("civil_clause_1", rank=1, law_id="LAW_CIVIL", article_number="10"),
        _hit("civil_clause_2", rank=2, law_id="LAW_CIVIL", article_number="10"),
        _hit("admin_rule", rank=3, law_id="LAW_ADMIN", article_number="20"),
        _hit("tax_rule", rank=4, law_id="LAW_TAX", article_number="30"),
        _hit("business_rule", rank=5, law_id="LAW_BUSINESS", article_number="40"),
    ]
    dense_results = [
        _hit("dense_civil", rank=1, law_id="LAW_CIVIL", article_number="11"),
        _hit("dense_admin", rank=2, law_id="LAW_ADMIN", article_number="21"),
    ]

    forward = reciprocal_rank_fusion(
        dense_results=dense_results,
        sparse_results=sparse_results,
        final_top_k=5,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=0, sparse_quota=4, dense_quota=1),
    )
    reversed_input = reciprocal_rank_fusion(
        dense_results=list(reversed(dense_results)),
        sparse_results=list(reversed(sparse_results)),
        final_top_k=5,
        rrf_k=60,
        quota_config=QuotaSelectionConfig(fused_best=0, sparse_quota=4, dense_quota=1),
    )

    assert [candidate.chunk_id for candidate in reversed_input] == [
        candidate.chunk_id for candidate in forward
    ]


def test_diversity_penalty_promotes_different_article() -> None:
    fused = reciprocal_rank_fusion(
        dense_results=[
            _hit("article_1_a", rank=1),
            _hit("article_1_b", rank=2),
            _hit("article_2", rank=3, article_number="2"),
        ],
        sparse_results=[],
        final_top_k=3,
        rrf_k=60,
        diversity_config=DiversitySelectionConfig(penalty=0.01),
    )

    assert [candidate.chunk_id for candidate in fused][:2] == ["article_1_a", "article_2"]


def test_fusion_does_not_rank_by_gold_relevance_metadata() -> None:
    low_gold_top_rank = _hit("top_by_rank", rank=1).model_copy(
        update={"metadata": {"relevance": "irrelevant", "evidence_group_ids": []}}
    )
    high_gold_lower_rank = _hit("lower_by_rank", rank=2).model_copy(
        update={"metadata": {"relevance": "required_direct", "evidence_group_ids": ["gold_group"]}}
    )

    fused = reciprocal_rank_fusion(
        dense_results=[low_gold_top_rank, high_gold_lower_rank],
        sparse_results=[],
        final_top_k=2,
        rrf_k=60,
    )

    assert [candidate.chunk_id for candidate in fused] == ["top_by_rank", "lower_by_rank"]


def test_empty_candidate_handling_returns_empty_list() -> None:
    assert (
        reciprocal_rank_fusion(
            dense_results=[],
            sparse_results=[],
            final_top_k=10,
        )
        == []
    )
