#!/usr/bin/env python3
"""Run offline strict generation error analysis."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.fingerprinting import (
    add_benchmark_output_policy_argument,
    validate_benchmark_output_dir,
)
from src.evaluation.benchmark.strict_generation_error_analysis import (
    StrictGenerationErrorAnalysisError,
    StrictGenerationErrorAnalysisPaths,
    run_strict_generation_error_analysis,
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_INPUT_DIR = Path("artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation")
DEFAULT_OUTPUT_DIR = Path(
    "artifacts/reports/evaluation/advanced_rag/strict_generation_error_analysis"
)
EVALUATION_REPORTS_ROOT = REPO_ROOT / "artifacts/reports/evaluation"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the offline strict generation error-analysis parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/analyze_strict_generation_errors.py",
        description="Analyze strict generation evaluation errors from existing artifacts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--case-results", type=Path, default=None)
    parser.add_argument("--metrics-all", type=Path, default=None)
    parser.add_argument("--breakdowns", type=Path, default=None)
    parser.add_argument("--comparison", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    add_benchmark_output_policy_argument(parser)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run offline strict generation error analysis."""
    args = build_arg_parser().parse_args(argv)
    try:
        validate_cli_arguments(args.output_dir, output_policy=args.output_policy)
        analysis = run_strict_generation_error_analysis(_paths_from_args(args))
    except (OSError, ValueError, StrictGenerationErrorAnalysisError) as exc:
        print(f"strict generation error analysis failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    if not args.quiet:
        input_summary = analysis["input_summary"]
        bottleneck = analysis["bottleneck_diagnosis"]
        print("Strict Generation Error Analysis")
        print(f"Cases: {input_summary['case_count']}")
        print(f"Development cases: {input_summary['development_case_count']}")
        print(f"Held-out reporting cases: {input_summary['held_out_test_case_count']}")
        print(f"Primary bottleneck: {bottleneck['primary_bottleneck']}")
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


def _paths_from_args(args: argparse.Namespace) -> StrictGenerationErrorAnalysisPaths:
    input_dir = args.input_dir
    return StrictGenerationErrorAnalysisPaths(
        case_results=args.case_results or input_dir / "case_results.jsonl",
        metrics_all=args.metrics_all or input_dir / "metrics_all.json",
        breakdowns=args.breakdowns or input_dir / "breakdowns.json",
        comparison=args.comparison or input_dir / "comparison.json",
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
