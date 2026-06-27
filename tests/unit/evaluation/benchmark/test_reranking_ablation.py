"""Unit tests for reranking ablation configuration and selection."""

from __future__ import annotations

import pytest

from src.evaluation.benchmark.reranking_ablation import (
    RerankingAblationError,
    assert_manifest_has_no_secret_keys,
    default_reranking_configs,
    select_reranking_config,
)


def _metrics(
    *,
    group_10: float = 0.75,
    recall_10: float = 0.95,
    ndcg_10: float = 0.62,
    mrr_10: float = 0.69,
    group_5: float = 0.50,
    recall_5: float = 0.80,
    latency: float = 10.0,
) -> dict[str, float]:
    return {
        "evidence_group_coverage_at_10": group_10,
        "recall_at_10": recall_10,
        "ndcg_at_10": ndcg_10,
        "mrr_at_10": mrr_10,
        "evidence_group_coverage_at_5": group_5,
        "recall_at_5": recall_5,
        "mean_retrieval_latency_ms": latency,
    }


def _variant(
    config_id: str,
    metrics: dict[str, float],
    *,
    simplicity_rank: int = 1,
    held_out_ndcg: float | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "config": {
            "config_id": config_id,
            "simplicity_rank": simplicity_rank,
            "no_rerank": config_id == "baseline_no_rerank",
        },
        "development_metrics": metrics,
    }
    if held_out_ndcg is not None:
        payload["held_out_metrics"] = {"ndcg_at_10": held_out_ndcg}
    return payload


def test_default_configs_cover_requested_reranking_variants() -> None:
    configs = default_reranking_configs()

    assert [config.config_id for config in configs] == [
        "baseline_no_rerank",
        "pure_reranker_pool30",
        "mixed_reranker_70_base_30_pool30",
        "mixed_equal_pool30",
        "pure_reranker_pool50",
        "mixed_reranker_70_base_30_pool50",
        "quota_preserved_reranker_pool50",
    ]
    assert configs[0].no_rerank is True
    assert {config.candidate_pool_k for config in configs[1:]} == {30, 50}
    assert configs[-1].preserve_source_quota is True


def test_selection_rejects_configs_that_break_base_preservation_gates() -> None:
    base = _metrics(group_10=0.75, recall_10=0.95)
    variants = [
        _variant("baseline_no_rerank", base, simplicity_rank=0),
        _variant(
            "pure_reranker_pool30",
            _metrics(group_10=0.73, recall_10=0.99, ndcg_10=0.90),
        ),
        _variant(
            "mixed_reranker_70_base_30_pool30",
            _metrics(group_10=0.80, recall_10=0.93, ndcg_10=0.90),
        ),
    ]

    selection = select_reranking_config(variants, base_development_metrics=base)

    assert selection["eligible_config_ids"] == []
    assert selection["adopted"] is False
    assert selection["selected_config_id"] is None


def test_selection_uses_ndcg_then_mrr_and_adopts_rank_gain() -> None:
    base = _metrics(ndcg_10=0.62, mrr_10=0.69)
    variants = [
        _variant("baseline_no_rerank", base, simplicity_rank=0),
        _variant("pure_reranker_pool30", _metrics(ndcg_10=0.64, mrr_10=0.70)),
        _variant(
            "mixed_reranker_70_base_30_pool30",
            _metrics(ndcg_10=0.65, mrr_10=0.68),
        ),
    ]

    selection = select_reranking_config(variants, base_development_metrics=base)

    assert selection["selected_config_id"] == "mixed_reranker_70_base_30_pool30"
    assert selection["adopted"] is True


def test_selection_does_not_adopt_without_rank_quality_gain() -> None:
    base = _metrics(ndcg_10=0.65, mrr_10=0.70)
    variants = [
        _variant("baseline_no_rerank", base, simplicity_rank=0),
        _variant("pure_reranker_pool30", _metrics(ndcg_10=0.64, mrr_10=0.80)),
    ]

    selection = select_reranking_config(variants, base_development_metrics=base)

    assert selection["best_eligible_config_id"] == "pure_reranker_pool30"
    assert selection["adopted"] is False
    assert selection["decision"] == "no_adoption_no_rank_gain"


def test_held_out_metrics_are_not_used_for_selection() -> None:
    base = _metrics()
    variants = [
        _variant("baseline_no_rerank", base, simplicity_rank=0),
        _variant("pure_reranker_pool30", _metrics(ndcg_10=0.64), held_out_ndcg=0.0),
        _variant(
            "mixed_reranker_70_base_30_pool30",
            _metrics(ndcg_10=0.63),
            held_out_ndcg=1.0,
        ),
    ]

    selection = select_reranking_config(variants, base_development_metrics=base)

    assert selection["selected_config_id"] == "pure_reranker_pool30"


def test_manifest_guard_rejects_secret_shaped_keys() -> None:
    assert_manifest_has_no_secret_keys({"report_type": "test", "command": ["python", "script.py"]})

    with pytest.raises(RerankingAblationError, match="secret-shaped"):
        assert_manifest_has_no_secret_keys({"nested": {"authorization": "redacted"}})
