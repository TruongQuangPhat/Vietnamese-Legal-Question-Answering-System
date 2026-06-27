"""Offline evidence selection diagnostics for strict generation reports."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.indexing.official_artifacts import write_json_atomic

WORKFLOW_NAME = "evidence_selection_diagnostics"
SOURCE_WORKFLOW = "strict_generation_evaluation"
RETRIEVAL_STRATEGY = "coverage_aware_quota"

DIAGNOSTIC_LABELS = (
    "answer_allowed_fallback",
    "fallback_required_answered",
    "selected_evidence_empty",
    "required_evidence_not_retrieved",
    "required_evidence_retrieved_but_not_selected",
    "selected_but_incomplete_required_group_coverage",
    "parent_context_only_fallback",
    "all_selected_evidence_caution",
    "exact_target_missing_in_eval_mode",
    "citation_guard_fallback",
    "retrieval_error",
    "generation_error",
)

DIRECT_RELEVANCE = {"required_direct", "alternative_direct"}


@dataclass(frozen=True)
class EvidenceSelectionDiagnosticsPaths:
    """Input reports, benchmark references, and output directory."""

    case_results: Path
    metrics_all: Path
    breakdowns: Path
    comparison: Path
    error_buckets: Path
    development_error_buckets: Path
    domain_error_summary: Path
    question_type_error_summary: Path
    qrels: Path
    evidence_groups: Path
    output_dir: Path


class EvidenceSelectionDiagnosticsError(RuntimeError):
    """Raised when offline evidence selection diagnostics cannot run safely."""


def run_evidence_selection_diagnostics(
    paths: EvidenceSelectionDiagnosticsPaths,
) -> dict[str, Any]:
    """Run offline evidence-selection diagnostics and write reports."""
    cases = load_jsonl_objects(paths.case_results)
    metrics = load_json_object(paths.metrics_all)
    breakdowns = load_json_object(paths.breakdowns)
    comparison = load_json_object(paths.comparison)
    error_buckets = load_json_object(paths.error_buckets)
    development_error_buckets = load_json_object(paths.development_error_buckets)
    domain_error_summary = load_json_object(paths.domain_error_summary)
    question_type_error_summary = load_json_object(paths.question_type_error_summary)
    qrels = load_qrels(paths.qrels)
    evidence_groups = load_evidence_groups(paths.evidence_groups)
    diagnostics = build_evidence_selection_diagnostics(
        cases=cases,
        qrels=qrels,
        evidence_groups=evidence_groups,
        metrics=metrics,
        breakdowns=breakdowns,
        comparison=comparison,
        error_buckets=error_buckets,
        development_error_buckets=development_error_buckets,
        domain_error_summary=domain_error_summary,
        question_type_error_summary=question_type_error_summary,
    )
    write_evidence_selection_diagnostics(paths.output_dir, diagnostics)
    return diagnostics


def build_evidence_selection_diagnostics(
    *,
    cases: list[dict[str, Any]],
    qrels: dict[str, set[str]],
    evidence_groups: dict[str, list[dict[str, Any]]],
    metrics: dict[str, Any],
    breakdowns: dict[str, Any],
    comparison: dict[str, Any],
    error_buckets: dict[str, Any],
    development_error_buckets: dict[str, Any],
    domain_error_summary: dict[str, Any],
    question_type_error_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic diagnostics from existing reports and benchmark references."""
    if not cases:
        raise EvidenceSelectionDiagnosticsError("case results must not be empty")
    case_diagnostics = [
        build_case_diagnostic(case, qrels=qrels, evidence_groups=evidence_groups) for case in cases
    ]
    development_case_diagnostics = [
        item for item in case_diagnostics if item["split"] == "development"
    ]
    diagnostic_counts = count_diagnostic_labels(case_diagnostics)
    development_diagnostic_counts = count_diagnostic_labels(development_case_diagnostics)
    domain_summary = build_group_summary(case_diagnostics, "primary_domain")
    question_type_summary = build_question_type_summary(case_diagnostics)
    matrix = build_retrieved_vs_selected_matrix(case_diagnostics)
    warning_summary = build_warning_summary(case_diagnostics)
    primary = likely_primary_bottleneck(development_case_diagnostics)
    summary = {
        "report_type": WORKFLOW_NAME,
        "workflow_name": WORKFLOW_NAME,
        "source_workflow": SOURCE_WORKFLOW,
        "retrieval_strategy": RETRIEVAL_STRATEGY,
        "held_out_reporting_only": True,
        "development_first": True,
        "query_count": len(case_diagnostics),
        "development_query_count": len(development_case_diagnostics),
        "diagnostic_counts": diagnostic_counts,
        "development_diagnostic_counts": development_diagnostic_counts,
        "likely_primary_bottleneck": primary,
        "recommended_next_actions": recommended_next_actions(primary),
        "input_summary": {
            "metrics_query_count": metrics.get("query_count"),
            "breakdown_dimensions": sorted(breakdowns.keys()),
            "comparison_systems": sorted((comparison.get("systems") or {}).keys()),
            "error_bucket_count": len(error_buckets),
            "development_error_bucket_count": len(development_error_buckets),
            "domain_error_summary_count": len(domain_error_summary),
            "question_type_error_summary_count": len(question_type_error_summary),
        },
    }
    return {
        "summary": summary,
        "development_summary": {
            **summary,
            "query_count": len(development_case_diagnostics),
            "diagnostic_counts": development_diagnostic_counts,
            "scope": "development",
        },
        "case_diagnostics": case_diagnostics,
        "development_case_diagnostics": development_case_diagnostics,
        "retrieved_vs_selected_matrix": matrix,
        "warning_summary": warning_summary,
        "domain_selection_diagnostics": domain_summary,
        "question_type_selection_diagnostics": question_type_summary,
        "top_selector_failure_cases": top_selector_failure_cases(case_diagnostics),
    }


def build_case_diagnostic(
    case: dict[str, Any],
    *,
    qrels: dict[str, set[str]],
    evidence_groups: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build one case-level evidence selection diagnostic record."""
    query_id = str(case.get("query_id") or "")
    retrieved_ids = set(_string_list(case.get("retrieved_evidence_ids")))
    selected_chunk_ids = set(_string_list(case.get("selected_chunk_ids")))
    selected_evidence_ids = set(_string_list(case.get("selected_evidence_ids")))
    selected_ids_for_matching = selected_chunk_ids | selected_evidence_ids
    groups = evidence_groups.get(query_id, [])
    required_group_ids = required_group_chunk_ids(groups)
    required_ids = set(qrels.get(query_id, set())) | {
        chunk_id for ids in required_group_ids for chunk_id in ids
    }
    required_retrieved = required_ids & retrieved_ids
    required_selected = required_ids & selected_ids_for_matching
    required_retrieved_but_not_selected = required_retrieved - required_selected
    selected_evidence_count = max(len(selected_chunk_ids), len(selected_evidence_ids))
    group_coverage = selected_evidence_group_coverage(case, groups, selected_ids_for_matching)
    labels = classify_diagnostic_labels(
        case=case,
        required_evidence_count=len(required_ids),
        required_retrieved_count=len(required_retrieved),
        required_selected_count=len(required_selected),
        required_retrieved_but_not_selected_count=len(required_retrieved_but_not_selected),
        selected_evidence_count=selected_evidence_count,
        selected_evidence_group_coverage=group_coverage,
    )
    return {
        "query_id": query_id,
        "split": case.get("split"),
        "primary_domain": case.get("primary_domain"),
        "question_types": _string_list(case.get("question_types")),
        "expected_decision": case.get("expected_decision"),
        "pipeline_decision": case.get("pipeline_decision"),
        "case_status": case.get("case_status"),
        "pipeline_answered": bool(case.get("pipeline_answered")),
        "retrieved_evidence_count": len(retrieved_ids),
        "selected_evidence_count": selected_evidence_count,
        "required_evidence_count": len(required_ids),
        "required_group_count": len(required_group_ids),
        "required_retrieved_count": len(required_retrieved),
        "required_selected_count": len(required_selected),
        "required_retrieved_but_not_selected_count": len(required_retrieved_but_not_selected),
        "selected_evidence_group_coverage": group_coverage,
        "fallback_reasons": _string_list(case.get("fallback_reasons")),
        "selection_warnings": _string_list(case.get("selection_warnings")),
        "diagnostic_labels": labels,
        "likely_bottleneck": likely_case_bottleneck(labels),
    }


def classify_diagnostic_labels(
    *,
    case: dict[str, Any],
    required_evidence_count: int,
    required_retrieved_count: int,
    required_selected_count: int,
    required_retrieved_but_not_selected_count: int,
    selected_evidence_count: int,
    selected_evidence_group_coverage: float,
) -> list[str]:
    """Return functional evidence-selection diagnostic labels for one case."""
    labels: list[str] = []
    expected = str(case.get("expected_decision") or "")
    answered = bool(case.get("pipeline_answered"))
    fallback_reasons = set(_string_list(case.get("fallback_reasons")))
    warnings = set(_string_list(case.get("selection_warnings")))
    citation_guard = case.get("citation_guard_result") or {}
    citation_invalid = (
        bool(citation_guard.get("citation_issue_count", 0))
        or citation_guard.get("citation_id_valid") is False
        or citation_guard.get("citation_coverage_valid") is False
    )
    if expected == "answer_allowed" and not answered:
        labels.append("answer_allowed_fallback")
    if expected == "fallback_required" and answered:
        labels.append("fallback_required_answered")
    if selected_evidence_count == 0:
        labels.append("selected_evidence_empty")
    if required_evidence_count > 0 and required_retrieved_count == 0:
        labels.append("required_evidence_not_retrieved")
    if required_retrieved_but_not_selected_count > 0:
        labels.append("required_evidence_retrieved_but_not_selected")
    if (
        selected_evidence_count > 0
        and expected == "answer_allowed"
        and selected_evidence_group_coverage < 1.0
    ):
        labels.append("selected_but_incomplete_required_group_coverage")
    if _contains_token(fallback_reasons, "parent_context_only"):
        labels.append("parent_context_only_fallback")
    if (
        "all_selected_evidence_caution" in fallback_reasons
        or "all_selected_evidence_caution" in warnings
    ):
        labels.append("all_selected_evidence_caution")
    if "exact_target_missing_in_eval_mode" in fallback_reasons:
        labels.append("exact_target_missing_in_eval_mode")
    if not answered and citation_invalid:
        labels.append("citation_guard_fallback")
    if case.get("retrieval_error"):
        labels.append("retrieval_error")
    if case.get("generation_error"):
        labels.append("generation_error")
    return labels


def likely_case_bottleneck(labels: list[str]) -> str:
    """Map diagnostic labels to one likely bottleneck."""
    label_set = set(labels)
    if "generation_error" in label_set or "citation_guard_fallback" in label_set:
        return "generation"
    if "retrieval_error" in label_set or "required_evidence_not_retrieved" in label_set:
        return "retrieval"
    if "exact_target_missing_in_eval_mode" in label_set:
        return "benchmark_target_matching"
    if {
        "required_evidence_retrieved_but_not_selected",
        "selected_but_incomplete_required_group_coverage",
        "selected_evidence_empty",
        "parent_context_only_fallback",
        "all_selected_evidence_caution",
    } & label_set:
        return "evidence_selection"
    if {"answer_allowed_fallback", "fallback_required_answered"} & label_set:
        return "fallback_policy"
    return "none"


def likely_primary_bottleneck(case_diagnostics: list[dict[str, Any]]) -> str:
    """Return the most common likely bottleneck from development diagnostics."""
    counts = Counter(
        item["likely_bottleneck"]
        for item in case_diagnostics
        if item["likely_bottleneck"] != "none"
    )
    if not counts:
        return "none"
    return sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]


def build_retrieved_vs_selected_matrix(case_diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate required evidence retrieval and selection relationships."""
    counts: Counter[str] = Counter()
    for item in case_diagnostics:
        if item["required_evidence_count"] == 0:
            counts["no_required_evidence_defined"] += 1
        elif item["required_retrieved_count"] == 0:
            counts["required_evidence_not_retrieved"] += 1
        elif item["required_selected_count"] > 0:
            counts["required_evidence_retrieved_and_selected"] += 1
        elif item["required_retrieved_but_not_selected_count"] > 0:
            counts["required_evidence_retrieved_but_not_selected"] += 1
        if item["selected_evidence_count"] == 0:
            counts["selected_evidence_empty"] += 1
    return {
        "case_count": len(case_diagnostics),
        "counts": dict(sorted(counts.items())),
    }


def build_warning_summary(case_diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate fallback reasons and selection warnings."""
    fallback_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    for item in case_diagnostics:
        fallback_counts.update(item["fallback_reasons"])
        warning_counts.update(item["selection_warnings"])
    return {
        "fallback_reason_counts": dict(sorted(fallback_counts.items())),
        "selection_warning_counts": dict(sorted(warning_counts.items())),
    }


def build_group_summary(case_diagnostics: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
    """Aggregate diagnostics by a single-valued field."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in case_diagnostics:
        grouped[str(item.get(field_name) or "unknown")].append(item)
    return {
        label: summarize_diagnostics(items)
        for label, items in sorted(grouped.items(), key=lambda entry: entry[0])
    }


def build_question_type_summary(case_diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate diagnostics by each question type."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in case_diagnostics:
        for question_type in item["question_types"] or ["unknown"]:
            grouped[question_type].append(item)
    return {
        label: summarize_diagnostics(items)
        for label, items in sorted(grouped.items(), key=lambda entry: entry[0])
    }


def summarize_diagnostics(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a group of case diagnostics."""
    labels = Counter(label for item in items for label in item["diagnostic_labels"])
    bottlenecks = Counter(item["likely_bottleneck"] for item in items)
    selection_blocked = sum(
        1
        for item in items
        if item["likely_bottleneck"] == "evidence_selection"
        or "required_evidence_retrieved_but_not_selected" in item["diagnostic_labels"]
    )
    return {
        "case_count": len(items),
        "diagnostic_counts": {label: labels.get(label, 0) for label in DIAGNOSTIC_LABELS},
        "likely_bottleneck_counts": dict(sorted(bottlenecks.items())),
        "selection_bottleneck_count": selection_blocked,
        "selection_bottleneck_rate": _rate(selection_blocked, len(items)),
        "selected_evidence_empty_count": labels.get("selected_evidence_empty", 0),
        "required_evidence_not_retrieved_count": labels.get("required_evidence_not_retrieved", 0),
        "required_evidence_retrieved_but_not_selected_count": labels.get(
            "required_evidence_retrieved_but_not_selected", 0
        ),
    }


def count_diagnostic_labels(case_diagnostics: list[dict[str, Any]]) -> dict[str, int]:
    """Count diagnostic labels across case diagnostics."""
    counts = Counter(label for item in case_diagnostics for label in item["diagnostic_labels"])
    return {label: counts.get(label, 0) for label in DIAGNOSTIC_LABELS}


def top_selector_failure_cases(
    case_diagnostics: list[dict[str, Any]], *, limit: int = 25
) -> list[dict[str, Any]]:
    """Return cases most relevant for manual evidence-selection inspection."""
    candidates = [
        item
        for item in case_diagnostics
        if item["likely_bottleneck"] == "evidence_selection"
        or "answer_allowed_fallback" in item["diagnostic_labels"]
        or "fallback_required_answered" in item["diagnostic_labels"]
    ]
    return sorted(candidates, key=_case_sort_key)[:limit]


def recommended_next_actions(primary_bottleneck: str) -> list[str]:
    """Return conservative next actions without using held-out results for tuning."""
    common = [
        "Do not relax citation guard.",
        "Do not make parent context directly citable.",
        "Do not change benchmark labels, qrels, legal chunks, retrieval artifacts, or generated results.",
        "Use development split only for policy changes.",
        "Keep held-out test reporting-only.",
    ]
    if primary_bottleneck == "evidence_selection":
        return [
            "Inspect why retrieved child evidence is marked caution or parent-context-only.",
            "Prefer improving selection diagnostics before changing selection policy.",
            *common,
        ]
    if primary_bottleneck == "retrieval":
        return [
            "Inspect development cases where required chunks never appeared in top retrieved evidence.",
            "Do not tune on held-out retrieval misses.",
            *common,
        ]
    if primary_bottleneck == "benchmark_target_matching":
        return [
            "Inspect exact-target evaluation misses against reviewed benchmark references.",
            "Do not rewrite qrels or labels without a separate reviewed benchmark task.",
            *common,
        ]
    if primary_bottleneck == "fallback_policy":
        return [
            "Audit answerability mismatches using development cases only.",
            "Preserve fallback when selected evidence is incomplete or unsafe.",
            *common,
        ]
    return common


def write_evidence_selection_diagnostics(output_dir: Path, diagnostics: dict[str, Any]) -> None:
    """Write all evidence-selection diagnostic artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "diagnostic_summary.json", diagnostics["summary"])
    write_json_atomic(
        output_dir / "development_diagnostic_summary.json",
        diagnostics["development_summary"],
    )
    write_jsonl_atomic(output_dir / "case_diagnostics.jsonl", diagnostics["case_diagnostics"])
    write_jsonl_atomic(
        output_dir / "development_case_diagnostics.jsonl",
        diagnostics["development_case_diagnostics"],
    )
    write_json_atomic(
        output_dir / "retrieved_vs_selected_matrix.json",
        diagnostics["retrieved_vs_selected_matrix"],
    )
    write_json_atomic(output_dir / "warning_summary.json", diagnostics["warning_summary"])
    write_json_atomic(
        output_dir / "domain_selection_diagnostics.json",
        diagnostics["domain_selection_diagnostics"],
    )
    write_json_atomic(
        output_dir / "question_type_selection_diagnostics.json",
        diagnostics["question_type_selection_diagnostics"],
    )
    write_jsonl_atomic(
        output_dir / "top_selector_failure_cases.jsonl",
        diagnostics["top_selector_failure_cases"],
    )
    (output_dir / "evidence_selection_diagnostics.md").write_text(
        render_markdown_report(diagnostics),
        encoding="utf-8",
    )


def render_markdown_report(diagnostics: dict[str, Any]) -> str:
    """Render a concise markdown report for evidence-selection diagnostics."""
    summary = diagnostics["summary"]
    dev_counts = summary["development_diagnostic_counts"]
    domain_rows = top_selection_groups(diagnostics["domain_selection_diagnostics"])
    question_rows = top_selection_groups(diagnostics["question_type_selection_diagnostics"])
    matrix = diagnostics["retrieved_vs_selected_matrix"]["counts"]
    lines = [
        "# Evidence Selection Diagnostics",
        "",
        "## Scope",
        "",
        f"- Workflow: `{WORKFLOW_NAME}`.",
        f"- Source workflow: `{SOURCE_WORKFLOW}`.",
        f"- Retrieval strategy: `{RETRIEVAL_STRATEGY}`.",
        "- Development split is used for improvement decisions.",
        "- Held-out test is reporting-only.",
        "",
        "## Main reason selected evidence coverage is low",
        "",
        _main_reason(summary["likely_primary_bottleneck"], dev_counts),
        "",
        "## Development counts",
        "",
        "- Retrieved-but-not-selected required evidence cases: "
        f"{dev_counts['required_evidence_retrieved_but_not_selected']}.",
        f"- Required evidence not retrieved cases: {dev_counts['required_evidence_not_retrieved']}.",
        f"- Parent-context-only fallback cases: {dev_counts['parent_context_only_fallback']}.",
        f"- Caution-only cases: {dev_counts['all_selected_evidence_caution']}.",
        f"- Exact target missing cases: {dev_counts['exact_target_missing_in_eval_mode']}.",
        "",
        "## Retrieved vs selected matrix",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(matrix.items())],
        "",
        "## Weakest domains",
        "",
        *_summary_lines(domain_rows),
        "",
        "## Weakest question types",
        "",
        *_summary_lines(question_rows),
        "",
        "## Manual inspection priority",
        "",
        "- Start with development cases in `top_selector_failure_cases.jsonl`.",
        "- Prioritize cases with required evidence retrieved but not selected.",
        "- Then inspect parent-context-only and caution-only fallback cases.",
        "",
        "## Recommended next actions",
        "",
        *[f"- {item}" for item in summary["recommended_next_actions"]],
        "",
    ]
    return "\n".join(lines)


def load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    """Load JSONL objects from disk."""
    if not path.is_file():
        raise EvidenceSelectionDiagnosticsError(f"JSONL input not found: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise EvidenceSelectionDiagnosticsError(
                    f"JSONL record must be an object at {path}:{line_number}"
                )
            records.append(payload)
    if not records:
        raise EvidenceSelectionDiagnosticsError(f"JSONL input is empty: {path}")
    return records


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    if not path.is_file():
        raise EvidenceSelectionDiagnosticsError(f"JSON input not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceSelectionDiagnosticsError(f"JSON root must be an object: {path}")
    return payload


def load_qrels(path: Path) -> dict[str, set[str]]:
    """Load direct evidence chunk IDs grouped by query."""
    records = load_jsonl_objects(path)
    grouped: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if str(record.get("relevance") or "") in DIRECT_RELEVANCE:
            grouped[str(record["query_id"])].add(str(record["chunk_id"]))
    return dict(grouped)


def load_evidence_groups(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load required evidence groups by query."""
    records = load_jsonl_objects(path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("requirement") == "required":
            grouped[str(record["query_id"])].append(record)
    return dict(grouped)


def required_group_chunk_ids(groups: list[dict[str, Any]]) -> list[set[str]]:
    """Return acceptable chunk IDs for each required evidence group."""
    return [set(_string_list(group.get("acceptable_chunk_ids"))) for group in groups]


def selected_evidence_group_coverage(
    case: dict[str, Any],
    groups: list[dict[str, Any]],
    selected_ids: set[str],
) -> float:
    """Return selected required group coverage, preferring case metric when present."""
    existing = (case.get("missing_required_evidence_check") or {}).get(
        "selected_evidence_group_coverage"
    )
    if isinstance(existing, int | float):
        return float(existing)
    required_groups = required_group_chunk_ids(groups)
    if not required_groups:
        return 0.0
    hits = sum(1 for group_ids in required_groups if group_ids & selected_ids)
    return hits / len(required_groups)


def top_selection_groups(summary: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    """Return groups sorted by evidence-selection bottleneck rate."""
    rows = [{"name": name, **payload} for name, payload in summary.items()]
    return sorted(
        rows,
        key=lambda row: (
            row["selection_bottleneck_rate"],
            row["required_evidence_retrieved_but_not_selected_count"],
            row["selected_evidence_empty_count"],
            row["case_count"],
        ),
        reverse=True,
    )[:limit]


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL records atomically."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def _case_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    split_rank = {"development": 0, "held_out_test": 1}.get(str(item.get("split")), 2)
    bottleneck_rank = {"evidence_selection": 0, "fallback_policy": 1, "retrieval": 2}.get(
        str(item.get("likely_bottleneck")),
        3,
    )
    return (
        split_rank,
        bottleneck_rank,
        str(item.get("primary_domain") or ""),
        str(item.get("query_id") or ""),
    )


def _main_reason(primary_bottleneck: str, development_counts: dict[str, int]) -> str:
    if primary_bottleneck == "evidence_selection":
        return (
            "Development diagnostics indicate evidence selection is the main bottleneck: "
            f"{development_counts['required_evidence_retrieved_but_not_selected']} cases had "
            "required evidence retrieved but not selected, "
            f"{development_counts['parent_context_only_fallback']} cases fell back because of "
            "parent-context-only behavior, and "
            f"{development_counts['all_selected_evidence_caution']} cases carried caution-only "
            "selection signals."
        )
    if primary_bottleneck == "retrieval":
        return "Development diagnostics indicate required evidence often did not appear in retrieved evidence."
    if primary_bottleneck == "benchmark_target_matching":
        return "Development diagnostics indicate exact target matching is blocking otherwise plausible evidence."
    if primary_bottleneck == "fallback_policy":
        return "Development diagnostics indicate answerability decisions need policy review."
    return "No dominant bottleneck was identified from development diagnostics."


def _summary_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No cases."]
    return [
        "- "
        f"`{row['name']}`: selection_bottleneck_rate={row['selection_bottleneck_rate']:.3f}, "
        "retrieved_but_not_selected="
        f"{row['required_evidence_retrieved_but_not_selected_count']}, "
        f"selected_empty={row['selected_evidence_empty_count']}, cases={row['case_count']}."
        for row in rows
    ]


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
