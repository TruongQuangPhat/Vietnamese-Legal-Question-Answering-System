"""Metric-contract tests for retrieval-quality generalization benchmark."""

from __future__ import annotations

from src.evaluation.retrieval_quality_generalization import (
    compare_reports,
    compute_aggregate_metrics,
    metric_definitions,
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
    assert "regression_counting" in definitions
    assert "law_id + article_number" in definitions["exact_matching_granularity"]


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
