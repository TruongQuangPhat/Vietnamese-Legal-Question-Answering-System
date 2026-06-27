"""Offline quality gate for the reviewed Naive RAG baseline.

The gate compares a Naive RAG generation evaluation report with the structured
manual faithfulness verdict manifest and a configurable policy. It does not call
OpenRouter, Qdrant, retrieval, generation, or any corpus-processing workflow.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.retrieval.generation_evaluation import GenerationEvalReport
from src.retrieval.selection import AnswerabilityDecision

ClaimReviewType = Literal["generated_claim", "review_finding"]
ClaimReviewVerdict = Literal[
    "supported",
    "partially_supported",
    "unsupported",
    "too_broad",
    "missing_key_condition",
    "irrelevant_citation",
    "needs_more_evidence",
    "not_applicable_for_fallback",
]
CaseReviewVerdict = Literal[
    "pass",
    "partial",
    "fail",
    "needs_more_evidence",
    "not_applicable_for_fallback",
]
GateStatus = Literal[
    "quality_gate_passed",
    "quality_gate_partial",
    "quality_gate_failed",
    "blocked",
]
GateIssueKind = Literal["hard", "quality", "warning", "blocked"]


class ClaimReviewRecord(BaseModel):
    """One claim or manual review finding from the manual faithfulness verdict manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., min_length=1)
    type: ClaimReviewType
    verdict: ClaimReviewVerdict
    cited_ids: list[str] = Field(default_factory=list)
    notes: str = Field(..., min_length=1)

    @field_validator("id", "notes")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Trim text fields and reject blank values."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be blank")
        return normalized


class CaseReviewRecord(BaseModel):
    """Human manual faithfulness review verdict for one generation-evaluation case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., min_length=1)
    blocking: bool
    decision: AnswerabilityDecision
    case_verdict: CaseReviewVerdict
    all_caution: bool
    manual_review_completed: bool
    substantive_legal_claims_present: bool = True
    claims: list[ClaimReviewRecord] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        """Trim and validate a case ID."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("case id must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_fallback_case(self) -> CaseReviewRecord:
        """Require fallback verdicts to avoid substantive legal claims."""
        if (
            self.case_verdict == "not_applicable_for_fallback"
            and self.substantive_legal_claims_present
        ):
            raise ValueError("fallback cases must not mark substantive legal claims as present")
        return self


class FaithfulnessReviewManifest(BaseModel):
    """Structured manual faithfulness review claim-to-citation verdict manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    source_review: str
    dataset_id: str
    review_status: str
    cases: list[CaseReviewRecord] = Field(..., min_length=1)

    @model_validator(mode="after")
    def require_unique_cases(self) -> FaithfulnessReviewManifest:
        """Reject duplicate case IDs."""
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("faithfulness manifest contains duplicate case IDs")
        return self


class HardGatePolicy(BaseModel):
    """Configurable deterministic safety gates that fail the baseline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_generation_report_status: list[str] = Field(..., min_length=1)
    minimum_total_cases: int = Field(..., ge=1)
    minimum_decision_pass_rate: float = Field(..., ge=0.0, le=1.0)
    minimum_llm_call_policy_pass_rate: float = Field(..., ge=0.0, le=1.0)
    minimum_fallback_policy_pass_rate: float = Field(..., ge=0.0, le=1.0)
    minimum_citation_id_coverage_rate: float = Field(..., ge=0.0, le=1.0)
    maximum_unknown_citation_id_count: int = Field(..., ge=0)
    maximum_missing_citation_id_count: int = Field(..., ge=0)
    maximum_secret_leak_failures: int = Field(..., ge=0)
    maximum_forbidden_phrase_failures: int = Field(..., ge=0)
    maximum_unsupported_claims: int = Field(..., ge=0)
    maximum_irrelevant_citations: int = Field(..., ge=0)
    fallback_cases_must_not_call_llm: bool = True
    fallback_cases_must_not_have_citations: bool = True
    fallback_cases_must_not_make_substantive_legal_claims: bool = True
    all_caution_answer_allowed_requires_manual_review: bool = True


class QualityGatePolicySection(BaseModel):
    """Configurable quality gates that can make the baseline partial."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    blocking_generated_cases_allowed_verdicts: list[CaseReviewVerdict] = Field(
        ...,
        min_length=1,
    )
    maximum_too_broad_claims_in_blocking_cases: int = Field(..., ge=0)
    maximum_missing_key_conditions_in_blocking_cases: int = Field(..., ge=0)
    allow_partial_non_blocking_cases: bool = True
    report_too_broad_claims_in_non_blocking_cases: bool = True
    report_missing_key_conditions_in_non_blocking_cases: bool = True


class StatusPolicy(BaseModel):
    """Status labels emitted for each gate outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hard_gate_violation: GateStatus
    no_hard_violation_but_quality_violation: GateStatus
    all_gates_passed: GateStatus
    missing_required_input: GateStatus


class QualityGatePolicy(BaseModel):
    """Top-level quality gate policy loaded from YAML."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    required_case_ids: list[str] = Field(..., min_length=1)
    hard_gates: HardGatePolicy
    quality_gates: QualityGatePolicySection
    status_policy: StatusPolicy

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> QualityGatePolicy:
        """Reject duplicate required case IDs."""
        if len(self.required_case_ids) != len(set(self.required_case_ids)):
            raise ValueError("required_case_ids must be unique")
        return self


class GateCheckResult(BaseModel):
    """One hard-gate violation, quality violation, warning, or blocker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    kind: GateIssueKind
    message: str
    case_id: str | None = None


class CaseGateResult(BaseModel):
    """Case-level quality-gate result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    blocking: bool
    decision: AnswerabilityDecision
    case_verdict: CaseReviewVerdict
    generated_case: bool
    fallback_case: bool
    manual_review_completed: bool
    all_caution: bool
    supported_claims: int = Field(0, ge=0)
    too_broad_claims: int = Field(0, ge=0)
    missing_key_conditions: int = Field(0, ge=0)
    unsupported_claims: int = Field(0, ge=0)
    irrelevant_citations: int = Field(0, ge=0)
    hard_violations: list[GateCheckResult] = Field(default_factory=list)
    quality_violations: list[GateCheckResult] = Field(default_factory=list)
    warnings: list[GateCheckResult] = Field(default_factory=list)


class QualityGateResult(BaseModel):
    """Serializable result for the quality gate offline quality gate."""

    model_config = ConfigDict(extra="forbid")

    report_type: str = "naive_rag_quality_gate"
    run_type: str = "offline_regression_gate"
    workflow_name: str = "retrieval_naive_rag_quality_gate"
    status: GateStatus
    hard_gate_passed: bool
    quality_gate_passed: bool
    hard_violations: list[GateCheckResult] = Field(default_factory=list)
    quality_violations: list[GateCheckResult] = Field(default_factory=list)
    warnings: list[GateCheckResult] = Field(default_factory=list)
    metrics: dict[str, int | float] = Field(default_factory=dict)
    cases: list[CaseGateResult] = Field(default_factory=list)


class QualityGateEvaluator:
    """Evaluate the reviewed generation baseline against deterministic QA gates.

    The evaluator is intentionally offline. It accepts already-produced generation
    report JSON, a source-controlled manual faithfulness verdict manifest, and a YAML
    policy. It never calls Qdrant, OpenRouter, embedding models, retrieval, or
    generation.
    """

    def evaluate_paths(
        self,
        *,
        generation_report_path: Path,
        faithfulness_verdicts_path: Path,
        policy_path: Path,
    ) -> QualityGateResult:
        """Load inputs from disk and evaluate the quality gate.

        Args:
            generation_report_path: Existing generation evaluation generation-evaluation report.
            faithfulness_verdicts_path: Structured manual faithfulness verdict manifest.
            policy_path: YAML policy file with hard and quality thresholds.

        Returns:
            Serializable gate result.

        Raises:
            OSError: If an input file cannot be read.
            ValueError: If an input file is malformed.
        """
        return self.evaluate(
            generation_report=load_generation_report(generation_report_path),
            verdicts=load_faithfulness_manifest(faithfulness_verdicts_path),
            policy=load_quality_gate_policy(policy_path),
        )

    def evaluate(
        self,
        *,
        generation_report: GenerationEvalReport,
        verdicts: FaithfulnessReviewManifest,
        policy: QualityGatePolicy,
    ) -> QualityGateResult:
        """Evaluate already-loaded generation evaluation/9D inputs against a policy."""
        report_cases = {case.id: case for case in generation_report.cases}
        verdict_cases = {case.id: case for case in verdicts.cases}
        blockers = self._required_case_blockers(report_cases, verdict_cases, policy)
        if blockers:
            return QualityGateResult(
                status=policy.status_policy.missing_required_input,
                hard_gate_passed=False,
                quality_gate_passed=False,
                hard_violations=blockers,
                metrics=self._aggregate_metrics(generation_report, verdicts, []),
            )

        hard_violations = self._report_hard_violations(generation_report, policy)
        case_results: list[CaseGateResult] = []
        for case_id in policy.required_case_ids:
            case_results.append(
                self._evaluate_case(
                    report_case=report_cases[case_id],
                    review_case=verdict_cases[case_id],
                    policy=policy,
                )
            )

        for case_result in case_results:
            hard_violations.extend(case_result.hard_violations)

        hard_violations.extend(self._manifest_hard_violations(verdicts, policy))
        quality_violations = [
            issue for case_result in case_results for issue in case_result.quality_violations
        ]
        warnings = [issue for case_result in case_results for issue in case_result.warnings]
        metrics = self._aggregate_metrics(generation_report, verdicts, case_results)

        hard_gate_passed = not hard_violations
        quality_gate_passed = not quality_violations
        if not hard_gate_passed:
            status = policy.status_policy.hard_gate_violation
        elif not quality_gate_passed:
            status = policy.status_policy.no_hard_violation_but_quality_violation
        else:
            status = policy.status_policy.all_gates_passed

        return QualityGateResult(
            status=status,
            hard_gate_passed=hard_gate_passed,
            quality_gate_passed=quality_gate_passed,
            hard_violations=hard_violations,
            quality_violations=quality_violations,
            warnings=warnings,
            metrics=metrics,
            cases=case_results,
        )

    def _required_case_blockers(
        self,
        report_cases: dict[str, Any],
        verdict_cases: dict[str, CaseReviewRecord],
        policy: QualityGatePolicy,
    ) -> list[GateCheckResult]:
        blockers: list[GateCheckResult] = []
        for case_id in policy.required_case_ids:
            if case_id not in report_cases:
                blockers.append(
                    _issue(
                        "missing_generation_report_case",
                        "blocked",
                        f"Required case is missing from generation report: {case_id}",
                        case_id,
                    )
                )
            if case_id not in verdict_cases:
                blockers.append(
                    _issue(
                        "missing_faithfulness_verdict_case",
                        "blocked",
                        f"Required case is missing from manual faithfulness review verdicts: {case_id}",
                        case_id,
                    )
                )
        return blockers

    def _report_hard_violations(
        self,
        report: GenerationEvalReport,
        policy: QualityGatePolicy,
    ) -> list[GateCheckResult]:
        gates = policy.hard_gates
        checks: list[GateCheckResult] = []
        if report.status not in gates.required_generation_report_status:
            checks.append(
                _issue(
                    "generation_report_status",
                    "hard",
                    f"Generation report status {report.status!r} is not allowed.",
                )
            )
        _check_minimum(checks, "total_cases", report.total_cases, gates.minimum_total_cases)
        _check_minimum(
            checks,
            "decision_pass_rate",
            report.decision_pass_rate,
            gates.minimum_decision_pass_rate,
        )
        _check_minimum(
            checks,
            "llm_call_policy_pass_rate",
            report.llm_call_policy_pass_rate,
            gates.minimum_llm_call_policy_pass_rate,
        )
        _check_minimum(
            checks,
            "fallback_policy_pass_rate",
            report.fallback_policy_pass_rate,
            gates.minimum_fallback_policy_pass_rate,
        )
        _check_minimum(
            checks,
            "citation_id_coverage_rate",
            report.citation_id_coverage_rate,
            gates.minimum_citation_id_coverage_rate,
        )
        _check_maximum(
            checks,
            "unknown_citation_id_count",
            report.unknown_citation_id_count,
            gates.maximum_unknown_citation_id_count,
        )
        _check_maximum(
            checks,
            "missing_citation_id_count",
            report.missing_citation_id_count,
            gates.maximum_missing_citation_id_count,
        )
        _check_maximum(
            checks,
            "secret_leak_failures",
            report.secret_leak_failures,
            gates.maximum_secret_leak_failures,
        )
        _check_maximum(
            checks,
            "forbidden_phrase_failures",
            report.forbidden_phrase_failures,
            gates.maximum_forbidden_phrase_failures,
        )
        return checks

    def _evaluate_case(
        self,
        *,
        report_case: Any,
        review_case: CaseReviewRecord,
        policy: QualityGatePolicy,
    ) -> CaseGateResult:
        hard: list[GateCheckResult] = []
        quality: list[GateCheckResult] = []
        warnings: list[GateCheckResult] = []

        if report_case.decision != review_case.decision:
            hard.append(
                _issue(
                    "case_decision_mismatch",
                    "hard",
                    "Generation report decision does not match manual faithfulness verdict manifest.",
                    review_case.id,
                )
            )
        if report_case.blocking != review_case.blocking:
            hard.append(
                _issue(
                    "case_blocking_mismatch",
                    "hard",
                    "Generation report blocking flag does not match manual faithfulness verdict manifest.",
                    review_case.id,
                )
            )
        if report_case.all_selected_evidence_caution != review_case.all_caution:
            hard.append(
                _issue(
                    "case_all_caution_mismatch",
                    "hard",
                    "Generation report all-caution flag does not match manual faithfulness verdict manifest.",
                    review_case.id,
                )
            )

        fallback_case = review_case.case_verdict == "not_applicable_for_fallback"
        generated_case = report_case.decision == AnswerabilityDecision.ANSWER_ALLOWED
        if fallback_case:
            self._evaluate_fallback_case(report_case, review_case, policy, hard)
        if (
            policy.hard_gates.all_caution_answer_allowed_requires_manual_review
            and generated_case
            and report_case.all_selected_evidence_caution
            and not review_case.manual_review_completed
        ):
            hard.append(
                _issue(
                    "all_caution_manual_review_missing",
                    "hard",
                    "All-caution answer-allowed case lacks completed manual review.",
                    review_case.id,
                )
            )

        verdict_counts = Counter(claim.verdict for claim in review_case.claims)
        too_broad = verdict_counts["too_broad"]
        missing_key = verdict_counts["missing_key_condition"]
        unsupported = verdict_counts["unsupported"]
        irrelevant = verdict_counts["irrelevant_citation"]

        if generated_case and review_case.blocking:
            self._evaluate_blocking_generated_case(
                review_case,
                policy,
                too_broad,
                missing_key,
                quality,
            )
        elif generated_case and not review_case.blocking:
            self._evaluate_non_blocking_generated_case(
                review_case,
                policy,
                too_broad,
                missing_key,
                warnings,
            )

        return CaseGateResult(
            id=review_case.id,
            blocking=review_case.blocking,
            decision=review_case.decision,
            case_verdict=review_case.case_verdict,
            generated_case=generated_case,
            fallback_case=fallback_case,
            manual_review_completed=review_case.manual_review_completed,
            all_caution=review_case.all_caution,
            supported_claims=verdict_counts["supported"],
            too_broad_claims=too_broad,
            missing_key_conditions=missing_key,
            unsupported_claims=unsupported,
            irrelevant_citations=irrelevant,
            hard_violations=hard,
            quality_violations=quality,
            warnings=warnings,
        )

    def _evaluate_fallback_case(
        self,
        report_case: Any,
        review_case: CaseReviewRecord,
        policy: QualityGatePolicy,
        hard: list[GateCheckResult],
    ) -> None:
        gates = policy.hard_gates
        if gates.fallback_cases_must_not_call_llm and report_case.llm_called:
            hard.append(
                _issue(
                    "fallback_called_llm",
                    "hard",
                    "Fallback case called the LLM.",
                    review_case.id,
                )
            )
        if gates.fallback_cases_must_not_have_citations and report_case.citation_count:
            hard.append(
                _issue(
                    "fallback_has_citations",
                    "hard",
                    "Fallback case contains citations.",
                    review_case.id,
                )
            )
        if (
            gates.fallback_cases_must_not_make_substantive_legal_claims
            and review_case.substantive_legal_claims_present
        ):
            hard.append(
                _issue(
                    "fallback_has_substantive_claim",
                    "hard",
                    "Fallback case is marked as containing substantive legal claims.",
                    review_case.id,
                )
            )

    def _evaluate_blocking_generated_case(
        self,
        review_case: CaseReviewRecord,
        policy: QualityGatePolicy,
        too_broad: int,
        missing_key: int,
        quality: list[GateCheckResult],
    ) -> None:
        gates = policy.quality_gates
        if review_case.case_verdict not in gates.blocking_generated_cases_allowed_verdicts:
            quality.append(
                _issue(
                    "blocking_case_not_pass",
                    "quality",
                    f"Blocking generated case verdict is {review_case.case_verdict!r}.",
                    review_case.id,
                )
            )
        if too_broad > gates.maximum_too_broad_claims_in_blocking_cases:
            quality.append(
                _issue(
                    "blocking_too_broad_claims",
                    "quality",
                    f"Blocking case has {too_broad} too-broad claim(s).",
                    review_case.id,
                )
            )
        if missing_key > gates.maximum_missing_key_conditions_in_blocking_cases:
            quality.append(
                _issue(
                    "blocking_missing_key_conditions",
                    "quality",
                    f"Blocking case has {missing_key} missing-key-condition finding(s).",
                    review_case.id,
                )
            )

    def _evaluate_non_blocking_generated_case(
        self,
        review_case: CaseReviewRecord,
        policy: QualityGatePolicy,
        too_broad: int,
        missing_key: int,
        warnings: list[GateCheckResult],
    ) -> None:
        gates = policy.quality_gates
        if review_case.case_verdict == "partial" and not gates.allow_partial_non_blocking_cases:
            warnings.append(
                _issue(
                    "non_blocking_partial_case",
                    "warning",
                    "Non-blocking case is partial and policy disallows partial cases.",
                    review_case.id,
                )
            )
        if too_broad and gates.report_too_broad_claims_in_non_blocking_cases:
            warnings.append(
                _issue(
                    "non_blocking_too_broad_claims",
                    "warning",
                    f"Non-blocking case has {too_broad} too-broad claim(s).",
                    review_case.id,
                )
            )
        if missing_key and gates.report_missing_key_conditions_in_non_blocking_cases:
            warnings.append(
                _issue(
                    "non_blocking_missing_key_conditions",
                    "warning",
                    f"Non-blocking case has {missing_key} missing-key-condition finding(s).",
                    review_case.id,
                )
            )

    def _manifest_hard_violations(
        self,
        verdicts: FaithfulnessReviewManifest,
        policy: QualityGatePolicy,
    ) -> list[GateCheckResult]:
        verdict_counts = Counter(claim.verdict for case in verdicts.cases for claim in case.claims)
        checks: list[GateCheckResult] = []
        _check_maximum(
            checks,
            "unsupported_claims",
            verdict_counts["unsupported"],
            policy.hard_gates.maximum_unsupported_claims,
        )
        _check_maximum(
            checks,
            "irrelevant_citations",
            verdict_counts["irrelevant_citation"],
            policy.hard_gates.maximum_irrelevant_citations,
        )
        return checks

    def _aggregate_metrics(
        self,
        report: GenerationEvalReport,
        verdicts: FaithfulnessReviewManifest,
        case_results: list[CaseGateResult],
    ) -> dict[str, int | float]:
        claim_counts = Counter(claim.verdict for case in verdicts.cases for claim in case.claims)
        type_counts = Counter(claim.type for case in verdicts.cases for claim in case.claims)
        blocking_generated_cases = [
            case for case in case_results if case.blocking and case.generated_case
        ]
        blocking_generated_passes = [
            case for case in blocking_generated_cases if case.case_verdict == "pass"
        ]
        manual_review_completed = [case for case in verdicts.cases if case.manual_review_completed]
        blocking_rate = _safe_rate(
            len(blocking_generated_passes),
            len(blocking_generated_cases),
        )
        return {
            "total_cases": report.total_cases,
            "required_cases": len(verdicts.cases),
            "generated_claim_rows": type_counts["generated_claim"],
            "review_finding_rows": type_counts["review_finding"],
            "supported_claims": claim_counts["supported"],
            "partially_supported_claims": claim_counts["partially_supported"],
            "unsupported_claims": claim_counts["unsupported"],
            "too_broad_claims": claim_counts["too_broad"],
            "missing_key_conditions": claim_counts["missing_key_condition"],
            "irrelevant_citations": claim_counts["irrelevant_citation"],
            "needs_more_evidence": claim_counts["needs_more_evidence"],
            "blocking_generated_case_count": len(blocking_generated_cases),
            "blocking_generated_case_pass_rate": blocking_rate,
            "manual_review_completion_rate": _safe_rate(
                len(manual_review_completed),
                len(verdicts.cases),
            ),
            "unknown_citation_id_count": report.unknown_citation_id_count,
            "missing_citation_id_count": report.missing_citation_id_count,
            "secret_leak_failures": report.secret_leak_failures,
        }


def load_generation_report(path: Path) -> GenerationEvalReport:
    """Load a Naive RAG generation evaluation report from JSON."""
    return GenerationEvalReport.model_validate_json(path.read_text(encoding="utf-8"))


def load_faithfulness_manifest(path: Path) -> FaithfulnessReviewManifest:
    """Load the source-controlled manual faithfulness verdict manifest from JSON."""
    return FaithfulnessReviewManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_quality_gate_policy(path: Path) -> QualityGatePolicy:
    """Load the quality-gate policy from YAML."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"quality gate policy must be a YAML mapping: {path}")
    return QualityGatePolicy.model_validate(payload)


def write_quality_gate_result(path: Path, result: QualityGateResult) -> None:
    """Write a deterministic JSON quality-gate result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _issue(
    code: str,
    kind: GateIssueKind,
    message: str,
    case_id: str | None = None,
) -> GateCheckResult:
    return GateCheckResult(code=code, kind=kind, message=message, case_id=case_id)


def _check_minimum(
    issues: list[GateCheckResult],
    code: str,
    actual: int | float,
    expected: int | float,
) -> None:
    if actual < expected:
        issues.append(
            _issue(
                code,
                "hard",
                f"{code}={actual} is below required minimum {expected}.",
            )
        )


def _check_maximum(
    issues: list[GateCheckResult],
    code: str,
    actual: int | float,
    expected: int | float,
) -> None:
    if actual > expected:
        issues.append(
            _issue(
                code,
                "hard",
                f"{code}={actual} exceeds allowed maximum {expected}.",
            )
        )


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator
