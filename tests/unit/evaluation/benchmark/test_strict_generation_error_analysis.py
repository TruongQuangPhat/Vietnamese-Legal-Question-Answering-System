"""Tests for offline strict generation error analysis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluation.analyze_strict_generation_errors import (
    DEFAULT_OUTPUT_DIR,
    build_arg_parser,
    main,
)
from src.evaluation.benchmark.strict_generation_error_analysis import (
    ERROR_BUCKETS,
    WORKFLOW_NAME,
    StrictGenerationErrorAnalysisPaths,
    build_strict_generation_error_analysis,
    classify_case,
    run_strict_generation_error_analysis,
)


def test_classify_case_covers_required_failure_buckets() -> None:
    cases = _cases()

    assert classify_case(cases[0]) == [
        "expected_answer_allowed_but_pipeline_fallback",
        "parent_context_only_fallback",
    ]
    assert "expected_fallback_required_but_pipeline_answered" in classify_case(cases[1])
    assert "partial_answer_missing_required_evidence" in classify_case(cases[2])
    assert (
        "selected_evidence_present_but_required_evidence_group_coverage_incomplete"
        in classify_case(cases[2])
    )
    assert "citation_guard_fallback" in classify_case(cases[3])
    assert "provider_or_generation_error" in classify_case(cases[4])
    assert "retrieval_error" in classify_case(cases[5])
    assert "selected_evidence_empty" in classify_case(cases[5])
    assert "all_selected_evidence_caution_fallback" in classify_case(cases[6])


def test_build_analysis_prioritizes_development_and_summarizes_groups() -> None:
    analysis = build_strict_generation_error_analysis(
        cases=_cases(),
        metrics={"query_count": 7},
        breakdowns={"split": {}, "primary_domain": {}},
        comparison={"systems": {"generation_baseline": {}, "strict_generation_evaluation": {}}},
    )

    assert analysis["report_type"] == WORKFLOW_NAME
    assert analysis["development_analyzed_first"] is True
    assert analysis["held_out_test_reporting_only"] is True
    assert analysis["input_summary"]["development_case_count"] == 6
    assert analysis["input_summary"]["held_out_test_case_count"] == 1
    assert analysis["development_error_buckets"]["retrieval_error"]["count"] == 1
    assert analysis["error_buckets"]["expected_answer_allowed_but_pipeline_fallback"]["count"] == 5
    assert analysis["domain_error_summary"]["labor"]["case_fail_rate"] == 0.5
    assert (
        analysis["question_type_error_summary"]["complete_list"]["missing_required_evidence_rate"]
        == 1.0
    )
    assert analysis["top_failing_domains"][0]["case_fail_rate"] == 1.0
    assert analysis["bottleneck_diagnosis"]["basis"] == "development_only"
    assert set(ERROR_BUCKETS) == set(analysis["error_buckets"])


def test_run_analysis_writes_expected_artifacts(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    analysis = run_strict_generation_error_analysis(paths)

    assert analysis["workflow_name"] == WORKFLOW_NAME
    assert {path.name for path in paths.output_dir.iterdir()} == {
        "error_buckets.json",
        "development_error_buckets.json",
        "domain_error_summary.json",
        "question_type_error_summary.json",
        "top_failure_cases.jsonl",
        "strict_generation_error_analysis.md",
    }
    buckets = json.loads((paths.output_dir / "error_buckets.json").read_text())
    markdown = (paths.output_dir / "strict_generation_error_analysis.md").read_text()
    top_cases = [
        json.loads(line)
        for line in (paths.output_dir / "top_failure_cases.jsonl").read_text().splitlines()
    ]
    assert buckets["retrieval_error"]["count"] == 1
    assert top_cases[0]["case_status"] == "fail"
    assert "Held-out test is reporting-only" in markdown
    assert "Primary bottleneck" in markdown


def test_loader_rejects_missing_inputs(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.case_results.unlink()

    with pytest.raises(Exception, match="case results not found"):
        run_strict_generation_error_analysis(paths)


def test_cli_defaults_and_help_do_not_run_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    args = build_arg_parser().parse_args([])
    assert args.output_dir == DEFAULT_OUTPUT_DIR

    monkeypatch.setattr(
        "scripts.evaluation.analyze_strict_generation_errors.run_strict_generation_error_analysis",
        lambda paths: pytest.fail("analysis must not run while rendering help"),
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def _paths(tmp_path: Path) -> StrictGenerationErrorAnalysisPaths:
    input_dir = tmp_path / "strict_generation_evaluation"
    output_dir = tmp_path / "strict_generation_error_analysis"
    input_dir.mkdir()
    _write_jsonl(input_dir / "case_results.jsonl", _cases())
    (input_dir / "metrics_all.json").write_text(json.dumps({"query_count": 7}))
    (input_dir / "breakdowns.json").write_text(json.dumps({"split": {}}))
    (input_dir / "comparison.json").write_text(
        json.dumps({"systems": {"generation_baseline": {}, "strict_generation_evaluation": {}}})
    )
    return StrictGenerationErrorAnalysisPaths(
        case_results=input_dir / "case_results.jsonl",
        metrics_all=input_dir / "metrics_all.json",
        breakdowns=input_dir / "breakdowns.json",
        comparison=input_dir / "comparison.json",
        output_dir=output_dir,
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(f"{json.dumps(record, ensure_ascii=False)}\n" for record in records),
        encoding="utf-8",
    )


def _cases() -> list[dict[str, object]]:
    return [
        _case(
            "dev-answer-fallback-parent",
            expected_decision="answer_allowed",
            pipeline_answered=False,
            pipeline_decision="fallback_required",
            primary_domain="labor",
            question_types=["single_article_lookup"],
            case_status="fail",
            selected_evidence_ids=["E1"],
            fallback_reasons=["parent_context_only"],
            group_coverage=1.0,
        ),
        _case(
            "dev-fallback-answered",
            expected_decision="fallback_required",
            pipeline_answered=True,
            pipeline_decision="answer_allowed",
            primary_domain="traffic",
            question_types=["fallback"],
            case_status="fail",
            selected_evidence_ids=["E1"],
        ),
        _case(
            "dev-partial-missing",
            expected_decision="answer_allowed",
            pipeline_answered=True,
            pipeline_decision="answer_allowed",
            primary_domain="labor",
            question_types=["complete_list"],
            case_status="partial",
            selected_evidence_ids=["E1"],
            missing_required_evidence=True,
            group_coverage=0.5,
        ),
        _case(
            "dev-citation-fallback",
            expected_decision="answer_allowed",
            pipeline_answered=False,
            pipeline_decision="fallback_required",
            primary_domain="civil",
            question_types=["paraphrase"],
            case_status="fail",
            selected_evidence_ids=["E1"],
            citation_issue_count=1,
            citation_id_valid=False,
        ),
        _case(
            "dev-generation-error",
            expected_decision="answer_allowed",
            pipeline_answered=False,
            pipeline_decision="error",
            primary_domain="civil",
            question_types=["single_article_lookup"],
            case_status="fail",
            generation_error="provider offline",
        ),
        _case(
            "dev-retrieval-error",
            expected_decision="answer_allowed",
            pipeline_answered=False,
            pipeline_decision="error",
            primary_domain="business",
            question_types=["definition"],
            case_status="fail",
            retrieval_error="qdrant offline",
        ),
        _case(
            "held-caution-fallback",
            split="held_out_test",
            expected_decision="answer_allowed",
            pipeline_answered=False,
            pipeline_decision="fallback_required",
            primary_domain="health",
            question_types=["conditions_and_exceptions"],
            case_status="fail",
            selected_evidence_ids=["E1"],
            fallback_reasons=["all_selected_evidence_caution"],
            selection_warnings=["all_selected_evidence_caution"],
        ),
    ]


def _case(
    query_id: str,
    *,
    split: str = "development",
    expected_decision: str,
    pipeline_answered: bool,
    pipeline_decision: str,
    primary_domain: str,
    question_types: list[str],
    case_status: str,
    selected_evidence_ids: list[str] | None = None,
    fallback_reasons: list[str] | None = None,
    selection_warnings: list[str] | None = None,
    missing_required_evidence: bool = False,
    group_coverage: float = 0.0,
    citation_issue_count: int = 0,
    citation_id_valid: bool = True,
    retrieval_error: str | None = None,
    generation_error: str | None = None,
) -> dict[str, object]:
    selected_ids = selected_evidence_ids or []
    return {
        "query_id": query_id,
        "split": split,
        "primary_domain": primary_domain,
        "question_types": question_types,
        "expected_decision": expected_decision,
        "pipeline_decision": pipeline_decision,
        "pipeline_answered": pipeline_answered,
        "case_status": case_status,
        "error": generation_error or retrieval_error,
        "retrieval_error": retrieval_error,
        "generation_error": generation_error,
        "selected_evidence_ids": selected_ids,
        "fallback_reasons": fallback_reasons or [],
        "selection_warnings": selection_warnings or [],
        "citation_guard_result": {
            "citation_id_valid": citation_id_valid,
            "citation_coverage_valid": citation_issue_count == 0,
            "citation_issue_count": citation_issue_count,
        },
        "missing_required_evidence_check": {
            "missing_required_evidence": missing_required_evidence,
            "selected_evidence_group_coverage": group_coverage,
            "selected_required_direct_coverage": group_coverage,
        },
    }
