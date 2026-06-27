"""Integration tests for evidence selection diagnostics workflow."""

from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.benchmark.evidence_selection_diagnostics import (
    EvidenceSelectionDiagnosticsPaths,
    run_evidence_selection_diagnostics,
)


def test_evidence_selection_diagnostics_workflow_labels_required_evidence_paths(
    tmp_path: Path,
) -> None:
    """Diagnostics reads tiny result/qrel artifacts and writes tmp-path reports."""
    paths = _paths(tmp_path)

    analysis = run_evidence_selection_diagnostics(paths)

    summary = analysis["summary"]
    matrix = analysis["retrieved_vs_selected_matrix"]["counts"]
    warning_summary = analysis["warning_summary"]
    assert summary["workflow_name"] == "evidence_selection_diagnostics"
    assert summary["development_first"] is True
    assert summary["diagnostic_counts"]["required_evidence_retrieved_but_not_selected"] == 1
    assert summary["diagnostic_counts"]["required_evidence_not_retrieved"] == 1
    assert summary["diagnostic_counts"]["selected_evidence_empty"] == 2
    assert summary["diagnostic_counts"]["answer_allowed_fallback"] == 2
    assert summary["diagnostic_counts"]["fallback_required_answered"] == 1
    assert matrix["required_evidence_retrieved_and_selected"] == 2
    assert matrix["required_evidence_retrieved_but_not_selected"] == 1
    assert matrix["required_evidence_not_retrieved"] == 1
    assert warning_summary["fallback_reason_counts"]["parent_context_only"] == 1
    assert warning_summary["selection_warning_counts"]["all_selected_evidence_caution"] == 1
    assert {path.name for path in paths.output_dir.iterdir()} == {
        "diagnostic_summary.json",
        "development_diagnostic_summary.json",
        "case_diagnostics.jsonl",
        "development_case_diagnostics.jsonl",
        "retrieved_vs_selected_matrix.json",
        "warning_summary.json",
        "domain_selection_diagnostics.json",
        "question_type_selection_diagnostics.json",
        "top_selector_failure_cases.jsonl",
        "evidence_selection_diagnostics.md",
    }
    assert all(path.is_relative_to(tmp_path) for path in paths.output_dir.iterdir())


def _paths(tmp_path: Path) -> EvidenceSelectionDiagnosticsPaths:
    """Create strict-generation, error-analysis, qrels, and group fixtures."""
    strict_dir = tmp_path / "strict_generation_evaluation"
    error_dir = tmp_path / "strict_generation_error_analysis"
    output_dir = tmp_path / "evidence_selection_diagnostics"
    strict_dir.mkdir()
    error_dir.mkdir()
    _write_jsonl(strict_dir / "case_results.jsonl", _cases())
    (strict_dir / "metrics_all.json").write_text(json.dumps({"query_count": 4}), encoding="utf-8")
    (strict_dir / "breakdowns.json").write_text(json.dumps({"split": {}}), encoding="utf-8")
    (strict_dir / "comparison.json").write_text(
        json.dumps({"systems": {"generation_baseline": {}, "strict_generation_evaluation": {}}}),
        encoding="utf-8",
    )
    for name in (
        "error_buckets.json",
        "development_error_buckets.json",
        "domain_error_summary.json",
        "question_type_error_summary.json",
    ):
        (error_dir / name).write_text(json.dumps({"retrieval_error": {"count": 0}}))
    qrels = tmp_path / "qrels.jsonl"
    groups = tmp_path / "evidence_groups.jsonl"
    _write_jsonl(
        qrels,
        [
            _qrel("selected", "required-selected"),
            _qrel("not-selected", "required-not-selected"),
            _qrel("not-retrieved", "required-missing"),
            _qrel("fallback-answered", "required-fallback"),
        ],
    )
    _write_jsonl(
        groups,
        [
            _group("selected", "required-selected"),
            _group("not-selected", "required-not-selected"),
            _group("not-retrieved", "required-missing"),
            _group("fallback-answered", "required-fallback"),
        ],
    )
    return EvidenceSelectionDiagnosticsPaths(
        case_results=strict_dir / "case_results.jsonl",
        metrics_all=strict_dir / "metrics_all.json",
        breakdowns=strict_dir / "breakdowns.json",
        comparison=strict_dir / "comparison.json",
        error_buckets=error_dir / "error_buckets.json",
        development_error_buckets=error_dir / "development_error_buckets.json",
        domain_error_summary=error_dir / "domain_error_summary.json",
        question_type_error_summary=error_dir / "question_type_error_summary.json",
        qrels=qrels,
        evidence_groups=groups,
        output_dir=output_dir,
    )


def _cases() -> list[dict[str, object]]:
    """Build tiny strict-generation cases for diagnostics."""
    return [
        _case(
            "selected",
            retrieved_evidence_ids=["required-selected"],
            selected_chunk_ids=["required-selected"],
            selected_evidence_ids=["required-selected"],
            pipeline_answered=True,
            pipeline_decision="answer_allowed",
            group_coverage=1.0,
        ),
        _case(
            "not-selected",
            retrieved_evidence_ids=["required-not-selected"],
            selected_chunk_ids=[],
            selected_evidence_ids=[],
            fallback_reasons=["parent_context_only"],
        ),
        _case(
            "not-retrieved",
            retrieved_evidence_ids=["other"],
            selected_chunk_ids=[],
            selected_evidence_ids=[],
            selection_warnings=["all_selected_evidence_caution"],
        ),
        _case(
            "fallback-answered",
            expected_decision="fallback_required",
            pipeline_decision="answer_allowed",
            pipeline_answered=True,
            retrieved_evidence_ids=["required-fallback"],
            selected_chunk_ids=["required-fallback"],
            selected_evidence_ids=["required-fallback"],
            group_coverage=1.0,
        ),
    ]


def _case(
    query_id: str,
    *,
    expected_decision: str = "answer_allowed",
    pipeline_decision: str = "fallback_required",
    pipeline_answered: bool = False,
    retrieved_evidence_ids: list[str],
    selected_chunk_ids: list[str],
    selected_evidence_ids: list[str],
    fallback_reasons: list[str] | None = None,
    selection_warnings: list[str] | None = None,
    group_coverage: float = 0.0,
) -> dict[str, object]:
    """Build one case result record for diagnostics."""
    return {
        "query_id": query_id,
        "split": "development",
        "primary_domain": "labor",
        "question_types": ["single_article_lookup"],
        "expected_decision": expected_decision,
        "pipeline_decision": pipeline_decision,
        "pipeline_answered": pipeline_answered,
        "case_status": "pass" if pipeline_answered else "fail",
        "retrieved_evidence_ids": retrieved_evidence_ids,
        "selected_chunk_ids": selected_chunk_ids,
        "selected_evidence_ids": selected_evidence_ids,
        "fallback_reasons": fallback_reasons or [],
        "selection_warnings": selection_warnings or [],
        "citation_guard_result": {"citation_id_valid": True, "citation_issue_count": 0},
        "missing_required_evidence_check": {"selected_evidence_group_coverage": group_coverage},
    }


def _qrel(query_id: str, chunk_id: str) -> dict[str, object]:
    """Build one direct evidence judgment."""
    return {"query_id": query_id, "chunk_id": chunk_id, "relevance": "required_direct"}


def _group(query_id: str, chunk_id: str) -> dict[str, object]:
    """Build one required evidence group."""
    return {
        "query_id": query_id,
        "evidence_group_id": f"group-{query_id}",
        "requirement": "required",
        "acceptable_chunk_ids": [chunk_id],
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """Write JSONL records to a temporary path."""
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
