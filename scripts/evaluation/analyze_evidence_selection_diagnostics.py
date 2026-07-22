#!/usr/bin/env python3
"""Run offline evidence selection diagnostics for strict generation results."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.evidence_selection_diagnostics import (
    EvidenceSelectionDiagnosticsError,
    EvidenceSelectionDiagnosticsPaths,
    run_evidence_selection_diagnostics,
)
from src.evaluation.benchmark.fingerprinting import (
    add_benchmark_output_policy_argument,
    validate_benchmark_output_dir,
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_STRICT_GENERATION_DIR = Path(
    "artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation"
)
DEFAULT_ERROR_ANALYSIS_DIR = Path(
    "artifacts/reports/evaluation/advanced_rag/strict_generation_error_analysis"
)
DEFAULT_QRELS = Path("data/eval/legal_qa_benchmark/benchmark_qrels.jsonl")
DEFAULT_EVIDENCE_GROUPS = Path("data/eval/legal_qa_benchmark/evidence_groups.jsonl")
DEFAULT_OUTPUT_DIR = Path(
    "artifacts/reports/evaluation/advanced_rag/evidence_selection_diagnostics"
)
EVALUATION_REPORTS_ROOT = REPO_ROOT / "artifacts/reports/evaluation"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the offline evidence selection diagnostics parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/analyze_evidence_selection_diagnostics.py",
        description=(
            "Analyze strict generation evidence selection using existing offline artifacts."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--strict-generation-dir", type=Path, default=DEFAULT_STRICT_GENERATION_DIR)
    parser.add_argument("--error-analysis-dir", type=Path, default=DEFAULT_ERROR_ANALYSIS_DIR)
    parser.add_argument("--case-results", type=Path, default=None)
    parser.add_argument("--metrics-all", type=Path, default=None)
    parser.add_argument("--breakdowns", type=Path, default=None)
    parser.add_argument("--comparison", type=Path, default=None)
    parser.add_argument("--error-buckets", type=Path, default=None)
    parser.add_argument("--development-error-buckets", type=Path, default=None)
    parser.add_argument("--domain-error-summary", type=Path, default=None)
    parser.add_argument("--question-type-error-summary", type=Path, default=None)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--evidence-groups", type=Path, default=DEFAULT_EVIDENCE_GROUPS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    add_benchmark_output_policy_argument(parser)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run offline evidence selection diagnostics."""
    args = build_arg_parser().parse_args(argv)
    try:
        validate_cli_arguments(args.output_dir, output_policy=args.output_policy)
        diagnostics = run_evidence_selection_diagnostics(_paths_from_args(args))
    except (OSError, ValueError, EvidenceSelectionDiagnosticsError) as exc:
        print(f"evidence selection diagnostics failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    if not args.quiet:
        summary = diagnostics["summary"]
        print("Evidence Selection Diagnostics")
        print(f"Cases: {summary['query_count']}")
        print(f"Development cases: {summary['development_query_count']}")
        print(f"Primary bottleneck: {summary['likely_primary_bottleneck']}")
        print(f"Output: {args.output_dir}")
    return EXIT_SUCCESS


def validate_cli_arguments(output_dir: Path, *, output_policy: str = "canonical") -> None:
    """Validate the output path against the shared official benchmark policy."""
    validate_benchmark_output_dir(
        output_dir,
        repo_root=REPO_ROOT,
        evaluation_reports_root=EVALUATION_REPORTS_ROOT,
        output_policy=output_policy,
        label="output-dir",
    )


def _paths_from_args(args: argparse.Namespace) -> EvidenceSelectionDiagnosticsPaths:
    strict_generation_dir = args.strict_generation_dir
    error_analysis_dir = args.error_analysis_dir
    return EvidenceSelectionDiagnosticsPaths(
        case_results=args.case_results or strict_generation_dir / "case_results.jsonl",
        metrics_all=args.metrics_all or strict_generation_dir / "metrics_all.json",
        breakdowns=args.breakdowns or strict_generation_dir / "breakdowns.json",
        comparison=args.comparison or strict_generation_dir / "comparison.json",
        error_buckets=args.error_buckets or error_analysis_dir / "error_buckets.json",
        development_error_buckets=args.development_error_buckets
        or error_analysis_dir / "development_error_buckets.json",
        domain_error_summary=args.domain_error_summary
        or error_analysis_dir / "domain_error_summary.json",
        question_type_error_summary=args.question_type_error_summary
        or error_analysis_dir / "question_type_error_summary.json",
        qrels=args.qrels,
        evidence_groups=args.evidence_groups,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
