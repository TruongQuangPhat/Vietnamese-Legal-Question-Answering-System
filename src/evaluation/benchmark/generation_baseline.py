"""Metrics for frozen Naive RAG generation baseline reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from src.evaluation.benchmark.enums import ExpectedDecision, RelevanceLevel
from src.evaluation.benchmark.schemas import BenchmarkQuery, EvidenceGroup, EvidenceJudgment

DIRECT_RELEVANCE = {RelevanceLevel.REQUIRED_DIRECT, RelevanceLevel.ALTERNATIVE_DIRECT}


def evaluate_generation_case(
    *,
    query: BenchmarkQuery,
    split: str,
    result: Any,
    retrieved_chunks: list[dict[str, Any]],
    judgments: list[EvidenceJudgment],
    groups: list[EvidenceGroup],
    elapsed_ms: float,
    error: str | None = None,
) -> dict[str, Any]:
    """Build one serializable generation baseline case result.

    Args:
        query: Frozen benchmark query metadata.
        split: Frozen split assignment.
        result: ``RagAnswerResult``-compatible object from the Naive RAG
            pipeline, or ``None`` when a pipeline error occurred before a
            result could be built.
        retrieved_chunks: Dense retrieval result summaries for this query.
        judgments: Benchmark qrels for this query.
        groups: Evidence groups for this query.
        elapsed_ms: Wall-clock generation pipeline latency.
        error: Optional pipeline-level error message.

    Returns:
        JSON-compatible case result.
    """
    selected_chunk_ids = _selected_chunk_ids(result)
    selected_evidence_ids = _selected_evidence_ids(result)
    cited_evidence_ids = _cited_evidence_ids(result)
    direct_chunk_ids = _direct_chunk_ids(judgments)
    coverage = _coverage(selected_chunk_ids, direct_chunk_ids)
    group_coverage = _group_coverage(selected_chunk_ids, groups)
    pipeline_decision = _pipeline_decision(result)
    expected_decision = query.expected_decision.value
    is_answer_allowed = expected_decision == ExpectedDecision.ANSWER_ALLOWED.value
    missing_required_evidence = is_answer_allowed and group_coverage < 1.0
    citation_issues = _citation_issues(result)
    unknown_citation_count = sum(
        1 for issue in citation_issues if issue.get("code") == "unknown_citation_id"
    )
    missing_citation_count = sum(
        1 for issue in citation_issues if issue.get("code") == "missing_citation_id"
    )
    pipeline_answered = pipeline_decision == ExpectedDecision.ANSWER_ALLOWED.value
    citation_id_valid = unknown_citation_count == 0
    citation_coverage_valid = not pipeline_answered or missing_citation_count == 0
    case_status = _case_status(
        expected_decision=expected_decision,
        pipeline_decision=pipeline_decision,
        citation_id_valid=citation_id_valid,
        citation_coverage_valid=citation_coverage_valid,
        missing_required_evidence=missing_required_evidence,
        error=error,
    )
    answer_text = _answer_text(result)
    is_fallback = not pipeline_answered

    return {
        "query_id": query.id,
        "split": split,
        "primary_domain": query.primary_domain.value,
        "question_types": [item.value for item in query.question_types],
        "blocking": query.blocking,
        "expected_decision": expected_decision,
        "pipeline_decision": pipeline_decision,
        "pipeline_answered": pipeline_answered,
        "answer_text": answer_text if pipeline_answered else None,
        "fallback_text": answer_text if is_fallback else None,
        "llm_called": bool(getattr(result, "llm_called", False)) if result is not None else False,
        "model": getattr(result, "model", None) if result is not None else None,
        "provider": getattr(result, "provider", None) if result is not None else None,
        "selected_evidence_ids": selected_evidence_ids,
        "selected_chunk_ids": sorted(selected_chunk_ids),
        "cited_evidence_ids": cited_evidence_ids,
        "retrieved_evidence_ids": [
            item["chunk_id"] for item in retrieved_chunks if item.get("chunk_id")
        ],
        "citation_guard_result": {
            "citation_id_valid": citation_id_valid,
            "citation_coverage_valid": citation_coverage_valid,
            "citation_issue_count": len(citation_issues),
            "unknown_citation_id_count": unknown_citation_count,
            "missing_citation_id_count": missing_citation_count,
            "issues": citation_issues,
        },
        "unsupported_claim_check": {
            "available": False,
            "method": "not_available_without_human_claim_review",
        },
        "unsupported_or_uncited_claim_check": {
            "available": True,
            "method": "citation_id_guard_only",
            "issue_present": bool(citation_issues),
        },
        "missing_required_evidence_check": {
            "missing_required_evidence": missing_required_evidence,
            "selected_required_direct_coverage": coverage,
            "selected_evidence_group_coverage": group_coverage,
        },
        "vietnamese_heuristic": _vietnamese_heuristic(answer_text),
        "fallback_reasons": _optional_list(result, "fallback_reasons"),
        "selection_warnings": _optional_list(result, "selection_warnings"),
        "generation_metadata": _optional_dict(result, "generation_metadata"),
        "selection_metadata": _optional_dict(result, "selection_metadata"),
        "latency_ms": elapsed_ms,
        "error": error,
        "case_status": case_status,
    }


def aggregate_generation_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate frozen generation baseline metrics for a set of case results."""
    expected_answer = [
        case for case in cases if case["expected_decision"] == ExpectedDecision.ANSWER_ALLOWED.value
    ]
    expected_fallback = [
        case
        for case in cases
        if case["expected_decision"] == ExpectedDecision.FALLBACK_REQUIRED.value
    ]
    answered = [case for case in cases if case["pipeline_answered"]]
    fallback = [case for case in cases if not case["pipeline_answered"]]
    latencies = [case["latency_ms"] for case in cases if case["latency_ms"] is not None]
    return {
        "query_count": len(cases),
        "generation_error_count": sum(1 for case in cases if case["error"]),
        "expected_answer_allowed_count": len(expected_answer),
        "expected_fallback_required_count": len(expected_fallback),
        "pipeline_answer_count": len(answered),
        "pipeline_fallback_count": len(fallback),
        "decision_accuracy": _rate(
            cases,
            lambda case: case["pipeline_decision"] == case["expected_decision"],
        ),
        "answer_allowed_answer_rate": _rate(
            expected_answer,
            lambda case: case["pipeline_answered"],
        ),
        "fallback_required_fallback_rate": _rate(
            expected_fallback,
            lambda case: not case["pipeline_answered"],
        ),
        "citation_id_validity_rate": _rate(
            answered,
            lambda case: case["citation_guard_result"]["citation_id_valid"],
        ),
        "selected_required_direct_coverage": _mean(
            case["missing_required_evidence_check"]["selected_required_direct_coverage"]
            for case in expected_answer
        ),
        "selected_evidence_group_coverage": _mean(
            case["missing_required_evidence_check"]["selected_evidence_group_coverage"]
            for case in expected_answer
        ),
        "missing_required_evidence_rate": _rate(
            expected_answer,
            lambda case: case["missing_required_evidence_check"]["missing_required_evidence"],
        ),
        "unsupported_or_uncited_claim_rate": _rate(
            answered,
            lambda case: case["unsupported_or_uncited_claim_check"]["issue_present"],
        ),
        "unsupported_or_uncited_claim_check": "citation_id_guard_only",
        "case_pass_rate": _rate(cases, lambda case: case["case_status"] == "pass"),
        "case_partial_rate": _rate(cases, lambda case: case["case_status"] == "partial"),
        "case_fail_rate": _rate(cases, lambda case: case["case_status"] == "fail"),
        "mean_latency_ms": _mean(latencies),
        "fallback_behavior": {
            "fallback_cases": len(fallback),
            "fallback_without_llm_count": sum(1 for case in fallback if not case["llm_called"]),
            "fallback_with_citations_count": sum(
                1 for case in fallback if case["cited_evidence_ids"]
            ),
        },
    }


def build_generation_breakdowns(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate generation metrics by split, domain, decision, and question type."""
    return {
        "split": _breakdown(cases, lambda case: [case["split"]]),
        "primary_domain": _breakdown(cases, lambda case: [case["primary_domain"]]),
        "expected_decision": _breakdown(cases, lambda case: [case["expected_decision"]]),
        "question_types": _breakdown(cases, lambda case: case["question_types"]),
        "blocking": _breakdown(cases, lambda case: [str(bool(case.get("blocking", False)))]),
    }


def _coverage(selected: set[str], required: set[str]) -> float:
    if not required:
        return 0.0
    return len(selected & required) / len(required)


def _group_coverage(selected: set[str], groups: list[EvidenceGroup]) -> float:
    required = [group for group in groups if group.requirement.value == "required"]
    if not required:
        return 0.0
    hits = 0
    for group in required:
        if selected & set(group.acceptable_chunk_ids):
            hits += 1
    return hits / len(required)


def _direct_chunk_ids(judgments: list[EvidenceJudgment]) -> set[str]:
    return {judgment.chunk_id for judgment in judgments if judgment.relevance in DIRECT_RELEVANCE}


def _selected_chunk_ids(result: Any) -> set[str]:
    if result is None:
        return set()
    return {item.chunk_id for item in getattr(result, "used_evidence", []) if item.chunk_id}


def _selected_evidence_ids(result: Any) -> list[str]:
    if result is None:
        return []
    return [item.evidence_id for item in getattr(result, "used_evidence", [])]


def _cited_evidence_ids(result: Any) -> list[str]:
    if result is None:
        return []
    return [item.evidence_id for item in getattr(result, "citations", [])]


def _citation_issues(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    return [issue.model_dump(mode="json") for issue in getattr(result, "citation_issues", [])]


def _optional_list(result: Any, field_name: str) -> list[Any]:
    if result is None:
        return []
    return list(getattr(result, field_name, None) or [])


def _optional_dict(result: Any, field_name: str) -> dict[str, Any]:
    if result is None:
        return {}
    payload = getattr(result, field_name, None) or {}
    return payload if isinstance(payload, dict) else {}


def _pipeline_decision(result: Any) -> str:
    if result is None:
        return "error"
    decision = getattr(result, "decision", None)
    return getattr(decision, "value", str(decision))


def _answer_text(result: Any) -> str:
    if result is None:
        return ""
    return str(getattr(result, "answer", "") or "")


def _vietnamese_heuristic(text: str) -> dict[str, Any]:
    has_diacritic = any(char in text.lower() for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặ")
    has_legal_marker = any(marker in text.lower() for marker in ("điều", "khoản", "pháp luật"))
    return {
        "available": True,
        "likely_vietnamese": bool(has_diacritic or has_legal_marker),
    }


def _case_status(
    *,
    expected_decision: str,
    pipeline_decision: str,
    citation_id_valid: bool,
    citation_coverage_valid: bool,
    missing_required_evidence: bool,
    error: str | None,
) -> str:
    if error or pipeline_decision != expected_decision:
        return "fail"
    if not citation_id_valid or not citation_coverage_valid or missing_required_evidence:
        return "partial"
    return "pass"


def _breakdown(
    cases: list[dict[str, Any]],
    labels_getter: Any,
) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        for label in labels_getter(case):
            buckets[str(label)].append(case)
    return {
        label: aggregate_generation_metrics(bucket) for label, bucket in sorted(buckets.items())
    }


def _rate(cases: list[dict[str, Any]], predicate: Any) -> float:
    if not cases:
        return 0.0
    return sum(1 for case in cases if predicate(case)) / len(cases)


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def status_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    """Return pass/partial/fail counts for report summaries."""
    return dict(Counter(case["case_status"] for case in cases))
