from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.retrieval.evaluate_quality_gate import main as quality_gate_cli_main
from src.retrieval.generation_evaluation import GenerationEvalReport
from src.retrieval.quality_gate import (
    FaithfulnessReviewManifest,
    QualityGateEvaluator,
    QualityGatePolicy,
    load_faithfulness_manifest,
)


def test_current_like_baseline_is_partial() -> None:
    report = _report(
        [
            _case("blocking_pass", blocking=True),
            _case("blocking_partial", blocking=True),
            _case("fallback", decision="fallback_required", llm_called=False, citation_count=0),
            _case("non_blocking_partial", blocking=False),
        ]
    )
    verdicts = _manifest(
        [
            _review_case("blocking_pass", blocking=True, case_verdict="pass"),
            _review_case(
                "blocking_partial",
                blocking=True,
                case_verdict="partial",
                claims=[_claim("too_broad")],
            ),
            _review_case(
                "fallback",
                blocking=True,
                decision="fallback_required",
                case_verdict="not_applicable_for_fallback",
                substantive_legal_claims_present=False,
                claims=[_claim("not_applicable_for_fallback", claim_type="review_finding")],
            ),
            _review_case(
                "non_blocking_partial",
                blocking=False,
                case_verdict="partial",
                claims=[_claim("missing_key_condition", claim_type="review_finding")],
            ),
        ]
    )

    result = _evaluate(report, verdicts, _policy(report_case_ids(report)))

    assert result.status == "quality_gate_partial"
    assert result.hard_gate_passed is True
    assert result.quality_gate_passed is False
    assert [issue.code for issue in result.quality_violations] == [
        "blocking_case_not_pass",
        "blocking_too_broad_claims",
    ]
    assert result.metrics["generated_claim_rows"] == 2
    assert result.metrics["review_finding_rows"] == 2


def test_fully_clean_baseline_passes() -> None:
    report = _report(
        [
            _case("blocking_pass", blocking=True),
            _case("non_blocking_pass", blocking=False),
            _case("fallback", decision="fallback_required", llm_called=False, citation_count=0),
        ]
    )
    verdicts = _manifest(
        [
            _review_case("blocking_pass", blocking=True, case_verdict="pass"),
            _review_case("non_blocking_pass", blocking=False, case_verdict="pass"),
            _review_case(
                "fallback",
                blocking=True,
                decision="fallback_required",
                case_verdict="not_applicable_for_fallback",
                substantive_legal_claims_present=False,
                claims=[_claim("not_applicable_for_fallback", claim_type="review_finding")],
            ),
        ]
    )

    result = _evaluate(report, verdicts, _policy(report_case_ids(report)))

    assert result.status == "quality_gate_passed"
    assert result.hard_gate_passed is True
    assert result.quality_gate_passed is True


def test_unsupported_claim_fails() -> None:
    result = _single_claim_result("unsupported")

    assert result.status == "quality_gate_failed"
    assert any(issue.code == "unsupported_claims" for issue in result.hard_violations)


def test_irrelevant_citation_fails() -> None:
    result = _single_claim_result("irrelevant_citation")

    assert result.status == "quality_gate_failed"
    assert any(issue.code == "irrelevant_citations" for issue in result.hard_violations)


def test_unknown_citation_ids_fail() -> None:
    report = _report([_case("case")], unknown_citation_id_count=1)
    verdicts = _manifest([_review_case("case", case_verdict="pass")])

    result = _evaluate(report, verdicts, _policy(["case"]))

    assert result.status == "quality_gate_failed"
    assert any(issue.code == "unknown_citation_id_count" for issue in result.hard_violations)


def test_missing_citation_ids_fail() -> None:
    report = _report([_case("case")], missing_citation_id_count=1)
    verdicts = _manifest([_review_case("case", case_verdict="pass")])

    result = _evaluate(report, verdicts, _policy(["case"]))

    assert result.status == "quality_gate_failed"
    assert any(issue.code == "missing_citation_id_count" for issue in result.hard_violations)


def test_secret_leak_failure_fails() -> None:
    report = _report([_case("case")], secret_leak_failures=1)
    verdicts = _manifest([_review_case("case", case_verdict="pass")])

    result = _evaluate(report, verdicts, _policy(["case"]))

    assert result.status == "quality_gate_failed"
    assert any(issue.code == "secret_leak_failures" for issue in result.hard_violations)


def test_fallback_case_calling_llm_fails() -> None:
    report = _report(
        [_case("fallback", decision="fallback_required", llm_called=True, citation_count=0)]
    )
    verdicts = _manifest(
        [
            _review_case(
                "fallback",
                decision="fallback_required",
                case_verdict="not_applicable_for_fallback",
                substantive_legal_claims_present=False,
            )
        ]
    )

    result = _evaluate(report, verdicts, _policy(["fallback"]))

    assert result.status == "quality_gate_failed"
    assert any(issue.code == "fallback_called_llm" for issue in result.hard_violations)


def test_fallback_case_with_citations_fails() -> None:
    report = _report(
        [_case("fallback", decision="fallback_required", llm_called=False, citation_count=1)]
    )
    verdicts = _manifest(
        [
            _review_case(
                "fallback",
                decision="fallback_required",
                case_verdict="not_applicable_for_fallback",
                substantive_legal_claims_present=False,
            )
        ]
    )

    result = _evaluate(report, verdicts, _policy(["fallback"]))

    assert result.status == "quality_gate_failed"
    assert any(issue.code == "fallback_has_citations" for issue in result.hard_violations)


def test_missing_required_case_id_is_blocked() -> None:
    report = _report([_case("present")])
    verdicts = _manifest([_review_case("present")])

    result = _evaluate(report, verdicts, _policy(["present", "missing"]))

    assert result.status == "blocked"
    assert result.hard_gate_passed is False
    assert any(issue.code == "missing_generation_report_case" for issue in result.hard_violations)
    assert any(
        issue.code == "missing_faithfulness_verdict_case" for issue in result.hard_violations
    )


def test_all_caution_answer_allowed_without_manual_review_fails() -> None:
    report = _report([_case("case", all_caution=True)])
    verdicts = _manifest([_review_case("case", all_caution=True, manual_review_completed=False)])

    result = _evaluate(report, verdicts, _policy(["case"]))

    assert result.status == "quality_gate_failed"
    assert any(
        issue.code == "all_caution_manual_review_missing" for issue in result.hard_violations
    )


def test_too_broad_claim_in_blocking_case_is_partial() -> None:
    result = _single_claim_result("too_broad")

    assert result.status == "quality_gate_partial"
    assert any(issue.code == "blocking_too_broad_claims" for issue in result.quality_violations)


def test_missing_key_condition_in_blocking_case_is_partial() -> None:
    result = _single_claim_result("missing_key_condition", claim_type="review_finding")

    assert result.status == "quality_gate_partial"
    assert any(
        issue.code == "blocking_missing_key_conditions" for issue in result.quality_violations
    )


def test_partial_non_blocking_case_is_allowed_but_warned() -> None:
    report = _report([_case("case", blocking=False)])
    verdicts = _manifest(
        [
            _review_case(
                "case",
                blocking=False,
                case_verdict="partial",
                claims=[_claim("too_broad")],
            )
        ]
    )

    result = _evaluate(report, verdicts, _policy(["case"]))

    assert result.status == "quality_gate_passed"
    assert result.quality_violations == []
    assert [warning.code for warning in result.warnings] == ["non_blocking_too_broad_claims"]


def test_manifest_distinguishes_generated_claim_and_review_finding(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    manifest = _manifest(
        [
            _review_case(
                "case",
                claims=[
                    _claim("supported", claim_type="generated_claim"),
                    _claim("missing_key_condition", claim_type="review_finding"),
                ],
            )
        ]
    )
    path.write_text(manifest.model_dump_json(), encoding="utf-8")

    loaded = load_faithfulness_manifest(path)

    assert loaded.cases[0].claims[0].type == "generated_claim"
    assert loaded.cases[0].claims[1].type == "review_finding"


def test_cli_exit_codes(tmp_path: Path) -> None:
    assert _run_cli(tmp_path, _scenario("passed")) == 0
    assert _run_cli(tmp_path, _scenario("partial")) == 0
    assert _run_cli(tmp_path, _scenario("partial"), fail_on_partial=True) == 1
    assert _run_cli(tmp_path, _scenario("failed")) == 1
    assert _run_cli(tmp_path, _scenario("blocked")) == 1


def _single_claim_result(verdict: str, *, claim_type: str = "generated_claim") -> Any:
    report = _report([_case("case", blocking=True)])
    case_verdict = "partial" if verdict in {"too_broad", "missing_key_condition"} else "pass"
    verdicts = _manifest(
        [
            _review_case(
                "case",
                blocking=True,
                case_verdict=case_verdict,
                claims=[_claim(verdict, claim_type=claim_type)],
            )
        ]
    )
    return _evaluate(report, verdicts, _policy(["case"]))


def _scenario(name: str) -> tuple[GenerationEvalReport, FaithfulnessReviewManifest, list[str]]:
    if name == "passed":
        return (
            _report([_case("case")]),
            _manifest([_review_case("case", case_verdict="pass")]),
            ["case"],
        )
    if name == "partial":
        return (
            _report([_case("case")]),
            _manifest(
                [
                    _review_case(
                        "case",
                        case_verdict="partial",
                        claims=[_claim("too_broad")],
                    )
                ]
            ),
            ["case"],
        )
    if name == "failed":
        return (
            _report([_case("case")], unknown_citation_id_count=1),
            _manifest([_review_case("case", case_verdict="pass")]),
            ["case"],
        )
    if name == "blocked":
        return (
            _report([_case("case")]),
            _manifest([_review_case("case", case_verdict="pass")]),
            ["case", "missing"],
        )
    raise AssertionError(f"unknown scenario: {name}")


def _run_cli(
    tmp_path: Path,
    scenario: tuple[GenerationEvalReport, FaithfulnessReviewManifest, list[str]],
    *,
    fail_on_partial: bool = False,
) -> int:
    report, manifest, required_case_ids = scenario
    report_path = tmp_path / "report.json"
    manifest_path = tmp_path / "manifest.json"
    policy_path = tmp_path / "policy.yml"
    output_path = tmp_path / "output.json"
    report_path.write_text(report.model_dump_json(), encoding="utf-8")
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    policy_path.write_text(
        yaml.safe_dump(_policy(required_case_ids).model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    argv = [
        "--generation-report",
        str(report_path),
        "--faithfulness-verdicts",
        str(manifest_path),
        "--policy",
        str(policy_path),
        "--output",
        str(output_path),
    ]
    if fail_on_partial:
        argv.append("--fail-on-partial")
    return quality_gate_cli_main(argv)


def _evaluate(
    report: GenerationEvalReport,
    verdicts: FaithfulnessReviewManifest,
    policy: QualityGatePolicy,
) -> Any:
    return QualityGateEvaluator().evaluate(
        generation_report=report,
        verdicts=verdicts,
        policy=policy,
    )


def _case(
    case_id: str,
    *,
    blocking: bool = True,
    decision: str = "answer_allowed",
    llm_called: bool = True,
    citation_count: int = 1,
    all_caution: bool = False,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "query": f"Query for {case_id}",
        "passed": True,
        "allowed_decisions": [decision],
        "decision": decision,
        "decision_passed": True,
        "expected_llm_called": llm_called,
        "llm_called": llm_called,
        "llm_call_policy_passed": True,
        "fallback_policy_passed": True,
        "requires_citation_ids": decision == "answer_allowed",
        "citation_id_coverage_applicable": decision == "answer_allowed",
        "citation_id_coverage_passed": True,
        "citation_count": citation_count,
        "citation_issue_count": 0,
        "unknown_citation_id_count": 0,
        "missing_citation_id_count": 0,
        "vietnamese_language_passed": True,
        "forbidden_phrase_failures": [],
        "secret_leak_failures": [],
        "fallback_reasons": ["expected"] if decision != "answer_allowed" else [],
        "selection_warnings": [],
        "selected_evidence_count": 1 if decision == "answer_allowed" else 0,
        "caution_selected_count": 1 if all_caution else 0,
        "all_selected_evidence_caution": all_caution,
        "manual_review_required": False,
        "blocking": blocking,
        "evidence_previews": [],
        "cited_evidence_previews": [],
        "all_cited_ids_have_preview": True,
        "evidence_preview_count": 0,
        "cited_evidence_preview_count": 0,
        "evidence_preview_missing_count": 0,
        "caution_evidence_ids": ["E1"] if all_caution else [],
        "all_caution_evidence_ids": ["E1"] if all_caution else [],
        "validation_issues": [],
        "answer_preview": "Câu trả lời [E1]" if decision == "answer_allowed" else "Fallback",
        "answer_preview_truncated": False,
        "model": "test/model",
        "provider": "test-provider",
        "pipeline_error_count": 0,
        "notes": None,
    }


def _report(cases: list[dict[str, Any]], **overrides: Any) -> GenerationEvalReport:
    payload: dict[str, Any] = {
        "report_type": "naive_rag_generation_evaluation",
        "run_type": "manual_generation_eval",
        "workflow_name": "retrieval_naive_rag_generation",
        "status": "expanded_generation_eval_passed",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:01+00:00",
        "dataset_path": "data/eval/test.jsonl",
        "collection_name": "test_collection",
        "vector_name": "dense",
        "top_k": 20,
        "provider": "test-provider",
        "model": "test/model",
        "total_cases": len(cases),
        "passed_cases": len(cases),
        "failed_cases": 0,
        "blocking_case_count": sum(1 for case in cases if case["blocking"]),
        "non_blocking_case_count": sum(1 for case in cases if not case["blocking"]),
        "blocking_failed_cases": 0,
        "manual_review_required_count": 0,
        "decision_pass_rate": 1.0,
        "llm_call_policy_pass_rate": 1.0,
        "citation_id_coverage_rate": 1.0,
        "unknown_citation_id_count": 0,
        "missing_citation_id_count": 0,
        "fallback_policy_pass_rate": 1.0,
        "vietnamese_language_pass_rate": 1.0,
        "forbidden_phrase_failures": 0,
        "secret_leak_failures": 0,
        "total_caution_selected_count": 0,
        "cases_with_all_caution_evidence": 0,
        "selection_warning_count": 0,
        "evidence_preview_case_count": 0,
        "evidence_preview_total_count": 0,
        "cited_evidence_preview_total_count": 0,
        "evidence_preview_missing_count": 0,
        "all_cited_ids_have_preview_rate": 1.0,
        "cases_missing_evidence_preview": [],
        "cases": cases,
        "notes": [],
    }
    payload.update(overrides)
    return GenerationEvalReport.model_validate(payload)


def _review_case(
    case_id: str,
    *,
    blocking: bool = True,
    decision: str = "answer_allowed",
    case_verdict: str = "pass",
    all_caution: bool = False,
    manual_review_completed: bool = True,
    substantive_legal_claims_present: bool = True,
    claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "blocking": blocking,
        "decision": decision,
        "case_verdict": case_verdict,
        "all_caution": all_caution,
        "manual_review_completed": manual_review_completed,
        "substantive_legal_claims_present": substantive_legal_claims_present,
        "claims": claims or [_claim("supported")],
    }


def _manifest(cases: list[dict[str, Any]]) -> FaithfulnessReviewManifest:
    return FaithfulnessReviewManifest.model_validate(
        {
            "schema_version": "1.0",
            "source_review": "docs/test.md",
            "dataset_id": "test_dataset",
            "review_status": "test_status",
            "cases": cases,
        }
    )


def _claim(verdict: str, *, claim_type: str = "generated_claim") -> dict[str, Any]:
    return {
        "id": f"{claim_type}_{verdict}",
        "type": claim_type,
        "verdict": verdict,
        "cited_ids": ["E1"] if verdict != "not_applicable_for_fallback" else [],
        "notes": f"{verdict} note",
    }


def _policy(required_case_ids: list[str]) -> QualityGatePolicy:
    return QualityGatePolicy.model_validate(
        {
            "schema_version": "1.0",
            "required_case_ids": required_case_ids,
            "hard_gates": {
                "required_generation_report_status": ["expanded_generation_eval_passed"],
                "minimum_total_cases": len(required_case_ids),
                "minimum_decision_pass_rate": 1.0,
                "minimum_llm_call_policy_pass_rate": 1.0,
                "minimum_fallback_policy_pass_rate": 1.0,
                "minimum_citation_id_coverage_rate": 1.0,
                "maximum_unknown_citation_id_count": 0,
                "maximum_missing_citation_id_count": 0,
                "maximum_secret_leak_failures": 0,
                "maximum_forbidden_phrase_failures": 0,
                "maximum_unsupported_claims": 0,
                "maximum_irrelevant_citations": 0,
                "fallback_cases_must_not_call_llm": True,
                "fallback_cases_must_not_have_citations": True,
                "fallback_cases_must_not_make_substantive_legal_claims": True,
                "all_caution_answer_allowed_requires_manual_review": True,
            },
            "quality_gates": {
                "blocking_generated_cases_allowed_verdicts": ["pass"],
                "maximum_too_broad_claims_in_blocking_cases": 0,
                "maximum_missing_key_conditions_in_blocking_cases": 0,
                "allow_partial_non_blocking_cases": True,
                "report_too_broad_claims_in_non_blocking_cases": True,
                "report_missing_key_conditions_in_non_blocking_cases": True,
            },
            "status_policy": {
                "hard_gate_violation": "quality_gate_failed",
                "no_hard_violation_but_quality_violation": "quality_gate_partial",
                "all_gates_passed": "quality_gate_passed",
                "missing_required_input": "blocked",
            },
        }
    )


def report_case_ids(report: GenerationEvalReport) -> list[str]:
    return [case.id for case in report.cases]
