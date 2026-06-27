"""Integration tests for strict generation error analysis workflow."""

from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.benchmark.strict_generation_error_analysis import (
    StrictGenerationErrorAnalysisPaths,
    run_strict_generation_error_analysis,
)


def test_strict_generation_error_analysis_workflow_counts_failure_buckets(
    tmp_path: Path,
) -> None:
    """Offline analysis reads tiny strict-generation artifacts and writes reports."""
    input_dir = tmp_path / "strict_generation_evaluation"
    output_dir = tmp_path / "strict_generation_error_analysis"
    input_dir.mkdir()
    _write_jsonl(input_dir / "case_results.jsonl", _cases())
    (input_dir / "metrics_all.json").write_text(json.dumps({"query_count": 6}), encoding="utf-8")
    (input_dir / "breakdowns.json").write_text(json.dumps({"split": {}}), encoding="utf-8")
    (input_dir / "comparison.json").write_text(
        json.dumps({"systems": {"generation_baseline": {}, "strict_generation_evaluation": {}}}),
        encoding="utf-8",
    )

    analysis = run_strict_generation_error_analysis(
        StrictGenerationErrorAnalysisPaths(
            case_results=input_dir / "case_results.jsonl",
            metrics_all=input_dir / "metrics_all.json",
            breakdowns=input_dir / "breakdowns.json",
            comparison=input_dir / "comparison.json",
            output_dir=output_dir,
        )
    )

    assert analysis["development_analyzed_first"] is True
    assert analysis["held_out_test_reporting_only"] is True
    assert analysis["error_buckets"]["expected_answer_allowed_but_pipeline_fallback"]["count"] == 3
    assert (
        analysis["error_buckets"]["expected_fallback_required_but_pipeline_answered"]["count"] == 1
    )
    assert analysis["error_buckets"]["retrieval_error"]["count"] == 1
    assert analysis["error_buckets"]["provider_or_generation_error"]["count"] == 1
    assert {path.name for path in output_dir.iterdir()} == {
        "error_buckets.json",
        "development_error_buckets.json",
        "domain_error_summary.json",
        "question_type_error_summary.json",
        "top_failure_cases.jsonl",
        "strict_generation_error_analysis.md",
    }
    markdown = (output_dir / "strict_generation_error_analysis.md").read_text(encoding="utf-8")
    assert "Primary bottleneck" in markdown
    assert all(path.is_relative_to(tmp_path) for path in output_dir.iterdir())


def _cases() -> list[dict[str, object]]:
    """Build synthetic case results covering major error buckets."""
    return [
        _case("answer-fallback", expected_decision="answer_allowed", pipeline_answered=False),
        _case(
            "fallback-answered",
            expected_decision="fallback_required",
            pipeline_decision="answer_allowed",
            pipeline_answered=True,
            case_status="fail",
        ),
        _case("retrieval-error", retrieval_error="offline", pipeline_answered=False),
        _case("generation-error", generation_error="provider offline", pipeline_answered=False),
        _case("pass-case", pipeline_answered=True, case_status="pass"),
        _case(
            "partial-case",
            pipeline_answered=True,
            case_status="partial",
            missing_required_evidence=True,
            group_coverage=0.5,
        ),
    ]


def _case(
    query_id: str,
    *,
    expected_decision: str = "answer_allowed",
    pipeline_decision: str = "fallback_required",
    pipeline_answered: bool = False,
    case_status: str = "fail",
    retrieval_error: str | None = None,
    generation_error: str | None = None,
    missing_required_evidence: bool = False,
    group_coverage: float = 1.0,
) -> dict[str, object]:
    """Build one synthetic strict-generation case."""
    return {
        "query_id": query_id,
        "split": "development",
        "primary_domain": "labor",
        "question_types": ["single_article_lookup"],
        "expected_decision": expected_decision,
        "pipeline_decision": pipeline_decision,
        "pipeline_answered": pipeline_answered,
        "case_status": case_status,
        "selected_evidence_ids": [] if not pipeline_answered else ["E1"],
        "fallback_reasons": ["parent_context_only"] if not pipeline_answered else [],
        "selection_warnings": [],
        "retrieval_error": retrieval_error,
        "generation_error": generation_error,
        "missing_required_evidence_check": {
            "missing_required_evidence": missing_required_evidence,
            "selected_evidence_group_coverage": group_coverage,
        },
        "citation_guard_result": {"citation_id_valid": True, "citation_issue_count": 0},
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """Write JSONL records to a temporary path."""
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
