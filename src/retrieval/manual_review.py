"""Offline Markdown export for Phase 9C.2 manual faithfulness review.

The exporter reads an existing Phase 9C.1 JSON report and creates a human
review worksheet. It does not retrieve evidence, call an LLM, or determine
semantic faithfulness automatically.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from src.retrieval.generation_evaluation import (
    EvidencePreview,
    GenerationEvalCaseResult,
    GenerationEvalReport,
    build_text_preview,
    find_secret_leak_labels,
)
from src.retrieval.selection import AnswerabilityDecision
from src.retrieval.workflows.common import is_protected_output

DEFAULT_INPUT = Path("artifacts/reports/retrieval/naive_rag_generation_eval_expanded.json")
DEFAULT_OUTPUT = Path(
    "artifacts/reports/retrieval/naive_rag_generation_eval_expanded_manual_review.md"
)
_CITATION_ID_RE = re.compile(r"\[E[1-9][0-9]*\]")
_CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
DEFAULT_MAX_ANSWER_PREVIEW_CHARS = 1200
DEFAULT_MAX_EVIDENCE_PREVIEW_CHARS = 500


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the offline Phase 9C.2 export CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/retrieval/export_naive_rag_manual_review.py",
        description="Export an existing generation report as a manual review worksheet.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--max-answer-preview-chars",
        type=int,
        default=DEFAULT_MAX_ANSWER_PREVIEW_CHARS,
    )
    parser.add_argument(
        "--max-evidence-preview-chars",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_PREVIEW_CHARS,
    )
    return parser


def load_generation_report(path: Path) -> GenerationEvalReport:
    """Load a validated Phase 9C.1 report without external service calls.

    Args:
        path: Existing expanded generation evaluation JSON report.

    Returns:
        Validated generation evaluation report.

    Raises:
        ValueError: If the report contains secret-like authentication content.
        OSError: If the report cannot be read.
    """
    serialized = path.read_text(encoding="utf-8")
    if find_secret_leak_labels(serialized):
        raise ValueError("refusing manual review export from unsafe report content")
    return GenerationEvalReport.model_validate_json(serialized)


def render_manual_review(
    report: GenerationEvalReport,
    *,
    max_answer_preview_chars: int = DEFAULT_MAX_ANSWER_PREVIEW_CHARS,
    max_evidence_preview_chars: int = DEFAULT_MAX_EVIDENCE_PREVIEW_CHARS,
) -> str:
    """Render a human review worksheet from deterministic evaluation metadata.

    The source report contains answer previews and citation IDs, but not the
    selected evidence text or citation summaries. The worksheet therefore
    leaves semantic verdicts unchecked and requires the reviewer to inspect
    the original selected evidence separately.

    Args:
        report: Validated expanded generation evaluation report.

    Returns:
        Secret-screened Markdown review worksheet.

    Raises:
        ValueError: If source or rendered content contains secret-like markers.
    """
    if max_answer_preview_chars <= 0 or max_evidence_preview_chars <= 0:
        raise ValueError("manual review preview limits must be positive")
    if find_secret_leak_labels(report.model_dump_json()):
        raise ValueError("refusing manual review export from unsafe report content")

    priority_ids = [
        case.id
        for case in report.cases
        if case.manual_review_required or case.all_selected_evidence_caution
    ]
    lines = [
        "# Naive RAG Manual Faithfulness Review",
        "",
        f"Status: `{_review_status(report)}`",
        "",
        "This worksheet supports human claim-to-citation inspection. It does not "
        "prove semantic faithfulness or legal correctness and is not professional "
        "legal advice.",
        "",
        "Evidence previews contain only short, redacted safe-citable child text. "
        "Auxiliary parent context is represented by flags and is not directly citable. "
        "Reviewers must still assign all semantic verdicts manually.",
        "",
        "## Run Summary",
        "",
        f"- Source status: `{report.status}`",
        f"- Cases: {report.total_cases}",
        f"- Generated answers: {_generated_case_count(report)}",
        f"- Fallback cases: {_fallback_case_count(report)}",
        f"- Manual-review cases: {report.manual_review_required_count}",
        f"- All-caution cases: {report.cases_with_all_caution_evidence}",
        f"- Evidence previews: {report.evidence_preview_total_count}",
        f"- Missing cited evidence previews: {report.evidence_preview_missing_count}",
        f"- Priority review: {', '.join(f'`{case_id}`' for case_id in priority_ids)}",
        "",
        "## Reviewer Verdicts",
        "",
        "Use one of: `pass`, `partial`, `fail`, `needs_more_evidence`, "
        "`not_applicable_for_fallback`.",
        "",
    ]

    for index, case in enumerate(report.cases, start=1):
        lines.extend(
            _render_case(
                index,
                case,
                max_answer_preview_chars=max_answer_preview_chars,
                max_evidence_preview_chars=max_evidence_preview_chars,
            )
        )

    rendered = "\n".join(lines).rstrip() + "\n"
    if find_secret_leak_labels(rendered):
        raise ValueError("refusing to write unsafe manual review content")
    return rendered


def write_manual_review(path: Path, content: str) -> None:
    """Write a Markdown review artifact within allowed report boundaries.

    Args:
        path: Destination Markdown path.
        content: Secret-screened review content.

    Raises:
        ValueError: If the destination is protected or content is unsafe.
        OSError: If the artifact cannot be written.
    """
    if is_protected_output(path):
        raise ValueError(f"refusing protected manual review output path: {path}")
    if find_secret_leak_labels(content):
        raise ValueError("refusing to write unsafe manual review content")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    """Run the offline Phase 9C.2 manual review export."""
    args = build_arg_parser().parse_args(argv)
    try:
        report = load_generation_report(args.input)
        content = render_manual_review(
            report,
            max_answer_preview_chars=args.max_answer_preview_chars,
            max_evidence_preview_chars=args.max_evidence_preview_chars,
        )
        write_manual_review(args.output, content)
    except (OSError, ValueError) as exc:
        print(f"Manual review export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Manual review artifact: {args.output}")
    print(f"Cases exported: {report.total_cases}")
    print(f"Status: {_review_status(report)}")
    return 0


def _render_case(
    index: int,
    case: GenerationEvalCaseResult,
    *,
    max_answer_preview_chars: int,
    max_evidence_preview_chars: int,
) -> list[str]:
    cited_ids = _citation_ids(case.answer_preview)
    answer_preview, locally_truncated = build_text_preview(
        case.answer_preview,
        max_chars=max_answer_preview_chars,
    )
    answer_truncated = case.answer_preview_truncated or locally_truncated
    priority_flags = _priority_flags(case, answer_truncated=answer_truncated)
    lines = [
        f"## {index}. `{case.id}`",
        "",
        f"- Query: {_inline(case.query)}",
        f"- Decision: `{case.decision}`",
        f"- LLM called: `{str(case.llm_called).lower()}`",
        f"- Blocking: `{str(case.blocking).lower()}`",
        f"- Manual review required: `{str(case.manual_review_required).lower()}`",
        f"- Selected evidence count: {case.selected_evidence_count}",
        f"- Caution selected count: {case.caution_selected_count}",
        f"- All selected evidence caution: `{str(case.all_selected_evidence_caution).lower()}`",
        f"- Cited evidence IDs in preview: {', '.join(cited_ids) if cited_ids else 'none'}",
        f"- Evidence preview count: {case.evidence_preview_count}",
        f"- Missing cited evidence previews: {case.evidence_preview_missing_count}",
        f"- Answer truncated: `{str(answer_truncated).lower()}`",
        f"- Priority flags: {', '.join(priority_flags) or 'none'}",
        f"- Fallback reasons: {', '.join(case.fallback_reasons) or 'none'}",
        "- Preliminary reviewer verdict: `"
        + (
            "not_applicable_for_fallback"
            if case.decision != AnswerabilityDecision.ANSWER_ALLOWED
            else "unchecked"
        )
        + "`",
        "",
        "### Selection Warnings",
        "",
    ]
    lines.extend([f"- `{warning}`" for warning in case.selection_warnings] or ["- None recorded."])
    lines.extend(
        [
            "",
            "### Answer Preview",
            "",
            *_blockquote(answer_preview),
            *(
                ["", "> **Preview truncated; review the complete answer separately.**"]
                if answer_truncated
                else []
            ),
            "",
            "### Evidence Preview Table",
            "",
            *_render_evidence_table(
                case,
                max_evidence_preview_chars=max_evidence_preview_chars,
            ),
            "",
        ]
    )
    if case.decision == AnswerabilityDecision.ANSWER_ALLOWED:
        lines.extend(_render_claim_checklist(case.answer_preview))
    else:
        lines.extend(_render_fallback_checklist(case))
    lines.extend(
        [
            "",
            "### Manual Review Checklist",
            "",
            "- [ ] Every material legal claim is supported by its cited evidence.",
            "- [ ] Citation hierarchy and source metadata match the claim.",
            "- [ ] The answer does not broaden conditions, exceptions, or scope.",
            "- [ ] Caution evidence has been inspected and explained.",
            "- [ ] Auxiliary context was not treated as directly citable evidence.",
            "- [ ] Final verdict and reviewer notes are recorded.",
            "",
            "Reviewer notes:",
            "",
            "> Unchecked.",
            "",
        ]
    )
    return lines


def _render_claim_checklist(answer_preview: str) -> list[str]:
    claims = _claim_rows(answer_preview)
    lines = [
        "### Claim-to-Citation Checklist",
        "",
        "| Claim from answer preview | Citation IDs | Reviewer check | Notes |",
        "| --- | --- | --- | --- |",
    ]
    if not claims:
        lines.append("| Reviewer identifies claim | none | unchecked | |")
        return lines
    for claim, citation_ids in claims:
        lines.append(
            f"| {_table_cell(claim)} | {_table_cell(', '.join(citation_ids) or 'none')} "
            "| unchecked | |"
        )
    return lines


def _render_fallback_checklist(case: GenerationEvalCaseResult) -> list[str]:
    return [
        "### Fallback Review",
        "",
        "| Check | Recorded state | Reviewer check | Notes |",
        "| --- | --- | --- | --- |",
        f"| Fallback decision recorded | `{case.decision}` | checked | |",
        f"| LLM was not called | `{str(not case.llm_called).lower()}` | checked | |",
        f"| Citation count is zero | `{str(case.citation_count == 0).lower()}` | checked | |",
        "| Answer avoided unsupported legal claims | review answer preview | unchecked | |",
        "| Fallback reason is acceptable | review fallback reasons | unchecked | |",
    ]


def _claim_rows(answer_preview: str) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    for segment in _CLAIM_SPLIT_RE.split(answer_preview):
        claim = segment.strip().lstrip("*- ").strip()
        if claim:
            rows.append((claim, _citation_ids(claim)))
    return rows


def _citation_ids(text: str) -> list[str]:
    return list(dict.fromkeys(_CITATION_ID_RE.findall(text)))


def _blockquote(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.splitlines()] or [">"]


def _inline(text: str) -> str:
    return " ".join(text.split())


def _table_cell(text: str) -> str:
    return _inline(text).replace("|", "\\|")


def _generated_case_count(report: GenerationEvalReport) -> int:
    return sum(case.decision == AnswerabilityDecision.ANSWER_ALLOWED for case in report.cases)


def _fallback_case_count(report: GenerationEvalReport) -> int:
    return report.total_cases - _generated_case_count(report)


def _render_evidence_table(
    case: GenerationEvalCaseResult,
    *,
    max_evidence_preview_chars: int,
) -> list[str]:
    previews = case.evidence_previews
    lines = [
        "| Evidence ID | Citation | Scope | Safety | Text Preview | Source |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not previews:
        lines.append("| none | unavailable | unavailable | unavailable | missing preview | |")
        return lines
    for preview in previews:
        lines.append(
            _evidence_row(
                preview,
                max_evidence_preview_chars=max_evidence_preview_chars,
            )
        )
    return lines


def _evidence_row(
    preview: EvidencePreview,
    *,
    max_evidence_preview_chars: int,
) -> str:
    text = preview.text_preview or "unavailable"
    text, locally_truncated = build_text_preview(
        text,
        max_chars=max_evidence_preview_chars,
    )
    if preview.text_preview_truncated or locally_truncated:
        text = f"{text} [truncated]"
    citation = preview.citation or _citation_summary(preview)
    return (
        f"| {_table_cell(preview.evidence_id)} "
        f"| {_table_cell(citation or 'unavailable')} "
        f"| {_table_cell(preview.citation_scope or 'unavailable')} "
        f"| {_table_cell(preview.safety_level or 'unavailable')} "
        f"| {_table_cell(text)} "
        f"| {_table_cell(preview.source_url or 'unavailable')} |"
    )


def _citation_summary(preview: EvidencePreview) -> str | None:
    parts = [
        preview.law_title or preview.law_id,
        f"Điều {preview.article_number}" if preview.article_number else None,
        f"Khoản {preview.clause_number}" if preview.clause_number else None,
        f"Điểm {preview.point_label}" if preview.point_label else None,
    ]
    values = [part for part in parts if part]
    return ", ".join(values) if values else None


def _priority_flags(
    case: GenerationEvalCaseResult,
    *,
    answer_truncated: bool,
) -> list[str]:
    flags: list[str] = []
    if case.all_selected_evidence_caution:
        flags.append("all-caution evidence")
    if case.manual_review_required:
        flags.append("manual-review required")
    if case.decision != AnswerabilityDecision.ANSWER_ALLOWED:
        flags.append("fallback case")
    if case.evidence_preview_missing_count or (
        case.decision == AnswerabilityDecision.ANSWER_ALLOWED and not case.evidence_previews
    ):
        flags.append("missing evidence preview")
    if answer_truncated:
        flags.append("answer truncated")
    return flags


def _review_status(report: GenerationEvalReport) -> str:
    generated_cases = [
        case for case in report.cases if case.decision == AnswerabilityDecision.ANSWER_ALLOWED
    ]
    if (
        generated_cases
        and report.evidence_preview_missing_count == 0
        and all(case.evidence_previews for case in generated_cases)
    ):
        return "evidence_preview_review_ready"
    return "evidence_preview_partial"
