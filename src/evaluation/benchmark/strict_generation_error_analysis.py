"""Offline error analysis for strict generation evaluation reports."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.indexing.official_artifacts import write_json_atomic

WORKFLOW_NAME = "strict_generation_error_analysis"
SOURCE_WORKFLOW_NAME = "strict_generation_evaluation"
RETRIEVAL_STRATEGY = "coverage_aware_quota"

ERROR_BUCKETS = (
    "expected_answer_allowed_but_pipeline_fallback",
    "expected_fallback_required_but_pipeline_answered",
    "partial_answer_missing_required_evidence",
    "parent_context_only_fallback",
    "all_selected_evidence_caution_fallback",
    "selected_evidence_empty",
    "selected_evidence_present_but_required_evidence_group_coverage_incomplete",
    "citation_guard_fallback",
    "provider_or_generation_error",
    "retrieval_error",
)


@dataclass(frozen=True)
class StrictGenerationErrorAnalysisPaths:
    """Input strict-generation reports and output directory for offline analysis."""

    case_results: Path
    metrics_all: Path
    breakdowns: Path
    comparison: Path
    output_dir: Path


class StrictGenerationErrorAnalysisError(RuntimeError):
    """Raised when strict generation error analysis cannot run safely."""


def run_strict_generation_error_analysis(
    paths: StrictGenerationErrorAnalysisPaths,
) -> dict[str, Any]:
    """Analyze strict generation case results and write offline reports.

    Args:
        paths: Required input reports and output destination.

    Returns:
        JSON-compatible summary payload containing bucket, domain, question
        type, and recommendation data.

    Raises:
        StrictGenerationErrorAnalysisError: If required inputs are missing or
            malformed.
    """
    cases = load_case_results(paths.case_results)
    metrics = load_json_object(paths.metrics_all)
    breakdowns = load_json_object(paths.breakdowns)
    comparison = load_json_object(paths.comparison)
    analysis = build_strict_generation_error_analysis(
        cases=cases,
        metrics=metrics,
        breakdowns=breakdowns,
        comparison=comparison,
    )
    write_strict_generation_error_analysis(paths.output_dir, analysis)
    return analysis


def build_strict_generation_error_analysis(
    *,
    cases: list[dict[str, Any]],
    metrics: dict[str, Any],
    breakdowns: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic error analysis without external services.

    Development cases are analyzed first and drive next-action guidance.
    Held-out test cases are summarized separately for reporting only.
    """
    if not cases:
        raise StrictGenerationErrorAnalysisError("case results must not be empty")
    development_cases = [case for case in cases if case.get("split") == "development"]
    held_out_cases = [case for case in cases if case.get("split") == "held_out_test"]
    bucketed_all = build_error_buckets(cases)
    bucketed_development = build_error_buckets(development_cases)
    domain_summary = build_group_summary(cases, "primary_domain")
    question_type_summary = build_question_type_summary(cases)
    top_failures = select_top_failure_cases(cases)
    diagnosis = diagnose_bottleneck(bucketed_development, development_cases)
    return {
        "report_type": WORKFLOW_NAME,
        "workflow_name": WORKFLOW_NAME,
        "source_workflow_name": SOURCE_WORKFLOW_NAME,
        "retrieval_strategy": RETRIEVAL_STRATEGY,
        "development_analyzed_first": True,
        "held_out_test_reporting_only": True,
        "input_summary": {
            "case_count": len(cases),
            "development_case_count": len(development_cases),
            "held_out_test_case_count": len(held_out_cases),
            "metrics_query_count": metrics.get("query_count"),
            "comparison_systems": sorted((comparison.get("systems") or {}).keys()),
            "breakdown_dimensions": sorted(breakdowns.keys()),
        },
        "error_buckets": bucketed_all,
        "development_error_buckets": bucketed_development,
        "domain_error_summary": domain_summary,
        "question_type_error_summary": question_type_summary,
        "top_failing_domains": top_group_summaries(domain_summary),
        "top_failing_question_types": top_group_summaries(question_type_summary),
        "top_failure_cases": top_failures,
        "bottleneck_diagnosis": diagnosis,
        "recommended_next_actions": recommend_next_actions(diagnosis),
    }


def build_error_buckets(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Bucket cases into deterministic strict-generation failure categories."""
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in ERROR_BUCKETS}
    for case in cases:
        for bucket_name in classify_case(case):
            buckets[bucket_name].append(_case_reference(case, include_reasons=True))
    return {
        name: {
            "count": len(items),
            "case_ids": [item["query_id"] for item in items],
            "cases": items,
        }
        for name, items in buckets.items()
    }


def classify_case(case: dict[str, Any]) -> list[str]:
    """Return all error buckets matched by one strict-generation case."""
    buckets: list[str] = []
    expected = str(case.get("expected_decision") or "")
    answered = bool(case.get("pipeline_answered"))
    fallback_reasons = set(_string_list(case.get("fallback_reasons")))
    warnings = set(_string_list(case.get("selection_warnings")))
    selected_ids = _string_list(case.get("selected_evidence_ids"))
    group_coverage = _group_coverage(case)
    citation_guard = case.get("citation_guard_result") or {}
    citation_invalid = (
        bool((citation_guard or {}).get("citation_issue_count", 0))
        or (citation_guard or {}).get("citation_id_valid") is False
        or (citation_guard or {}).get("citation_coverage_valid") is False
    )

    if expected == "answer_allowed" and not answered:
        buckets.append("expected_answer_allowed_but_pipeline_fallback")
    if expected == "fallback_required" and answered:
        buckets.append("expected_fallback_required_but_pipeline_answered")
    if case.get("case_status") == "partial" and _missing_required_evidence(case):
        buckets.append("partial_answer_missing_required_evidence")
    if not answered and _contains_token(fallback_reasons, "parent_context"):
        buckets.append("parent_context_only_fallback")
    if not answered and (
        "all_selected_evidence_caution" in fallback_reasons
        or "all_selected_evidence_caution" in warnings
    ):
        buckets.append("all_selected_evidence_caution_fallback")
    if not selected_ids:
        buckets.append("selected_evidence_empty")
    if selected_ids and expected == "answer_allowed" and group_coverage < 1.0:
        buckets.append("selected_evidence_present_but_required_evidence_group_coverage_incomplete")
    if not answered and citation_invalid:
        buckets.append("citation_guard_fallback")
    if case.get("generation_error"):
        buckets.append("provider_or_generation_error")
    if case.get("retrieval_error"):
        buckets.append("retrieval_error")
    return buckets


def build_group_summary(cases: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
    """Summarize failures and bucket counts for a single-valued case field."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[str(case.get(field_name) or "unknown")].append(case)
    return {
        label: summarize_cases(items)
        for label, items in sorted(grouped.items(), key=lambda item: item[0])
    }


def build_question_type_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize failures for each multi-valued question type."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        for question_type in _string_list(case.get("question_types")) or ["unknown"]:
            grouped[question_type].append(case)
    return {
        label: summarize_cases(items)
        for label, items in sorted(grouped.items(), key=lambda item: item[0])
    }


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate status, decision, evidence, and bucket counts for case groups."""
    bucket_counter: Counter[str] = Counter()
    for case in cases:
        bucket_counter.update(classify_case(case))
    failure_cases = [case for case in cases if case.get("case_status") == "fail"]
    missing_cases = [case for case in cases if _missing_required_evidence(case)]
    return {
        "case_count": len(cases),
        "case_fail_count": len(failure_cases),
        "case_fail_rate": _rate(len(failure_cases), len(cases)),
        "missing_required_evidence_count": len(missing_cases),
        "missing_required_evidence_rate": _rate(len(missing_cases), len(cases)),
        "answer_allowed_fallback_count": sum(
            1
            for case in cases
            if case.get("expected_decision") == "answer_allowed"
            and not bool(case.get("pipeline_answered"))
        ),
        "fallback_required_answered_count": sum(
            1
            for case in cases
            if case.get("expected_decision") == "fallback_required"
            and bool(case.get("pipeline_answered"))
        ),
        "retrieval_error_count": sum(1 for case in cases if case.get("retrieval_error")),
        "generation_error_count": sum(1 for case in cases if case.get("generation_error")),
        "bucket_counts": {name: bucket_counter.get(name, 0) for name in ERROR_BUCKETS},
    }


def top_group_summaries(summary: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    """Return groups sorted by failure rate, then missing-evidence rate."""
    rows = [{"name": name, **payload} for name, payload in summary.items()]
    return sorted(
        rows,
        key=lambda row: (
            row["case_fail_rate"],
            row["missing_required_evidence_rate"],
            row["case_fail_count"],
            row["case_count"],
        ),
        reverse=True,
    )[:limit]


def select_top_failure_cases(
    cases: list[dict[str, Any]], *, limit: int = 25
) -> list[dict[str, Any]]:
    """Select representative failing or partial cases for manual review."""
    candidates = [
        case
        for case in cases
        if case.get("case_status") in {"fail", "partial"} or classify_case(case)
    ]
    return [
        _case_reference(case, include_reasons=True)
        for case in sorted(candidates, key=_case_sort_key)[:limit]
    ]


def diagnose_bottleneck(
    development_buckets: dict[str, Any],
    development_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Identify the largest likely bottleneck from development cases only."""
    signals = {
        "retrieval": development_buckets["retrieval_error"]["count"]
        + development_buckets[
            "selected_evidence_present_but_required_evidence_group_coverage_incomplete"
        ]["count"]
        + development_buckets["selected_evidence_empty"]["count"],
        "evidence_selection": development_buckets["parent_context_only_fallback"]["count"]
        + development_buckets["all_selected_evidence_caution_fallback"]["count"]
        + development_buckets["partial_answer_missing_required_evidence"]["count"],
        "fallback_policy": development_buckets["expected_answer_allowed_but_pipeline_fallback"][
            "count"
        ]
        + development_buckets["expected_fallback_required_but_pipeline_answered"]["count"],
        "generation": development_buckets["provider_or_generation_error"]["count"]
        + development_buckets["citation_guard_fallback"]["count"],
    }
    primary = max(signals, key=lambda key: (signals[key], key)) if development_cases else "unknown"
    return {
        "basis": "development_only",
        "primary_bottleneck": primary,
        "signals": signals,
        "development_case_count": len(development_cases),
    }


def recommend_next_actions(diagnosis: dict[str, Any]) -> list[str]:
    """Return conservative next actions without using held-out results for tuning."""
    primary = diagnosis.get("primary_bottleneck")
    common = [
        "Use development split diagnostics for fixes; keep held_out_test reporting-only.",
        "Do not change benchmark labels, qrels, legal chunks, retrieval artifacts, or generated results.",
    ]
    if primary == "retrieval":
        return [
            "Inspect development answer_allowed cases with empty or incomplete selected evidence.",
            "Improve retrieval/evidence coverage on development cases before rerunning final reporting.",
            *common,
        ]
    if primary == "evidence_selection":
        return [
            "Review evidence selection warnings for parent-context-only and caution-only decisions.",
            "Tighten citation-safe child evidence selection without making parent context directly citable.",
            *common,
        ]
    if primary == "fallback_policy":
        return [
            "Audit decision policy mismatches between expected answerability and pipeline decisions.",
            "Check whether fallback thresholds are too conservative on answer_allowed development cases.",
            *common,
        ]
    if primary == "generation":
        return [
            "Inspect citation guard failures and provider errors before changing retrieval.",
            "Keep strict citation fallback enabled while improving prompt or provider reliability.",
            *common,
        ]
    return common


def write_strict_generation_error_analysis(
    output_dir: Path,
    analysis: dict[str, Any],
) -> None:
    """Write all strict generation error-analysis artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "error_buckets.json", analysis["error_buckets"])
    write_json_atomic(
        output_dir / "development_error_buckets.json",
        analysis["development_error_buckets"],
    )
    write_json_atomic(output_dir / "domain_error_summary.json", analysis["domain_error_summary"])
    write_json_atomic(
        output_dir / "question_type_error_summary.json",
        analysis["question_type_error_summary"],
    )
    write_jsonl_atomic(output_dir / "top_failure_cases.jsonl", analysis["top_failure_cases"])
    (output_dir / "strict_generation_error_analysis.md").write_text(
        render_markdown_report(analysis),
        encoding="utf-8",
    )


def render_markdown_report(analysis: dict[str, Any]) -> str:
    """Render a concise markdown error-analysis report."""
    dev_buckets = analysis["development_error_buckets"]
    all_buckets = analysis["error_buckets"]
    bottleneck = analysis["bottleneck_diagnosis"]
    weakest_domains = analysis["top_failing_domains"][:5]
    weakest_question_types = analysis["top_failing_question_types"][:5]
    lines = [
        "# Strict Generation Error Analysis",
        "",
        "## Scope",
        "",
        f"- Source workflow: `{SOURCE_WORKFLOW_NAME}`.",
        f"- Retrieval strategy: `{RETRIEVAL_STRATEGY}`.",
        "- Development split is analyzed first.",
        "- Held-out test is reporting-only and must not drive tuning.",
        "",
        "## Why many cases failed",
        "",
        _failure_explanation(dev_buckets),
        "",
        "## Key counts",
        "",
        "- Development answer_allowed fallback cases: "
        f"{dev_buckets['expected_answer_allowed_but_pipeline_fallback']['count']}.",
        "- All answer_allowed fallback cases: "
        f"{all_buckets['expected_answer_allowed_but_pipeline_fallback']['count']}.",
        "- Development fallback_required answered cases: "
        f"{dev_buckets['expected_fallback_required_but_pipeline_answered']['count']}.",
        "- All fallback_required answered cases: "
        f"{all_buckets['expected_fallback_required_but_pipeline_answered']['count']}.",
        "",
        "## Weakest domains",
        "",
        *_summary_lines(weakest_domains),
        "",
        "## Weakest question types",
        "",
        *_summary_lines(weakest_question_types),
        "",
        "## Main bottleneck",
        "",
        f"- Primary bottleneck: `{bottleneck['primary_bottleneck']}`.",
        f"- Signals: `{json.dumps(bottleneck['signals'], sort_keys=True)}`.",
        "",
        "## Recommended next actions",
        "",
        *[f"- {item}" for item in analysis["recommended_next_actions"]],
        "",
    ]
    return "\n".join(lines)


def load_case_results(path: Path) -> list[dict[str, Any]]:
    """Load strict generation case results from JSONL."""
    if not path.is_file():
        raise StrictGenerationErrorAnalysisError(f"case results not found: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise StrictGenerationErrorAnalysisError(
                    f"invalid JSONL at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise StrictGenerationErrorAnalysisError(
                    f"case result must be an object at {path}:{line_number}"
                )
            records.append(payload)
    if not records:
        raise StrictGenerationErrorAnalysisError(f"case results are empty: {path}")
    return records


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    if not path.is_file():
        raise StrictGenerationErrorAnalysisError(f"required input not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StrictGenerationErrorAnalysisError(f"JSON root must be an object: {path}")
    return payload


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL records atomically."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def _failure_explanation(development_buckets: dict[str, Any]) -> str:
    answer_fallback = development_buckets["expected_answer_allowed_but_pipeline_fallback"]["count"]
    incomplete = development_buckets[
        "selected_evidence_present_but_required_evidence_group_coverage_incomplete"
    ]["count"]
    empty = development_buckets["selected_evidence_empty"]["count"]
    citation = development_buckets["citation_guard_fallback"]["count"]
    retrieval = development_buckets["retrieval_error"]["count"]
    generation = development_buckets["provider_or_generation_error"]["count"]
    return (
        "Most failures should be read through development split buckets first: "
        f"{answer_fallback} answer-allowed cases fell back, {incomplete} cases had "
        f"incomplete required evidence coverage, {empty} cases had no selected evidence, "
        f"{citation} cases fell back through citation guard behavior, {retrieval} cases had "
        f"retrieval errors, and {generation} cases had provider/generation errors."
    )


def _summary_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No cases."]
    return [
        "- "
        f"`{row['name']}`: fail_rate={row['case_fail_rate']:.3f}, "
        f"missing_required_evidence_rate={row['missing_required_evidence_rate']:.3f}, "
        f"cases={row['case_count']}."
        for row in rows
    ]


def _case_reference(case: dict[str, Any], *, include_reasons: bool) -> dict[str, Any]:
    reference = {
        "query_id": case.get("query_id"),
        "split": case.get("split"),
        "primary_domain": case.get("primary_domain"),
        "question_types": _string_list(case.get("question_types")),
        "expected_decision": case.get("expected_decision"),
        "pipeline_decision": case.get("pipeline_decision"),
        "pipeline_answered": bool(case.get("pipeline_answered")),
        "case_status": case.get("case_status"),
        "error": case.get("error"),
        "retrieval_error": case.get("retrieval_error"),
        "generation_error": case.get("generation_error"),
        "selected_evidence_count": len(_string_list(case.get("selected_evidence_ids"))),
        "selected_evidence_group_coverage": _group_coverage(case),
    }
    if include_reasons:
        reference["matched_buckets"] = classify_case(case)
        reference["fallback_reasons"] = _string_list(case.get("fallback_reasons"))
        reference["selection_warnings"] = _string_list(case.get("selection_warnings"))
    return reference


def _case_sort_key(case: dict[str, Any]) -> tuple[int, int, str, str]:
    status_rank = {"fail": 0, "partial": 1, "pass": 2}.get(str(case.get("case_status")), 3)
    split_rank = {"development": 0, "held_out_test": 1}.get(str(case.get("split")), 2)
    return (status_rank, split_rank, str(case.get("primary_domain")), str(case.get("query_id")))


def _missing_required_evidence(case: dict[str, Any]) -> bool:
    payload = case.get("missing_required_evidence_check") or {}
    return bool(payload.get("missing_required_evidence"))


def _group_coverage(case: dict[str, Any]) -> float:
    payload = case.get("missing_required_evidence_check") or {}
    value = payload.get("selected_evidence_group_coverage", 0.0)
    return float(value if isinstance(value, int | float) else 0.0)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _contains_token(values: set[str], token: str) -> bool:
    return any(token in value for value in values)


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
