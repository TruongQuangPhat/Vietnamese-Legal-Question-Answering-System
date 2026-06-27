#!/usr/bin/env python3
"""Thin CLI wrapper for deterministic benchmark split creation."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.loader import load_benchmark_config, load_benchmark_queries
from src.evaluation.benchmark.splitting import create_grouped_split
from src.evaluation.benchmark.validator import load_regression_query_texts
from src.indexing.official_artifacts import write_json_atomic

DEFAULT_CONFIG = Path("configs/evaluation/legal_qa_benchmark.yml")
DEFAULT_REGRESSION_RETRIEVAL = Path("data/eval/manual_retrieval_queries.jsonl")
DEFAULT_REGRESSION_GENERATION = Path("data/eval/manual_naive_rag_generation_queries.jsonl")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the split creation argument parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/create_benchmark_split.py",
        description="Create a deterministic grouped legal QA benchmark split.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--regression-input",
        type=Path,
        action="append",
        default=[DEFAULT_REGRESSION_RETRIEVAL, DEFAULT_REGRESSION_GENERATION],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Create and write a grouped split manifest."""
    args = build_arg_parser().parse_args(argv)
    try:
        config = load_benchmark_config(args.config)
        queries = load_benchmark_queries(args.queries)
        regression_texts = load_regression_query_texts(args.regression_input)
        plan = create_grouped_split(
            queries,
            config=config,
            regression_query_texts=regression_texts,
        )
        write_json_atomic(args.output, plan.manifest.model_dump(mode="json"))
    except (OSError, ValueError) as exc:
        print(f"benchmark split failed to run: {exc}", file=sys.stderr)
        return 2

    print("Legal QA Benchmark Split")
    print(f"Development: {plan.achieved_counts.get('development', 0)}")
    print(f"Held-out test: {plan.achieved_counts.get('held_out_test', 0)}")
    print(f"Warnings: {len(plan.warnings)}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
