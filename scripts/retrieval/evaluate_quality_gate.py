#!/usr/bin/env python3
"""Thin CLI wrapper for the offline quality gate."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.retrieval.quality_gate import (  # noqa: E402
    QualityGateEvaluator,
    write_quality_gate_result,
)

DEFAULT_GENERATION_REPORT = Path(
    "artifacts/reports/retrieval/naive_rag_generation_eval_expanded_with_evidence.json"
)
DEFAULT_VERDICTS = Path("data/eval/manual_faithfulness_verdicts.json")
DEFAULT_POLICY = Path("configs/retrieval/quality_gate.yml")
DEFAULT_OUTPUT = Path("artifacts/reports/retrieval/quality_gate.json")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the quality-gate argument parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/retrieval/evaluate_quality_gate.py",
        description="Evaluate the offline quality gate.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--generation-report", type=Path, default=DEFAULT_GENERATION_REPORT)
    parser.add_argument("--faithfulness-verdicts", type=Path, default=DEFAULT_VERDICTS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--fail-on-partial",
        action="store_true",
        help="Return a non-zero exit code when the gate status is partial.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the offline quality gate."""
    args = build_arg_parser().parse_args(argv)
    try:
        result = QualityGateEvaluator().evaluate_paths(
            generation_report_path=args.generation_report,
            faithfulness_verdicts_path=args.faithfulness_verdicts,
            policy_path=args.policy,
        )
        write_quality_gate_result(args.output, result)
    except (OSError, ValueError) as exc:
        print(f"quality gate failed to run: {exc}", file=sys.stderr)
        return 2

    print("Quality Gate")
    print(f"Status: {result.status}")
    print(f"Hard gate passed: {str(result.hard_gate_passed).lower()}")
    print(f"Quality gate passed: {str(result.quality_gate_passed).lower()}")
    print(f"Hard violations: {len(result.hard_violations)}")
    print(f"Quality violations: {len(result.quality_violations)}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"Output: {args.output}")

    if result.status == "quality_gate_passed":
        return 0
    if result.status == "quality_gate_partial":
        return 1 if args.fail_on_partial else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
