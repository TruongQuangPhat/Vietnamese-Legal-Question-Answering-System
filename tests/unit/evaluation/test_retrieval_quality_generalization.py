"""Metric-contract tests for retrieval-quality generalization benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.evaluation.benchmark.direct_evidence as canonical_direct_evidence
import src.evaluation.retrieval_quality_generalization as compatibility_direct_evidence
from scripts.evaluation.run_retrieval_quality_generalization_benchmark import main as runner_main
from src.evaluation.benchmark.direct_evidence import (
    DIRECT_EVIDENCE_METRIC_CONTRACT_VERSION,
    DIRECT_EVIDENCE_SCHEMA_VERSION,
    BenchmarkRuntimeConfig,
    CaseEvaluation,
    DirectEvidenceReportValidationError,
    EvidenceTarget,
    _selection_input_retrieval,
    build_report_metadata,
    compare_reports,
    compute_aggregate_metrics,
    metric_definitions,
    validate_report_compatibility,
    validate_report_schema,
)
from src.retrieval.models import RetrievalResult, RetrievedChunk


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
    assert set(compatibility_direct_evidence.__all__) >= {
        "BenchmarkRuntimeConfig",
        "EvidenceTarget",
        "compare_reports",
        "validate_report_compatibility",
        "validate_report_schema",
    }
    assert (
        compatibility_direct_evidence.validate_report_schema
        is canonical_direct_evidence.validate_report_schema
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


def test_runtime_aligned_selection_view_scores_only_top_10_candidates() -> None:
    """Production-aligned selection input is structurally bounded to top 10."""
    retrieval = RetrievalResult(
        query="q",
        collection_name="fixture",
        vector_name="sparse_bm25",
        top_k=50,
        elapsed_ms=0.0,
        query_vector_dimension=0,
        results=[
            RetrievedChunk(
                rank=index,
                score=1.0 / index,
                chunk_id=f"c{index}",
                law_id="BLLD_VBHN",
                article_number=str(index),
                text="x" * 80,
            )
            for index in range(1, 51)
        ],
    )

    bounded = _selection_input_retrieval(retrieval, selection_input_top_k=10)

    assert len(retrieval.results) == 50
    assert len(bounded.results) == 10
    assert bounded.metadata["diagnostic_result_count"] == 50
    assert bounded.metadata["selection_input_top_k"] == 10
    assert bounded.results[-1].rank == 10


def test_case_evaluation_preserves_prompt_and_forbidden_target_semantics() -> None:
    """Canonical case rows distinguish primary, supporting, required, and forbidden roles."""
    primary = EvidenceTarget("BLLD_VBHN", "113", "1", role="primary")
    supporting = EvidenceTarget("BLLD_VBHN", "111", "1", role="supporting")
    forbidden = EvidenceTarget(
        "BLLD_VBHN",
        "114",
        role="forbidden",
        forbidden_primary=True,
        forbidden_citation=True,
    )
    evaluation = CaseEvaluation(
        case_id="leave",
        query="q",
        split="holdout",
        intent="multi_article_leave",
        expected_targets=(primary, supporting),
        primary_target=primary,
        candidate_ranks={primary.as_key(): 1, supporting.as_key(): 2},
        selection_input_ranks={primary.as_key(): 1, supporting.as_key(): 2},
        selection_input_top_k=10,
        selected_evidence=[
            {"law_id": "BLLD_VBHN", "article_number": "113", "clause_number": "1"},
            {"law_id": "BLLD_VBHN", "article_number": "111", "clause_number": "1"},
        ],
        prompt_evidence=[
            {"law_id": "BLLD_VBHN", "article_number": "113", "clause_number": "1"},
            {"law_id": "BLLD_VBHN", "article_number": "111", "clause_number": "1"},
        ],
        forbidden_selected=[
            {"law_id": "BLLD_VBHN", "article_number": "114", "target": forbidden.to_dict()}
        ],
        forbidden_cited=[],
        pass_status=False,
        pass_reason="forbidden primary target found",
        primary_evidence_accuracy=True,
        citation_alignment_accuracy=True,
        multi_article_coverage_accuracy=True,
        cross_reference_only_primary_error=False,
        wrong_actor_primary_error=False,
        wrong_domain_primary_error=False,
    )

    row = evaluation.to_dict(recall_depths=(5, 10))

    assert row["actual_primary_evidence"]["article_number"] == "113"
    assert row["actual_primary_prompt_evidence"]["article_number"] == "113"
    assert row["expected_targets"][0]["role"] == "primary"
    assert row["expected_targets"][1]["role"] == "supporting"
    assert row["forbidden_evidence_found"]["selected"][0]["article_number"] == "114"
    assert row["multi_article_coverage_accuracy"] is True


def test_compare_reports_counts_rank_loss_even_when_case_still_passes() -> None:
    """Regression reporting includes still-passing expected-target rank losses."""
    before = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after = _report([_case(case_id="annual", ranks=[3], passed=True)])

    comparison = compare_reports(before, after)

    assert comparison["regression_count"] == 1
    assert comparison["regressions"][0]["type"] == "candidate_rank_loss"
    assert comparison["regressions"][0]["case_still_passing"] is True
    assert comparison["largest_negative_rank_change"] == -2


def test_compare_reports_counts_semantic_regression() -> None:
    """Regression reporting still captures semantic primary/citation losses."""
    before = _report([_case(case_id="annual", ranks=[1], primary=True, passed=True)])
    after = _report([_case(case_id="annual", ranks=[1], primary=False, passed=False)])

    comparison = compare_reports(before, after)

    assert comparison["regression_count"] == 2
    assert comparison["semantic_regression_count"] == 2
    assert {item["type"] for item in comparison["regressions"]} == {
        "primary_evidence_accuracy",
        "pass",
    }


def test_compare_reports_rejects_incompatible_metadata() -> None:
    """Before/after comparisons require identical machine-readable contracts."""
    base = _report([_case(case_id="annual", ranks=[1], passed=True)])

    mutations = {
        "schema_version": "9.9",
        "metric_contract_version": "other_contract",
        "corpus_identity": "other_corpus",
        "case_set_identity": "other_case_set",
        "matching_granularity": "law_only",
        "evaluation_stage": "other_stage",
        "selection_input_top_k": 50,
        "selected_evidence_budget": 10,
        "benchmark_mode": "deep_diagnostic",
    }

    for field, value in mutations.items():
        candidate = _report([_case(case_id="annual", ranks=[1], passed=True)])
        if field in {"selection_input_top_k", "selected_evidence_budget"}:
            candidate["cutoff_configuration"][field] = value
            candidate["configuration"][field] = value
        else:
            candidate[field] = value
        try:
            validate_report_compatibility(base, candidate)
        except ValueError as exc:
            expected = (
                f"cutoff_configuration.{field}"
                if field in {"selection_input_top_k", "selected_evidence_budget"}
                else field
            )
            assert expected in str(exc)
        else:  # pragma: no cover - pytest assertion path
            raise AssertionError(f"comparison did not reject {field}")


@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        ("schema_version", "missing required field 'schema_version'"),
        ("metric_contract_version", "missing required field 'metric_contract_version'"),
        ("corpus_identity", "missing required field 'corpus_identity'"),
        ("case_set_identity", "missing required field 'case_set_identity'"),
        ("cases", "missing required field 'cases'"),
        ("cutoff_configuration", "missing required field 'cutoff_configuration'"),
    ],
)
def test_validate_report_schema_rejects_missing_required_fields(
    field_name: str,
    message: str,
) -> None:
    """Direct-evidence reports must be complete before comparison."""
    report = _report([_case(case_id="annual", ranks=[1], passed=True)])
    report.pop(field_name)

    with pytest.raises(DirectEvidenceReportValidationError, match=message):
        validate_report_schema(report)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("schema_version", None, "field 'schema_version' must not be null"),
        ("metric_contract_version", "", "field 'metric_contract_version' must not be empty"),
        ("cases", None, "field 'cases' must not be null"),
        ("cases", {"case_id": "x"}, "field 'cases' must be a list"),
        ("aggregate_metrics", [], "field 'aggregate_metrics' must be an object"),
        ("warnings", {}, "field 'warnings' must be a list"),
        ("limitations", {}, "field 'limitations' must be a list"),
    ],
)
def test_validate_report_schema_rejects_null_or_malformed_fields(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    """Null and malformed envelope fields are never compatible by default."""
    report = _report([_case(case_id="annual", ranks=[1], passed=True)])
    report[field_name] = bad_value

    with pytest.raises(DirectEvidenceReportValidationError, match=message):
        validate_report_schema(report)


def test_validate_report_schema_rejects_invalid_cases() -> None:
    """Malformed case rows fail deterministically instead of later KeyError."""
    report = _report([_case(case_id="annual", ranks=[1], passed=True)])
    report["cases"][0].pop("primary_evidence_accuracy")

    with pytest.raises(
        DirectEvidenceReportValidationError,
        match="missing required field 'primary_evidence_accuracy'",
    ):
        validate_report_schema(report)


def test_validate_report_schema_rejects_missing_cutoff_metadata() -> None:
    """Comparison-critical cutoff fields are required in the canonical envelope."""
    report = _report([_case(case_id="annual", ranks=[1], passed=True)])
    report["cutoff_configuration"].pop("selection_input_top_k")

    with pytest.raises(
        DirectEvidenceReportValidationError,
        match="cutoff_configuration.selection_input_top_k",
    ):
        validate_report_schema(report)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("production_aligned", False),
        ("schema_version", "other_schema"),
        ("metric_contract_version", "other_contract"),
        ("matching_granularity", "law_only"),
        ("evaluation_stage", "other_stage"),
    ],
)
def test_validate_report_compatibility_rejects_contract_mismatches(
    field_name: str,
    value: object,
) -> None:
    """Comparison rejects semantic contract mismatches even for valid reports."""
    before = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after[field_name] = value
    if field_name == "production_aligned":
        after["cutoff_configuration"]["production_aligned"] = value
        after["configuration"]["production_aligned"] = value

    with pytest.raises(DirectEvidenceReportValidationError, match=field_name):
        validate_report_compatibility(before, after)


def test_validate_report_compatibility_rejects_runtime_and_deep_diagnostic_reports() -> None:
    """Runtime-aligned and deep-diagnostic reports are not production comparisons."""
    before = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after = _report(
        [_case(case_id="annual", ranks=[1], passed=True)],
        runtime_config=BenchmarkRuntimeConfig.for_mode("deep_diagnostic"),
    )

    with pytest.raises(DirectEvidenceReportValidationError, match="selection_input_top_k"):
        validate_report_compatibility(before, after)


def test_validate_report_compatibility_rejects_selected_evidence_budget_mismatch() -> None:
    """Selected evidence budget differences are comparison-critical."""
    before = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after["cutoff_configuration"]["selected_evidence_budget"] = 4
    after["configuration"]["selected_evidence_budget"] = 4

    with pytest.raises(DirectEvidenceReportValidationError, match="selected_evidence_budget"):
        validate_report_compatibility(before, after)


@pytest.mark.parametrize(
    "legacy_report",
    [
        {},
        {"query_count": 128, "recall_at_10": 0.95, "mrr_at_10": 0.68},
    ],
)
def test_legacy_frozen_metrics_are_rejected_as_direct_evidence_reports(
    legacy_report: dict[str, object],
) -> None:
    """Frozen benchmark metrics are valid only under their original manifests."""
    valid = _report([_case(case_id="annual", ranks=[1], passed=True)])

    with pytest.raises(DirectEvidenceReportValidationError, match="before report is invalid"):
        compare_reports(legacy_report, valid)
    with pytest.raises(DirectEvidenceReportValidationError, match="after report is invalid"):
        compare_reports(valid, legacy_report)


def test_compare_reports_rejects_expected_target_set_mismatch() -> None:
    """Target-set mismatches fail as compatibility errors, not incidental KeyError."""
    before = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after = _report([_case(case_id="annual", ranks=[1], passed=True)])
    after["cases"][0]["expected_targets"][0]["target_key"] = "different-target"

    with pytest.raises(DirectEvidenceReportValidationError, match="expected target set differs"):
        compare_reports(before, after)


def test_comparison_cli_failure_does_not_create_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Failed compare invocations exit cleanly and create no output file."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "comparison.json"
    before.write_text(json.dumps({"query_count": 128}), encoding="utf-8")
    after.write_text(
        json.dumps(_report([_case(case_id="annual", ranks=[1], passed=True)])), encoding="utf-8"
    )

    exit_code = runner_main(
        [
            "compare",
            "--before",
            str(before),
            "--after",
            str(after),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert not output.exists()
    assert "Comparison failed:" in capsys.readouterr().err


def test_comparison_cli_failure_does_not_overwrite_existing_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Failed compare invocations leave existing output untouched."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "comparison.json"
    before.write_text("{", encoding="utf-8")
    after.write_text(
        json.dumps(_report([_case(case_id="annual", ranks=[1], passed=True)])), encoding="utf-8"
    )
    output.write_text("sentinel", encoding="utf-8")

    exit_code = runner_main(
        [
            "compare",
            "--before",
            str(before),
            "--after",
            str(after),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert output.read_text(encoding="utf-8") == "sentinel"
    assert "invalid JSON" in capsys.readouterr().err


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


def _report(
    cases: list[dict[str, object]],
    *,
    runtime_config: BenchmarkRuntimeConfig | None = None,
) -> dict[str, object]:
    config = runtime_config or BenchmarkRuntimeConfig.for_mode("runtime_aligned")
    metadata = build_report_metadata(
        git_revision="test",
        corpus_identity="data/processed/legal_chunks.jsonl",
        pipeline_family="direct_evidence",
        evaluation_stage="sparse_selection_diagnostic",
        retrieval_mode="sparse_selection",
        runtime_config=config,
    ).to_dict()
    report = {
        "benchmark_id": "test",
        "repo_root": "/tmp/test",
        "production_aligned": config.production_aligned,
        "aggregate_metrics": compute_aggregate_metrics(cases),
        "cases": cases,
    }
    report.update(metadata)
    assert report["schema_version"] == DIRECT_EVIDENCE_SCHEMA_VERSION
    assert report["metric_contract_version"] == DIRECT_EVIDENCE_METRIC_CONTRACT_VERSION
    return report
