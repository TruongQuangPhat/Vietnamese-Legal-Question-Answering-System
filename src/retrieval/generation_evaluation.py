"""Deterministic validation for Phase 9C Naive RAG generation results.

The checks cover decision policy, LLM call policy, citation-ID integrity,
fallback behavior, likely Vietnamese output, forbidden phrases, and secret-like
leakage. They do not measure semantic faithfulness or legal correctness.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.retrieval.generation import FALLBACK_ANSWER_VI, RagAnswerResult
from src.retrieval.selection import AnswerabilityDecision

GenerationEvalLanguage = Literal["vi"]
ValidationSeverity = Literal["warning", "error"]
GenerationEvalStatus = Literal[
    "validated_generation_eval_passed",
    "validated_generation_eval_partial",
]

_VIETNAMESE_DIACRITIC_RE = re.compile(
    r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồỗộớờởỡợ"
    r"úùủũụứừửữựýỳỷỹỵ]",
    re.IGNORECASE,
)
_VIETNAMESE_LEGAL_TERMS = (
    "pháp luật",
    "điều ",
    "khoản ",
    "điểm ",
    "quy định",
    "căn cứ",
    "bảo hiểm",
    "người lao động",
    "quyền dân sự",
)
_CITATION_ID_RE = re.compile(r"\[E[1-9][0-9]*\]")
_ANSWER_PREVIEW_LIMIT = 600
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openrouter-key-name", re.compile(r"OPENROUTER_API_KEY", re.IGNORECASE)),
    ("authorization-marker", re.compile(r"\bAuthorization\b", re.IGNORECASE)),
    ("bearer-token-marker", re.compile(r"\bBearer\b", re.IGNORECASE)),
    ("openrouter-token-shape", re.compile(r"\bsk-or-[A-Za-z0-9_.-]*", re.IGNORECASE)),
    ("secret-token-shape", re.compile(r"\bsk-[A-Za-z0-9_.-]+", re.IGNORECASE)),
    ("api-key-marker", re.compile(r"\bapi_key\b", re.IGNORECASE)),
    ("access-token-marker", re.compile(r"\baccess_token\b", re.IGNORECASE)),
)


class GenerationValidationIssue(BaseModel):
    """One deterministic Phase 9C validation issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(..., min_length=1)
    severity: ValidationSeverity
    message: str = Field(..., min_length=1)


class GenerationEvalQuery(BaseModel):
    """One manual query and deterministic generation expectations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    allowed_decisions: list[AnswerabilityDecision] = Field(..., min_length=1)
    expected_llm_called: bool
    requires_citation_ids: bool
    expected_language: GenerationEvalLanguage = "vi"
    must_not_contain: list[str] = Field(default_factory=list)
    manual_query_id: str | None = None
    notes: str | None = None

    @field_validator("id", "query", "manual_query_id", "notes")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim text fields and reject blank values when present."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be blank")
        return normalized

    @field_validator("allowed_decisions")
    @classmethod
    def require_unique_decisions(
        cls,
        values: list[AnswerabilityDecision],
    ) -> list[AnswerabilityDecision]:
        """Reject duplicate allowed decisions."""
        if len(values) != len(set(values)):
            raise ValueError("allowed_decisions must not contain duplicates")
        return values

    @field_validator("must_not_contain")
    @classmethod
    def normalize_forbidden_phrases(cls, values: list[str]) -> list[str]:
        """Normalize forbidden phrases while preserving declaration order."""
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("must_not_contain phrases must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_llm_expectation(self) -> GenerationEvalQuery:
        """Require an answer-allowed outcome when an LLM call is expected."""
        if (
            self.expected_llm_called
            and AnswerabilityDecision.ANSWER_ALLOWED not in self.allowed_decisions
        ):
            raise ValueError("expected_llm_called requires answer_allowed")
        return self


class GenerationEvalCaseResult(BaseModel):
    """Deterministic validation result for one generated answer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    query: str
    passed: bool
    allowed_decisions: list[AnswerabilityDecision]
    decision: AnswerabilityDecision
    decision_passed: bool
    expected_llm_called: bool
    llm_called: bool
    llm_call_policy_passed: bool
    fallback_policy_passed: bool
    requires_citation_ids: bool
    citation_id_coverage_passed: bool
    citation_count: int = Field(..., ge=0)
    citation_issue_count: int = Field(..., ge=0)
    unknown_citation_id_count: int = Field(..., ge=0)
    missing_citation_id_count: int = Field(..., ge=0)
    vietnamese_language_passed: bool
    forbidden_phrase_failures: list[str] = Field(default_factory=list)
    secret_leak_failures: list[str] = Field(default_factory=list)
    fallback_reasons: list[str] = Field(default_factory=list)
    selection_warnings: list[str] = Field(default_factory=list)
    validation_issues: list[GenerationValidationIssue] = Field(default_factory=list)
    answer_preview: str = ""
    model: str | None = None
    provider: str | None = None
    pipeline_error_count: int = Field(..., ge=0)
    notes: str | None = None


class GenerationEvalReport(BaseModel):
    """Comparable JSON report for a Phase 9C generation evaluation run."""

    model_config = ConfigDict(extra="forbid")

    report_type: str = "naive_rag_generation_evaluation"
    run_type: str = "manual_generation_eval"
    pipeline_stage: str = "retrieval_naive_rag_generation"
    status: GenerationEvalStatus
    started_at: str
    finished_at: str
    dataset_path: str
    collection_name: str
    vector_name: str
    top_k: int = Field(..., gt=0)
    provider: str
    model: str
    total_cases: int = Field(..., ge=0)
    passed_cases: int = Field(..., ge=0)
    failed_cases: int = Field(..., ge=0)
    decision_pass_rate: float = Field(..., ge=0.0, le=1.0)
    llm_call_policy_pass_rate: float = Field(..., ge=0.0, le=1.0)
    citation_id_coverage_rate: float = Field(..., ge=0.0, le=1.0)
    unknown_citation_id_count: int = Field(..., ge=0)
    missing_citation_id_count: int = Field(..., ge=0)
    fallback_policy_pass_rate: float = Field(..., ge=0.0, le=1.0)
    vietnamese_language_pass_rate: float = Field(..., ge=0.0, le=1.0)
    forbidden_phrase_failures: int = Field(..., ge=0)
    secret_leak_failures: int = Field(..., ge=0)
    cases: list[GenerationEvalCaseResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def load_generation_eval_queries(path: Path) -> list[GenerationEvalQuery]:
    """Load and validate Phase 9C manual generation queries from JSONL."""
    records: list[GenerationEvalQuery] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            records.append(GenerationEvalQuery.model_validate(payload))
    if not records:
        raise ValueError(f"generation evaluation dataset is empty: {path}")
    return records


def validate_generation_result(
    case: GenerationEvalQuery,
    result: RagAnswerResult,
) -> GenerationEvalCaseResult:
    """Validate one existing Naive RAG result without external calls."""
    issues: list[GenerationValidationIssue] = []

    decision_passed = result.decision in case.allowed_decisions
    if not decision_passed:
        issues.append(
            _issue("decision_not_allowed", "actual decision is outside allowed_decisions")
        )

    llm_call_policy_passed = result.llm_called == case.expected_llm_called
    if result.decision != AnswerabilityDecision.ANSWER_ALLOWED and result.llm_called:
        llm_call_policy_passed = False
    if not llm_call_policy_passed:
        issues.append(
            _issue("llm_call_policy_failed", "LLM call did not follow the expected policy")
        )

    fallback_policy_passed = _fallback_policy_passed(case, result)
    if not fallback_policy_passed:
        issues.append(
            _issue(
                "fallback_policy_failed",
                "fallback/review output must avoid LLM calls, citations, and generated claims",
            )
        )

    unknown_count = _citation_issue_count(result, "unknown_citation_id")
    missing_count = _citation_issue_count(result, "missing_citation_id")
    citation_id_coverage_passed = _citation_policy_passed(
        case,
        result,
        unknown_count=unknown_count,
        missing_count=missing_count,
    )
    if not citation_id_coverage_passed:
        issues.append(
            _issue(
                "citation_id_coverage_failed",
                "required generated citation IDs are missing or invalid",
            )
        )

    vietnamese_language_passed = case.expected_language != "vi" or is_likely_vietnamese(
        result.answer
    )
    if not vietnamese_language_passed:
        issues.append(
            _issue(
                "language_not_likely_vietnamese",
                "answer did not pass the deterministic Vietnamese-language heuristic",
            )
        )

    forbidden_failures = find_forbidden_phrases(result.answer, case.must_not_contain)
    if forbidden_failures:
        issues.append(
            _issue(
                "forbidden_phrase_detected",
                "answer contains one or more forbidden phrases",
            )
        )

    secret_failures = find_secret_leak_labels(result.answer)
    if secret_failures:
        issues.append(
            _issue(
                "secret_like_content_detected",
                "answer contains secret-like or provider-authentication content",
            )
        )

    if result.errors:
        issues.append(
            _issue(
                "pipeline_errors_present",
                "Naive RAG result contains one or more pipeline errors",
            )
        )

    passed = not any(issue.severity == "error" for issue in issues)
    return GenerationEvalCaseResult(
        id=case.id,
        query=case.query,
        passed=passed,
        allowed_decisions=case.allowed_decisions,
        decision=result.decision,
        decision_passed=decision_passed,
        expected_llm_called=case.expected_llm_called,
        llm_called=result.llm_called,
        llm_call_policy_passed=llm_call_policy_passed,
        fallback_policy_passed=fallback_policy_passed,
        requires_citation_ids=case.requires_citation_ids,
        citation_id_coverage_passed=citation_id_coverage_passed,
        citation_count=len(result.citations),
        citation_issue_count=len(result.citation_issues),
        unknown_citation_id_count=unknown_count,
        missing_citation_id_count=missing_count,
        vietnamese_language_passed=vietnamese_language_passed,
        forbidden_phrase_failures=forbidden_failures,
        secret_leak_failures=secret_failures,
        fallback_reasons=result.fallback_reasons,
        selection_warnings=result.selection_warnings,
        validation_issues=issues,
        answer_preview=redact_answer_preview(result.answer),
        model=result.model,
        provider=result.provider,
        pipeline_error_count=len(result.errors),
        notes=case.notes,
    )


def build_generation_eval_report(
    *,
    cases: Sequence[GenerationEvalCaseResult],
    started_at: datetime,
    dataset_path: Path,
    collection_name: str,
    vector_name: str,
    top_k: int,
    provider: str,
    model: str,
) -> GenerationEvalReport:
    """Aggregate deterministic case results into a comparable report."""
    case_list = list(cases)
    if not case_list:
        raise ValueError("generation evaluation requires at least one case")
    total = len(case_list)
    passed_cases = sum(case.passed for case in case_list)
    citation_cases = [case for case in case_list if case.requires_citation_ids]
    fallback_cases = [case for case in case_list if not case.expected_llm_called]
    return GenerationEvalReport(
        status=(
            "validated_generation_eval_passed"
            if passed_cases == total
            else "validated_generation_eval_partial"
        ),
        started_at=started_at.astimezone(UTC).isoformat(),
        finished_at=datetime.now(UTC).isoformat(),
        dataset_path=str(dataset_path),
        collection_name=collection_name,
        vector_name=vector_name,
        top_k=top_k,
        provider=provider,
        model=model,
        total_cases=total,
        passed_cases=passed_cases,
        failed_cases=total - passed_cases,
        decision_pass_rate=_rate(sum(case.decision_passed for case in case_list), total),
        llm_call_policy_pass_rate=_rate(
            sum(case.llm_call_policy_passed for case in case_list),
            total,
        ),
        citation_id_coverage_rate=_rate(
            sum(case.citation_id_coverage_passed for case in citation_cases),
            len(citation_cases),
        ),
        unknown_citation_id_count=sum(case.unknown_citation_id_count for case in case_list),
        missing_citation_id_count=sum(case.missing_citation_id_count for case in case_list),
        fallback_policy_pass_rate=_rate(
            sum(case.fallback_policy_passed for case in fallback_cases),
            len(fallback_cases),
        ),
        vietnamese_language_pass_rate=_rate(
            sum(case.vietnamese_language_passed for case in case_list),
            total,
        ),
        forbidden_phrase_failures=sum(len(case.forbidden_phrase_failures) for case in case_list),
        secret_leak_failures=sum(len(case.secret_leak_failures) for case in case_list),
        cases=case_list,
        notes=[
            "citation_id_coverage_rate validates [E#] ID integrity only",
            "semantic faithfulness and legal correctness require separate review",
        ],
    )


def is_likely_vietnamese(answer: str) -> bool:
    """Return whether text passes a small deterministic Vietnamese heuristic."""
    normalized = answer.strip().casefold()
    if not normalized:
        return False
    return bool(_VIETNAMESE_DIACRITIC_RE.search(normalized)) or any(
        term in normalized for term in _VIETNAMESE_LEGAL_TERMS
    )


def find_forbidden_phrases(answer: str, phrases: Sequence[str]) -> list[str]:
    """Return forbidden phrases found case-insensitively in an answer."""
    normalized = answer.casefold()
    return [phrase for phrase in phrases if phrase.casefold() in normalized]


def find_secret_leak_labels(text: str) -> list[str]:
    """Return safe labels for secret-like markers found in text."""
    return [label for label, pattern in _SECRET_PATTERNS if pattern.search(text)]


def redact_answer_preview(answer: str) -> str:
    """Build a bounded answer preview with secret-like content redacted."""
    redacted = answer
    for _, pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    if len(redacted) <= _ANSWER_PREVIEW_LIMIT:
        return redacted
    return f"{redacted[:_ANSWER_PREVIEW_LIMIT]}..."


def _fallback_policy_passed(
    case: GenerationEvalQuery,
    result: RagAnswerResult,
) -> bool:
    if case.expected_llm_called:
        return True
    return (
        result.decision != AnswerabilityDecision.ANSWER_ALLOWED
        and not result.llm_called
        and not result.citations
        and result.answer == FALLBACK_ANSWER_VI
    )


def _citation_policy_passed(
    case: GenerationEvalQuery,
    result: RagAnswerResult,
    *,
    unknown_count: int,
    missing_count: int,
) -> bool:
    if unknown_count or missing_count:
        return False
    if not case.requires_citation_ids:
        return True
    return bool(_CITATION_ID_RE.search(result.answer)) and bool(result.citations)


def _citation_issue_count(result: RagAnswerResult, code: str) -> int:
    return sum(issue.code == code for issue in result.citation_issues)


def _issue(code: str, message: str) -> GenerationValidationIssue:
    return GenerationValidationIssue(code=code, severity="error", message=message)


def _rate(passed: int, total: int) -> float:
    return 1.0 if total == 0 else passed / total
