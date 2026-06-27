"""Unit tests for coverage-aware fusion ablation helpers."""

from __future__ import annotations

import pytest

from src.evaluation.benchmark.fusion_ablation import (
    FusionAblationError,
    _select_best_config,
    assert_manifest_has_no_secret_keys,
    config_from_payload,
    default_ablation_configs,
)


def _variant(
    config_id: str,
    *,
    group: float,
    required: float = 0.0,
    recall: float = 0.0,
    mrr: float = 0.0,
    ndcg: float = 0.0,
    latency: float = 1.0,
    simplicity_rank: int = 0,
) -> dict[str, object]:
    return {
        "config": {"config_id": config_id, "simplicity_rank": simplicity_rank},
        "development_metrics": {
            "evidence_group_coverage_at_10": group,
            "required_direct_coverage_at_10": required,
            "recall_at_10": recall,
            "mrr_at_10": mrr,
            "ndcg_at_10": ndcg,
            "mean_retrieval_latency_ms": latency,
        },
    }


def test_default_ablation_configs_cover_requested_families() -> None:
    configs = default_ablation_configs()

    assert {config.config_id for config in configs} == {
        "equal_weight_rrf",
        "sparse_weight_1_25",
        "sparse_weight_1_5",
        "sparse_weight_2",
        "dense_weight_1_25",
        "sparse_weight_1_5_pool_50_100",
        "sparse_weight_1_5_pool_100_100",
        "sparse_weight_2_pool_50_100",
        "sparse_weight_2_pool_100_100",
        "quota_fused6_sparse3_dense1",
        "quota_fused5_sparse3_dense2",
        "quota_fused4_sparse4_dense2",
        "selected_coverage_aware_quota",
        "diversity_penalty_0_001",
        "diversity_penalty_0_002",
        "diversity_penalty_0_001_distinct_detail",
    }
    assert all(config.final_top_k == 10 for config in configs)
    assert all(config.rrf_k == 60 for config in configs)


def test_selection_uses_development_metrics_and_tie_breakers() -> None:
    selected = _select_best_config(
        [
            _variant("lower_group", group=0.7, required=1.0, recall=1.0),
            _variant("higher_group", group=0.8, required=0.1, recall=0.1),
        ]
    )

    assert selected["config"]["config_id"] == "higher_group"

    selected_tie = _select_best_config(
        [
            _variant("simple", group=0.8, required=0.7, recall=0.6, latency=2.0, simplicity_rank=1),
            _variant("faster", group=0.8, required=0.7, recall=0.6, latency=1.0, simplicity_rank=2),
        ]
    )

    assert selected_tie["config"]["config_id"] == "faster"


def test_selection_ignores_held_out_metrics() -> None:
    selected = _select_best_config(
        [
            {
                **_variant("better_development", group=0.8),
                "held_out_metrics": {"evidence_group_coverage_at_10": 0.1},
            },
            {
                **_variant("worse_development", group=0.7),
                "held_out_metrics": {"evidence_group_coverage_at_10": 1.0},
            },
        ]
    )

    assert selected["config"]["config_id"] == "better_development"


def test_config_payload_round_trip_for_quota_and_diversity() -> None:
    configs = {config.config_id: config for config in default_ablation_configs()}

    quota_variant = config_from_payload(configs["quota_fused4_sparse4_dense2"].model_dump())
    diversity_variant = config_from_payload(
        configs["diversity_penalty_0_001_distinct_detail"].model_dump()
    )

    assert quota_variant.quota_config() is not None
    assert quota_variant.quota_config().sparse_quota == 4
    assert diversity_variant.diversity_config() is not None
    assert diversity_variant.diversity_config().prefer_distinct_clause_point is True


def test_manifest_guard_rejects_secret_shaped_keys() -> None:
    assert_manifest_has_no_secret_keys(
        {
            "report_type": "test",
            "nested": [{"command": ["python", "script.py"]}],
        }
    )

    with pytest.raises(FusionAblationError):
        assert_manifest_has_no_secret_keys({"nested": {"api_key": "redacted"}})
