#!/usr/bin/env python3
"""Thin CLI wrapper for legal QA benchmark validation."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.loader import (
    BenchmarkFileSet,
    load_benchmark_config,
    load_benchmark_dataset,
    load_split_manifest,
)
from src.evaluation.benchmark.validator import (
    BenchmarkValidator,
    load_regression_query_texts,
)
from src.indexing.official_artifacts import write_json_atomic

DEFAULT_CONFIG = Path("configs/evaluation/legal_qa_benchmark.yml")
DEFAULT_REGRESSION_RETRIEVAL = Path("data/eval/manual_retrieval_queries.jsonl")
DEFAULT_REGRESSION_GENERATION = Path("data/eval/manual_naive_rag_generation_queries.jsonl")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the benchmark validation argument parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/validate_benchmark.py",
        description="Validate legal QA benchmark construction files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_file_set_args(parser)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--split-manifest", type=Path, default=None)
    parser.add_argument("--corpus-registry", type=Path, default=None)
    parser.add_argument("--processed-chunks", type=Path, default=None)
    parser.add_argument(
        "--regression-input",
        type=Path,
        action="append",
        default=[DEFAULT_REGRESSION_RETRIEVAL, DEFAULT_REGRESSION_GENERATION],
        help="Existing regression JSONL input used read-only for contamination checks.",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run benchmark validation."""
    args = build_arg_parser().parse_args(argv)
    try:
        config = load_benchmark_config(args.config)
        regression_texts = load_regression_query_texts(args.regression_input)
        dataset = load_benchmark_dataset(_file_set_from_args(args))
        split_manifest = load_split_manifest(args.split_manifest) if args.split_manifest else None
        report = BenchmarkValidator(
            config=config,
            regression_query_texts=regression_texts,
        ).validate(
            dataset,
            split_manifest=split_manifest,
            corpus_registry_path=args.corpus_registry,
            processed_chunks_path=args.processed_chunks,
        )
        if args.output:
            write_json_atomic(args.output, report.model_dump(mode="json"))
    except (OSError, ValueError) as exc:
        print(f"benchmark validation failed to run: {exc}", file=sys.stderr)
        return 2

    print("Legal QA Benchmark Validation")
    print(f"Status: {report.status}")
    print(f"Errors: {len(report.errors)}")
    print(f"Warnings: {len(report.warnings)}")
    if args.output:
        print(f"Output: {args.output}")
    return 0 if not report.errors else 1


def _add_file_set_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--legal-targets", type=Path, required=True)
    parser.add_argument("--evidence-judgments", type=Path, required=True)
    parser.add_argument("--evidence-groups", type=Path, required=True)
    parser.add_argument("--review-records", type=Path, required=True)


def _file_set_from_args(args: argparse.Namespace) -> BenchmarkFileSet:
    return BenchmarkFileSet(
        queries=args.queries,
        legal_targets=args.legal_targets,
        evidence_judgments=args.evidence_judgments,
        evidence_groups=args.evidence_groups,
        review_records=args.review_records,
    )


if __name__ == "__main__":
    raise SystemExit(main())
