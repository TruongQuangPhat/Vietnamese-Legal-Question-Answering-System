#!/usr/bin/env python3
"""Thin CLI wrapper for legal QA benchmark freeze manifest creation."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.fingerprinting import create_benchmark_manifest
from src.evaluation.benchmark.loader import BenchmarkFileSet, load_benchmark_config

DEFAULT_CONFIG = Path("configs/evaluation/legal_qa_benchmark.yml")
DEFAULT_CORPUS_REGISTRY = Path("configs/laws/corpus_registry.yml")
DEFAULT_PROCESSED_CHUNKS = Path("data/processed/legal_chunks.jsonl")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the freeze-manifest argument parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/freeze_benchmark.py",
        description="Validate and freeze a legal QA benchmark manifest.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--legal-targets", type=Path, required=True)
    parser.add_argument("--evidence-judgments", type=Path, required=True)
    parser.add_argument("--evidence-groups", type=Path, required=True)
    parser.add_argument("--review-records", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--corpus-registry", type=Path, default=DEFAULT_CORPUS_REGISTRY)
    parser.add_argument("--processed-chunks", type=Path, default=DEFAULT_PROCESSED_CHUNKS)
    parser.add_argument("--change-log", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Create a frozen benchmark manifest."""
    args = build_arg_parser().parse_args(argv)
    try:
        config = load_benchmark_config(args.config)
        manifest = create_benchmark_manifest(
            file_set=BenchmarkFileSet(
                queries=args.queries,
                legal_targets=args.legal_targets,
                evidence_judgments=args.evidence_judgments,
                evidence_groups=args.evidence_groups,
                review_records=args.review_records,
            ),
            config=config,
            split_manifest_path=args.split_manifest,
            corpus_registry_path=args.corpus_registry,
            processed_chunks_path=args.processed_chunks,
            output_path=args.output,
            change_log=args.change_log,
        )
    except (OSError, ValueError) as exc:
        print(f"benchmark freeze failed to run: {exc}", file=sys.stderr)
        return 2

    print("Legal QA Benchmark Freeze")
    print(f"Benchmark version: {manifest.benchmark_version}")
    print(f"Review status: {manifest.review_status}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
