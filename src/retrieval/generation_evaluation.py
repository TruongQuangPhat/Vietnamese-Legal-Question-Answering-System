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

from src.retrieval.generation import FALLBACK_ANSWER_VI, RagAnswerResult, UsedEvidence
from src.retrieval.selection import AnswerabilityDecision

GenerationEvalLanguage = Literal["vi"]
ValidationSeverity = Literal["warning", "error"]
GenerationEvalStatus = Literal[
    "expanded_generation_eval_passed",
    "expanded_generation_eval_partial",
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
_ANSWER_PREVIEW_LIMIT = 2000
DEFAULT_EVIDENCE_PREVIEW_CHARS = 500
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


class EvidencePreview(BaseModel):
    """Short, traceable preview of selected directly citable evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    packet_id: str | None = None
    chunk_id: str | None = None
    citation: str | None = None
    law_id: str | None = None
    law_title: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    source_url: str | None = None
    citation_scope: str | None = None
    safety_level: str | None = None
    is_directly_citable: bool | None = None
    text_preview: str | None = None
    text_preview_truncated: bool = False
    auxiliary_context_present: bool = False
    parent_context_included_in_prompt: bool = False


class GenerationEvalQuery(BaseModel):
    """One manual query and deterministic generation expectations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    allowed_decisions: list[AnswerabilityDecision] = Field(..., min_length=1)
    expected_llm_called: bool | None
    requires_citation_ids: bool
    expected_language: GenerationEvalLanguage = "vi"
    must_not_contain: list[str] = Field(default_factory=list)
    manual_query_id: str | None = None
    manual_review_required: bool = False
    blocking: bool = True
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
    expected_llm_called: bool | None
    llm_called: bool
    llm_call_policy_passed: bool
    fallback_policy_passed: bool
    requires_citation_ids: bool
    citation_id_coverage_applicable: bool
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
    selected_evidence_count: int = Field(..., ge=0)
    caution_selected_count: int = Field(..., ge=0)
    all_selected_evidence_caution: bool
    manual_review_required: bool
    blocking: bool
    evidence_previews: list[EvidencePreview] = Field(default_factory=list)
    cited_evidence_previews: list[EvidencePreview] = Field(default_factory=list)
    all_cited_ids_have_preview: bool = True
    evidence_preview_count: int = Field(0, ge=0)
    cited_evidence_preview_count: int = Field(0, ge=0)
    evidence_preview_missing_count: int = Field(0, ge=0)
    caution_evidence_ids: list[str] = Field(default_factory=list)
    all_caution_evidence_ids: list[str] = Field(default_factory=list)
    validation_issues: list[GenerationValidationIssue] = Field(default_factory=list)
    answer_preview: str = ""
    answer_preview_truncated: bool = False
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
    blocking_case_count: int = Field(..., ge=0)
    non_blocking_case_count: int = Field(..., ge=0)
    blocking_failed_cases: int = Field(..., ge=0)
    manual_review_required_count: int = Field(..., ge=0)
    decision_pass_rate: float = Field(..., ge=0.0, le=1.0)
    llm_call_policy_pass_rate: float = Field(..., ge=0.0, le=1.0)
    citation_id_coverage_rate: float = Field(..., ge=0.0, le=1.0)
    unknown_citation_id_count: int = Field(..., ge=0)
    missing_citation_id_count: int = Field(..., ge=0)
    fallback_policy_pass_rate: float = Field(..., ge=0.0, le=1.0)
    vietnamese_language_pass_rate: float = Field(..., ge=0.0, le=1.0)
    forbidden_phrase_failures: int = Field(..., ge=0)
    secret_leak_failures: int = Field(..., ge=0)
    total_caution_selected_count: int = Field(..., ge=0)
    cases_with_all_caution_evidence: int = Field(..., ge=0)
    selection_warning_count: int = Field(..., ge=0)
    evidence_preview_case_count: int = Field(0, ge=0)
    evidence_preview_total_count: int = Field(0, ge=0)
    cited_evidence_preview_total_count: int = Field(0, ge=0)
    evidence_preview_missing_count: int = Field(0, ge=0)
    all_cited_ids_have_preview_rate: float = Field(1.0, ge=0.0, le=1.0)
    cases_missing_evidence_preview: list[str] = Field(default_factory=list)
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
    *,
    include_evidence_preview: bool = False,
    evidence_preview_chars: int = DEFAULT_EVIDENCE_PREVIEW_CHARS,
) -> GenerationEvalCaseResult:
    """Validate one existing Naive RAG result without external calls."""
    if evidence_preview_chars <= 0:
        raise ValueError("evidence_preview_chars must be positive")
    issues: list[GenerationValidationIssue] = []

    decision_passed = result.decision in case.allowed_decisions
    if not decision_passed:
        issues.append(
            _issue("decision_not_allowed", "actual decision is outside allowed_decisions")
        )

    llm_call_policy_passed = _llm_call_policy_passed(case, result)
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

    selected_evidence_count = _metadata_count(
        result.selection_metadata,
        "selected_count",
    )
    caution_selected_count = _metadata_count(
        result.selection_metadata,
        "caution_selected_count",
    )
    all_selected_evidence_caution = (
        selected_evidence_count > 0 and caution_selected_count == selected_evidence_count
    )
    citation_id_coverage_applicable = (
        case.requires_citation_ids and result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    )
    evidence_previews = (
        [
            build_evidence_preview(item, max_chars=evidence_preview_chars)
            for item in result.used_evidence
        ]
        if include_evidence_preview
        else []
    )
    preview_by_id = {preview.evidence_id: preview for preview in evidence_previews}
    cited_ids = _citation_ids(result.answer)
    cited_evidence_previews = [
        preview_by_id[evidence_id] for evidence_id in cited_ids if evidence_id in preview_by_id
    ]
    evidence_preview_missing_count = sum(
        evidence_id not in preview_by_id for evidence_id in cited_ids
    )
    caution_evidence_ids = [
        preview.evidence_id for preview in evidence_previews if preview.safety_level == "caution"
    ]
    all_caution_evidence_ids = (
        caution_evidence_ids
        if evidence_previews and len(caution_evidence_ids) == len(evidence_previews)
        else []
    )
    answer_preview, answer_preview_truncated = build_text_preview(
        result.answer,
        max_chars=_ANSWER_PREVIEW_LIMIT,
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
        citation_id_coverage_applicable=citation_id_coverage_applicable,
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
        selected_evidence_count=selected_evidence_count,
        caution_selected_count=caution_selected_count,
        all_selected_evidence_caution=all_selected_evidence_caution,
        manual_review_required=case.manual_review_required,
        blocking=case.blocking,
        evidence_previews=evidence_previews,
        cited_evidence_previews=cited_evidence_previews,
        all_cited_ids_have_preview=evidence_preview_missing_count == 0,
        evidence_preview_count=len(evidence_previews),
        cited_evidence_preview_count=len(cited_evidence_previews),
        evidence_preview_missing_count=evidence_preview_missing_count,
        caution_evidence_ids=caution_evidence_ids,
        all_caution_evidence_ids=all_caution_evidence_ids,
        validation_issues=issues,
        answer_preview=answer_preview,
        answer_preview_truncated=answer_preview_truncated,
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
    citation_cases = [case for case in case_list if case.citation_id_coverage_applicable]
    fallback_cases = [
        case for case in case_list if case.decision != AnswerabilityDecision.ANSWER_ALLOWED
    ]
    blocking_cases = [case for case in case_list if case.blocking]
    cited_preview_cases = [
        case
        for case in case_list
        if case.decision == AnswerabilityDecision.ANSWER_ALLOWED
        and (case.cited_evidence_preview_count or case.evidence_preview_missing_count)
    ]
    return GenerationEvalReport(
        status=(
            "expanded_generation_eval_passed"
            if passed_cases == total
            else "expanded_generation_eval_partial"
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
        blocking_case_count=len(blocking_cases),
        non_blocking_case_count=total - len(blocking_cases),
        blocking_failed_cases=sum(not case.passed for case in blocking_cases),
        manual_review_required_count=sum(case.manual_review_required for case in case_list),
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
        total_caution_selected_count=sum(case.caution_selected_count for case in case_list),
        cases_with_all_caution_evidence=sum(
            case.all_selected_evidence_caution for case in case_list
        ),
        selection_warning_count=sum(len(case.selection_warnings) for case in case_list),
        evidence_preview_case_count=sum(bool(case.evidence_previews) for case in case_list),
        evidence_preview_total_count=sum(case.evidence_preview_count for case in case_list),
        cited_evidence_preview_total_count=sum(
            case.cited_evidence_preview_count for case in case_list
        ),
        evidence_preview_missing_count=sum(
            case.evidence_preview_missing_count for case in case_list
        ),
        all_cited_ids_have_preview_rate=_rate(
            sum(case.all_cited_ids_have_preview for case in cited_preview_cases),
            len(cited_preview_cases),
        ),
        cases_missing_evidence_preview=[
            case.id for case in case_list if case.evidence_preview_missing_count
        ],
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


def redact_secret_like_text(text: str) -> str:
    """Redact provider-authentication markers from report preview text."""
    redacted = text
    for _, pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def build_text_preview(text: str, *, max_chars: int) -> tuple[str, bool]:
    """Build a redacted bounded preview and return its truncation state."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    redacted = redact_secret_like_text(text)
    if len(redacted) <= max_chars:
        return redacted, False
    return f"{redacted[:max_chars]}...", True


def redact_answer_preview(answer: str) -> str:
    """Build a bounded answer preview with secret-like content redacted."""
    return build_text_preview(answer, max_chars=_ANSWER_PREVIEW_LIMIT)[0]


def build_evidence_preview(
    evidence: UsedEvidence,
    *,
    max_chars: int = DEFAULT_EVIDENCE_PREVIEW_CHARS,
) -> EvidencePreview:
    """Build a safe preview from selected child evidence only.

    Auxiliary parent context is represented only by booleans and is never
    copied into ``text_preview``.
    """
    text_preview: str | None = None
    text_preview_truncated = False
    if evidence.safe_citable_text:
        text_preview, text_preview_truncated = build_text_preview(
            evidence.safe_citable_text,
            max_chars=max_chars,
        )
    return EvidencePreview(
        evidence_id=evidence.evidence_id,
        packet_id=evidence.packet_id,
        chunk_id=evidence.chunk_id,
        citation=evidence.citation,
        law_id=evidence.law_id,
        law_title=evidence.law_title,
        article_number=evidence.article_number,
        clause_number=evidence.clause_number,
        point_label=evidence.point_label,
        source_url=evidence.source_url,
        citation_scope=evidence.citation_scope,
        safety_level=evidence.safety_level,
        is_directly_citable=evidence.is_directly_citable,
        text_preview=text_preview,
        text_preview_truncated=text_preview_truncated,
        auxiliary_context_present=evidence.auxiliary_context_present,
        parent_context_included_in_prompt=evidence.parent_context_included_in_prompt,
    )


def _fallback_policy_passed(
    case: GenerationEvalQuery,
    result: RagAnswerResult,
) -> bool:
    del case
    if result.decision == AnswerabilityDecision.ANSWER_ALLOWED:
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
    if result.decision != AnswerabilityDecision.ANSWER_ALLOWED:
        return not result.citations
    if not case.requires_citation_ids:
        return True
    return bool(_CITATION_ID_RE.search(result.answer)) and bool(result.citations)


def _llm_call_policy_passed(
    case: GenerationEvalQuery,
    result: RagAnswerResult,
) -> bool:
    decision_requires_llm = result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    if result.llm_called != decision_requires_llm:
        return False
    return case.expected_llm_called is None or result.llm_called == case.expected_llm_called


def _metadata_count(metadata: dict[str, object], key: str) -> int:
    value = metadata.get(key, 0)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _citation_issue_count(result: RagAnswerResult, code: str) -> int:
    return sum(issue.code == code for issue in result.citation_issues)


def _citation_ids(text: str) -> list[str]:
    return list(dict.fromkeys(match[1:-1] for match in _CITATION_ID_RE.findall(text)))


def _issue(code: str, message: str) -> GenerationValidationIssue:
    return GenerationValidationIssue(code=code, severity="error", message=message)


def _rate(passed: int, total: int) -> float:
    return 1.0 if total == 0 else passed / total
