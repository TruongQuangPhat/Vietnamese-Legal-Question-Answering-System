"""Tests for offline evidence selection diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluation.analyze_evidence_selection_diagnostics import (
    DEFAULT_OUTPUT_DIR,
    build_arg_parser,
    main,
)
from src.evaluation.benchmark.evidence_selection_diagnostics import (
    WORKFLOW_NAME,
    EvidenceSelectionDiagnosticsPaths,
    build_case_diagnostic,
    build_evidence_selection_diagnostics,
    load_evidence_groups,
    load_jsonl_objects,
    load_qrels,
    render_markdown_report,
    run_evidence_selection_diagnostics,
)


def test_load_jsonl_cases(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    _write_jsonl(path, [_case("query-one")])

    records = load_jsonl_objects(path)

    assert records[0]["query_id"] == "query-one"


def test_load_qrels_and_required_evidence_groups(tmp_path: Path) -> None:
    qrels_path = tmp_path / "qrels.jsonl"
    groups_path = tmp_path / "groups.jsonl"
    _write_jsonl(
        qrels_path,
        [
            {
                "query_id": "query-one",
                "chunk_id": "chunk-required",
                "relevance": "required_direct",
            },
            {
                "query_id": "query-one",
                "chunk_id": "chunk-context",
                "relevance": "context_only",
            },
        ],
    )
    _write_jsonl(
        groups_path,
        [
            _group("query-one", "group-one", ["chunk-required"]),
            {
                "query_id": "query-one",
                "evidence_group_id": "group-extra",
                "requirement": "optional",
                "acceptable_chunk_ids": ["chunk-extra"],
            },
        ],
    )

    assert load_qrels(qrels_path) == {"query-one": {"chunk-required"}}
    assert load_evidence_groups(groups_path)["query-one"][0]["evidence_group_id"] == "group-one"


def test_case_diagnostics_detect_core_labels() -> None:
    qrels, groups = _references()

    fallback_case = build_case_diagnostic(_case("query-one"), qrels=qrels, evidence_groups=groups)
    answered_case = build_case_diagnostic(
        _case(
            "query-two",
            expected_decision="fallback_required",
            pipeline_decision="answer_allowed",
            pipeline_answered=True,
            case_status="fail",
            retrieved_evidence_ids=["chunk-required-two"],
            selected_chunk_ids=["chunk-required-two"],
            group_coverage=1.0,
        ),
        qrels=qrels,
        evidence_groups=groups,
    )
    missing_case = build_case_diagnostic(
        _case("query-three", retrieved_evidence_ids=["chunk-other"]),
        qrels=qrels,
        evidence_groups=groups,
    )
    incomplete_case = build_case_diagnostic(
        _case(
            "query-four",
            retrieved_evidence_ids=["chunk-required-four"],
            selected_chunk_ids=["chunk-other"],
            group_coverage=0.5,
        ),
        qrels=qrels,
        evidence_groups=groups,
    )
    exact_target_case = build_case_diagnostic(
        _case(
            "query-five",
            fallback_reasons=["exact_target_missing_in_eval_mode"],
            retrieved_evidence_ids=["chunk-five"],
            selected_chunk_ids=["chunk-five"],
        ),
        qrels=qrels,
        evidence_groups=groups,
    )

    assert {
        "answer_allowed_fallback",
        "selected_evidence_empty",
        "required_evidence_retrieved_but_not_selected",
        "parent_context_only_fallback",
        "all_selected_evidence_caution",
    }.issubset(fallback_case["diagnostic_labels"])
    assert "fallback_required_answered" in answered_case["diagnostic_labels"]
    assert "required_evidence_not_retrieved" in missing_case["diagnostic_labels"]
    assert "selected_but_incomplete_required_group_coverage" in incomplete_case["diagnostic_labels"]
    assert "exact_target_missing_in_eval_mode" in exact_target_case["diagnostic_labels"]


def test_build_diagnostics_aggregates_domain_and_question_type_summaries() -> None:
    analysis = build_evidence_selection_diagnostics(
        cases=_cases(),
        qrels=_references()[0],
        evidence_groups=_references()[1],
        metrics={"query_count": 5},
        breakdowns={"split": {}},
        comparison={"systems": {"generation_baseline": {}, "strict_generation_evaluation": {}}},
        error_buckets={"retrieval_error": {"count": 0}},
        development_error_buckets={"retrieval_error": {"count": 0}},
        domain_error_summary={"labor": {"case_count": 1}},
        question_type_error_summary={"single_article_lookup": {"case_count": 1}},
    )

    assert analysis["summary"]["report_type"] == WORKFLOW_NAME
    assert analysis["summary"]["development_first"] is True
    assert analysis["summary"]["held_out_reporting_only"] is True
    assert analysis["summary"]["retrieval_strategy"] == "coverage_aware_quota"
    assert analysis["development_summary"]["query_count"] == 4
    assert analysis["summary"]["development_diagnostic_counts"]["answer_allowed_fallback"] == 3
    assert analysis["domain_selection_diagnostics"]["labor"]["case_count"] == 2
    assert (
        analysis["question_type_selection_diagnostics"]["single_article_lookup"][
            "selected_evidence_empty_count"
        ]
        == 2
    )
    assert (
        analysis["retrieved_vs_selected_matrix"]["counts"][
            "required_evidence_retrieved_but_not_selected"
        ]
        == 2
    )


def test_markdown_report_is_generated() -> None:
    analysis = build_evidence_selection_diagnostics(
        cases=_cases(),
        qrels=_references()[0],
        evidence_groups=_references()[1],
        metrics={"query_count": 5},
        breakdowns={"split": {}},
        comparison={"systems": {"generation_baseline": {}, "strict_generation_evaluation": {}}},
        error_buckets={},
        development_error_buckets={},
        domain_error_summary={},
        question_type_error_summary={},
    )

    markdown = render_markdown_report(analysis)

    assert "# Evidence Selection Diagnostics" in markdown
    assert "Retrieved-but-not-selected required evidence cases" in markdown
    assert "Recommended next actions" in markdown


def test_run_diagnostics_writes_expected_artifacts(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    analysis = run_evidence_selection_diagnostics(paths)

    assert analysis["summary"]["workflow_name"] == WORKFLOW_NAME
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
    summary = json.loads((paths.output_dir / "diagnostic_summary.json").read_text())
    case_rows = [
        json.loads(line)
        for line in (paths.output_dir / "case_diagnostics.jsonl").read_text().splitlines()
    ]
    assert summary["source_workflow"] == "strict_generation_evaluation"
    assert case_rows[0]["likely_bottleneck"] == "evidence_selection"


def test_cli_defaults_and_help_do_not_run_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = build_arg_parser().parse_args([])
    assert args.output_dir == DEFAULT_OUTPUT_DIR

    monkeypatch.setattr(
        "scripts.evaluation.analyze_evidence_selection_diagnostics.run_evidence_selection_diagnostics",
        lambda paths: pytest.fail("diagnostics must not run for help"),
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def _paths(tmp_path: Path) -> EvidenceSelectionDiagnosticsPaths:
    strict_dir = tmp_path / "strict_generation_evaluation"
    error_dir = tmp_path / "strict_generation_error_analysis"
    output_dir = tmp_path / "evidence_selection_diagnostics"
    strict_dir.mkdir()
    error_dir.mkdir()
    _write_jsonl(strict_dir / "case_results.jsonl", _cases())
    (strict_dir / "metrics_all.json").write_text(json.dumps({"query_count": 5}))
    (strict_dir / "breakdowns.json").write_text(json.dumps({"split": {}}))
    (strict_dir / "comparison.json").write_text(
        json.dumps({"systems": {"generation_baseline": {}, "strict_generation_evaluation": {}}})
    )
    (error_dir / "error_buckets.json").write_text(json.dumps({"retrieval_error": {"count": 0}}))
    (error_dir / "development_error_buckets.json").write_text(
        json.dumps({"retrieval_error": {"count": 0}})
    )
    (error_dir / "domain_error_summary.json").write_text(json.dumps({"labor": {"case_count": 1}}))
    (error_dir / "question_type_error_summary.json").write_text(
        json.dumps({"single_article_lookup": {"case_count": 1}})
    )
    qrels_path = tmp_path / "qrels.jsonl"
    groups_path = tmp_path / "groups.jsonl"
    _write_jsonl(qrels_path, _qrels())
    _write_jsonl(groups_path, _groups())
    return EvidenceSelectionDiagnosticsPaths(
        case_results=strict_dir / "case_results.jsonl",
        metrics_all=strict_dir / "metrics_all.json",
        breakdowns=strict_dir / "breakdowns.json",
        comparison=strict_dir / "comparison.json",
        error_buckets=error_dir / "error_buckets.json",
        development_error_buckets=error_dir / "development_error_buckets.json",
        domain_error_summary=error_dir / "domain_error_summary.json",
        question_type_error_summary=error_dir / "question_type_error_summary.json",
        qrels=qrels_path,
        evidence_groups=groups_path,
        output_dir=output_dir,
    )


def _cases() -> list[dict[str, object]]:
    return [
        _case("query-one"),
        _case(
            "query-two",
            expected_decision="fallback_required",
            pipeline_decision="answer_allowed",
            pipeline_answered=True,
            case_status="fail",
            primary_domain="traffic",
            question_types=["fallback"],
            retrieved_evidence_ids=["chunk-required-two"],
            selected_chunk_ids=["chunk-required-two"],
            group_coverage=1.0,
        ),
        _case(
            "query-three",
            primary_domain="labor",
            question_types=["single_article_lookup"],
            retrieved_evidence_ids=["chunk-other"],
        ),
        _case(
            "query-four",
            primary_domain="business",
            question_types=["complete_list"],
            retrieved_evidence_ids=["chunk-required-four"],
            selected_chunk_ids=["chunk-other"],
            group_coverage=0.5,
        ),
        _case(
            "query-held",
            split="held_out_test",
            primary_domain="civil",
            question_types=["definition"],
            retrieved_evidence_ids=["chunk-held"],
            selected_chunk_ids=["chunk-held"],
            fallback_reasons=["exact_target_missing_in_eval_mode"],
        ),
    ]


def _case(
    query_id: str,
    *,
    split: str = "development",
    expected_decision: str = "answer_allowed",
    pipeline_decision: str = "fallback_required",
    pipeline_answered: bool = False,
    case_status: str = "fail",
    primary_domain: str = "labor",
    question_types: list[str] | None = None,
    retrieved_evidence_ids: list[str] | None = None,
    selected_chunk_ids: list[str] | None = None,
    fallback_reasons: list[str] | None = None,
    selection_warnings: list[str] | None = None,
    group_coverage: float = 0.0,
) -> dict[str, object]:
    return {
        "query_id": query_id,
        "split": split,
        "primary_domain": primary_domain,
        "question_types": question_types or ["single_article_lookup"],
        "expected_decision": expected_decision,
        "pipeline_decision": pipeline_decision,
        "pipeline_answered": pipeline_answered,
        "case_status": case_status,
        "retrieved_evidence_ids": retrieved_evidence_ids or ["chunk-required-one"],
        "selected_chunk_ids": selected_chunk_ids or [],
        "selected_evidence_ids": selected_chunk_ids or [],
        "fallback_reasons": fallback_reasons
        or ["parent_context_only", "all_selected_evidence_caution"],
        "selection_warnings": selection_warnings or ["all_selected_evidence_caution"],
        "missing_required_evidence_check": {
            "selected_evidence_group_coverage": group_coverage,
        },
        "citation_guard_result": {
            "citation_issue_count": 0,
            "citation_id_valid": True,
            "citation_coverage_valid": True,
        },
        "retrieval_error": None,
        "generation_error": None,
    }


def _references() -> tuple[dict[str, set[str]], dict[str, list[dict[str, object]]]]:
    return load_qrels_from_records(_qrels()), load_groups_from_records(_groups())


def load_qrels_from_records(records: list[dict[str, object]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for record in records:
        grouped.setdefault(str(record["query_id"]), set()).add(str(record["chunk_id"]))
    return grouped


def load_groups_from_records(
    records: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        grouped.setdefault(str(record["query_id"]), []).append(record)
    return grouped


def _qrels() -> list[dict[str, object]]:
    return [
        {
            "query_id": "query-one",
            "chunk_id": "chunk-required-one",
            "relevance": "required_direct",
        },
        {
            "query_id": "query-two",
            "chunk_id": "chunk-required-two",
            "relevance": "required_direct",
        },
        {
            "query_id": "query-three",
            "chunk_id": "chunk-required-three",
            "relevance": "required_direct",
        },
        {
            "query_id": "query-four",
            "chunk_id": "chunk-required-four",
            "relevance": "required_direct",
        },
    ]


def _groups() -> list[dict[str, object]]:
    return [
        _group("query-one", "group-one", ["chunk-required-one"]),
        _group("query-two", "group-two", ["chunk-required-two"]),
        _group("query-three", "group-three", ["chunk-required-three"]),
        _group("query-four", "group-four", ["chunk-required-four"]),
    ]


def _group(
    query_id: str,
    group_id: str,
    chunks: list[str],
) -> dict[str, object]:
    return {
        "query_id": query_id,
        "evidence_group_id": group_id,
        "requirement": "required",
        "acceptable_chunk_ids": chunks,
        "acceptable_legal_targets": [],
        "minimum_hits": 1,
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(f"{json.dumps(record, ensure_ascii=False)}\n" for record in records),
        encoding="utf-8",
    )
