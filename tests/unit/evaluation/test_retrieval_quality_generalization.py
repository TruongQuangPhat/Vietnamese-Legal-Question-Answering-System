"""Metric-contract tests for retrieval-quality generalization benchmark."""

from __future__ import annotations

import src.evaluation.benchmark.direct_evidence as canonical_direct_evidence
import src.evaluation.retrieval_quality_generalization as compatibility_direct_evidence
from src.evaluation.benchmark.direct_evidence import (
    BenchmarkRuntimeConfig,
    EvidenceTarget,
    compare_reports,
    compute_aggregate_metrics,
    metric_definitions,
)


def test_direct_evidence_benchmark_uses_canonical_benchmark_package() -> None:
    """The branch-era import path remains a shim over the canonical package."""
    assert (
        compatibility_direct_evidence.RUNNER_EVALUATOR_VERSION
        == canonical_direct_evidence.RUNNER_EVALUATOR_VERSION
    )
    assert (
        compatibility_direct_evidence.BenchmarkRuntimeConfig
        is canonical_direct_evidence.BenchmarkRuntimeConfig
    )


def test_metric_definitions_document_required_contracts() -> None:
    """Metric documentation covers the semantic oracle boundaries."""
    definitions = metric_definitions()

    assert "exact_matching_granularity" in definitions
    assert "candidate_depth" in definitions
    assert "single_target_scoring" in definitions
    assert "multi_target_coverage" in definitions
    assert "primary_evidence_accuracy" in definitions
    assert "citation_alignment_accuracy" in definitions
    assert "cross_reference_only_primary_error_rate" in definitions
    assert "wrong_actor_primary_error_rate" in definitions
    assert "wrong_domain_primary_error_rate" in definitions
    assert "multi_article_coverage_accuracy" in definitions
    assert "regression_count" in definitions
    assert "regression_counting" in definitions
    assert "law_id + article_number" in definitions["exact_matching_granularity"]
    assert "micro-averaged" in definitions["recall_at_5"]
    assert "macro-averaged" in definitions["expected_article_mrr"]
    assert "article-level target" in definitions["multiple_acceptable_clauses"]
    assert "top-50 diagnostic retrieval pool" in definitions["candidate_depth"]
    assert "top-10 selection input" in definitions["evidence_selection_input_budget"]


def test_expected_target_granularity_documents_article_clause_and_point_matching() -> None:
    """Target serialization distinguishes article, clause, and point granularity."""
    article = EvidenceTarget("BLLD_VBHN", "35")
    clause = EvidenceTarget("BLLD_VBHN", "35", "1")
    point = EvidenceTarget("LHNGD_VBHN", "8", "1", "a")

    assert article.to_dict()["matching_granularity"] == "law_article"
    assert article.as_key() == "BLLD_VBHN / Điều 35"
    assert clause.to_dict()["matching_granularity"] == "law_article_clause"
    assert clause.as_key() == "BLLD_VBHN / Điều 35 / Khoản 1"
    assert point.to_dict()["matching_granularity"] == "law_article_clause_point"
    assert point.as_key() == "LHNGD_VBHN / Điều 8 / Khoản 1 / Điểm a"


def test_compute_aggregate_metrics_uses_target_level_recall_and_case_level_accuracy() -> None:
    """Recall is target-level while primary/citation accuracy is case-level."""
    cases = [
        _case(
            case_id="single",
            ranks=[1],
            primary=True,
            citation=True,
            multi=None,
            passed=True,
        ),
        _case(
            case_id="multi",
            ranks=[4, 12],
            primary=True,
            citation=False,
            multi=False,
            passed=False,
        ),
    ]

    metrics = compute_aggregate_metrics(cases, recall_depths=(5, 10))

    assert metrics["total_cases"] == 2
    assert metrics["total_expected_targets"] == 3
    assert metrics["expected_evidence_recall_at_5"] == 2 / 3
    assert metrics["expected_evidence_recall_at_10"] == 2 / 3
    assert metrics["expected_article_mrr"] == (1.0 + 0.25) / 2
    assert metrics["primary_evidence_accuracy"] == 1.0
    assert metrics["citation_alignment_accuracy"] == 0.5
    assert metrics["multi_article_coverage_accuracy"] == 0.0


def test_runtime_aligned_mode_uses_top_10_selection_input() -> None:
    """Default benchmark mode mirrors the production selector boundary."""
    config = BenchmarkRuntimeConfig.for_mode("runtime_aligned")

    assert config.diagnostic_candidate_top_k == 50
    assert config.selection_input_top_k == 10
    assert config.selected_evidence_budget == 5
    assert config.production_aligned is True


def test_deep_diagnostic_mode_is_not_production_aligned() -> None:
    """Deep diagnostics may let selection inspect the top-50 pool."""
    config = BenchmarkRuntimeConfig.for_mode("deep_diagnostic")

    assert config.diagnostic_candidate_top_k == 50
    assert config.selection_input_top_k == 50
    assert config.selected_evidence_budget == 5
    assert config.production_aligned is False


def test_target_rank_7_is_available_to_runtime_selection() -> None:
    """A target at rank 7 remains inside production-aligned selection input."""
    case = _case(case_id="rank7", ranks=[7], primary=True, citation=True, passed=True)
    target = case["expected_targets"][0]
    target["selection_input_rank"] = 7
    target["available_to_selection"] = True

    assert target["candidate_rank"] <= 10
    assert target["available_to_selection"] is True
    assert case["primary_evidence_accuracy"] is True
    assert case["citation_alignment_accuracy"] is True


def test_target_rank_11_is_diagnostic_only_and_fails_selection_metrics() -> None:
    """A top-50 target outside top 10 cannot rescue primary or citation accuracy."""
    case = _case(case_id="rank11", ranks=[11], primary=False, citation=False, passed=False)
    target = case["expected_targets"][0]
    target["selection_input_rank"] = None
    target["available_to_selection"] = False

    metrics = compute_aggregate_metrics([case], recall_depths=(5, 10, 50))

    assert metrics["expected_evidence_recall_at_10"] == 0.0
    assert metrics["expected_evidence_recall_at_50"] == 1.0
    assert metrics["primary_evidence_accuracy"] == 0.0
    assert metrics["citation_alignment_accuracy"] == 0.0
    assert target["available_to_selection"] is False


def test_multi_article_coverage_fails_when_one_target_is_outside_selection_input() -> None:
    """Multi-target coverage is evaluated after runtime input truncation."""
    case = _case(case_id="multi_boundary", ranks=[2, 11], primary=True, citation=False, multi=False)
    case["expected_targets"][0]["selection_input_rank"] = 2
    case["expected_targets"][0]["available_to_selection"] = True
    case["expected_targets"][1]["selection_input_rank"] = None
    case["expected_targets"][1]["available_to_selection"] = False

    metrics = compute_aggregate_metrics([case], recall_depths=(10, 50))

    assert metrics["expected_evidence_recall_at_50"] == 1.0
    assert metrics["multi_article_coverage_accuracy"] == 0.0


def test_deep_diagnostic_may_pass_where_runtime_aligned_fails() -> None:
    """Only runtime_aligned mode is production-gating."""
    runtime_case = _case(
        case_id="boundary", ranks=[11], primary=False, citation=False, passed=False
    )
    deep_case = _case(case_id="boundary", ranks=[11], primary=True, citation=True, passed=True)
    runtime_case["expected_targets"][0]["available_to_selection"] = False
    deep_case["expected_targets"][0]["available_to_selection"] = True

    runtime_metrics = compute_aggregate_metrics([runtime_case], recall_depths=(50,))
    deep_metrics = compute_aggregate_metrics([deep_case], recall_depths=(50,))

    assert runtime_metrics["expected_evidence_recall_at_50"] == 1.0
    assert runtime_metrics["primary_evidence_accuracy"] == 0.0
    assert deep_metrics["primary_evidence_accuracy"] == 1.0


def test_recall_at_10_can_pass_while_primary_accuracy_fails() -> None:
    """Retrieval recall and selected-primary correctness have separate denominators."""
    case = _case(case_id="misordered", ranks=[10], primary=False, citation=False, passed=False)

    metrics = compute_aggregate_metrics([case], recall_depths=(10,))

    assert metrics["expected_evidence_recall_at_10"] == 1.0
    assert metrics["primary_evidence_accuracy"] == 0.0
    assert metrics["citation_alignment_accuracy"] == 0.0


def test_compare_reports_counts_rank_loss_even_when_case_still_passes() -> None:
    """Regression reporting includes still-passing expected-target rank losses."""
    before = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after = _report([_case(case_id="annual", ranks=[3], passed=True)])

    comparison = compare_reports(before, after)

    assert comparison["regression_count"] == 1
    assert comparison["regressions"][0]["type"] == "candidate_rank_loss"
    assert comparison["regressions"][0]["case_still_passing"] is True
    assert comparison["largest_negative_rank_change"] == -2


def _case(
    *,
    case_id: str,
    ranks: list[int | None],
    primary: bool = True,
    citation: bool = True,
    multi: bool | None = None,
    passed: bool = True,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "expected_targets": [
            {
                "target_key": f"{case_id}-{index}",
                "candidate_rank": rank,
            }
            for index, rank in enumerate(ranks, start=1)
        ],
        "primary_evidence_accuracy": primary,
        "citation_alignment_accuracy": citation,
        "cross_reference_only_primary_error": False,
        "wrong_actor_primary_error": False,
        "wrong_domain_primary_error": False,
        "multi_article_coverage_accuracy": multi,
        "pass": passed,
    }


def _report(cases: list[dict[str, object]]) -> dict[str, object]:
    return {
        "benchmark_id": "test",
        "repo_root": "/tmp/test",
        "aggregate_metrics": compute_aggregate_metrics(cases),
        "cases": cases,
    }
