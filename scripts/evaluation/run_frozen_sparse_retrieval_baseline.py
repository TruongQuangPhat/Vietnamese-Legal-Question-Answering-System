#!/usr/bin/env python3
"""Run sparse BM25 retrieval metrics on the frozen legal QA benchmark."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.fingerprinting import (
    add_benchmark_output_policy_argument,
    validate_benchmark_output_dir,
)
from src.evaluation.benchmark.loader import BenchmarkFileSet
from src.evaluation.benchmark.retrieval_baseline import aggregate_case_metrics, build_breakdowns
from src.evaluation.benchmark.sparse_retrieval_baseline import (
    DEFAULT_BM25_B,
    DEFAULT_BM25_K1,
    SparseBenchmarkConfig,
    SparseBenchmarkPaths,
    run_sparse_benchmark,
)
from src.retrieval.sparse_retriever import SparseRetrieverError

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation/advanced_rag/sparse_retrieval")
DEFAULT_DENSE_REFERENCE_DIR = Path("artifacts/reports/evaluation/naive_rag_baseline/retrieval")
DEFAULT_CHUNKS = Path("data/processed/legal_chunks.jsonl")
DEFAULT_QUERIES = Path("data/eval/legal_qa_benchmark/benchmark_queries.jsonl")
DEFAULT_TARGETS = Path("data/eval/legal_qa_benchmark/benchmark_targets.jsonl")
DEFAULT_QRELS = Path("data/eval/legal_qa_benchmark/benchmark_qrels.jsonl")
DEFAULT_GROUPS = Path("data/eval/legal_qa_benchmark/evidence_groups.jsonl")
DEFAULT_REVIEWS = Path("data/eval/legal_qa_benchmark/review_records.jsonl")
DEFAULT_SPLIT_MANIFEST = Path("data/eval/legal_qa_benchmark/split_manifest.json")
DEFAULT_BENCHMARK_MANIFEST = Path("data/eval/legal_qa_benchmark/benchmark_manifest.json")
EVALUATION_REPORTS_ROOT = REPO_ROOT / "artifacts/reports/evaluation"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the frozen sparse retrieval baseline CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/run_frozen_sparse_retrieval_baseline.py",
        description="Run offline sparse BM25 retrieval over the frozen legal QA benchmark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--legal-targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--evidence-judgments", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--evidence-groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument("--review-records", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--split-manifest", type=Path, default=DEFAULT_SPLIT_MANIFEST)
    parser.add_argument("--benchmark-manifest", type=Path, default=DEFAULT_BENCHMARK_MANIFEST)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--k1", type=float, default=DEFAULT_BM25_K1)
    parser.add_argument("--b", type=float, default=DEFAULT_BM25_B)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dense-reference-dir", type=Path, default=DEFAULT_DENSE_REFERENCE_DIR)
    add_benchmark_output_policy_argument(parser)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous frozen sparse retrieval baseline command."""
    return asyncio.run(run_baseline(argv))


async def run_baseline(argv: list[str] | None = None) -> int:
    """Load the frozen benchmark, run sparse retrieval, and write artifacts."""
    args = build_arg_parser().parse_args(argv)
    try:
        validate_cli_arguments(args.output_dir, output_policy=args.output_policy)
        config = SparseBenchmarkConfig(top_k=args.top_k, k1=args.k1, b=args.b)
        paths = SparseBenchmarkPaths(
            file_set=BenchmarkFileSet(
                queries=args.queries,
                legal_targets=args.legal_targets,
                evidence_judgments=args.evidence_judgments,
                evidence_groups=args.evidence_groups,
                review_records=args.review_records,
            ),
            split_manifest=args.split_manifest,
            benchmark_manifest=args.benchmark_manifest,
            chunk_source=args.chunks,
            output_dir=args.output_dir,
            dense_reference_dir=args.dense_reference_dir,
        )
        case_results = await run_sparse_benchmark(
            paths=paths,
            config=config,
            command=["python", *sys.argv],
        )
    except (OSError, UnicodeError, ValueError, ValidationError, SparseRetrieverError) as exc:
        print(f"Frozen sparse retrieval baseline failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    if not args.quiet:
        metrics = aggregate_case_metrics(case_results)
        split_metrics = build_breakdowns(case_results)["split"]
        print("Retrieval method: sparse_bm25")
        print(f"Top-k: {args.top_k}")
        print(f"Queries: {metrics['query_count']} | Errors: {metrics['retrieval_error_count']}")
        for split_name, split_data in split_metrics.items():
            print(
                f"{split_name}: Recall@10={split_data['recall_at_10']:.3f} "
                f"MRR@10={split_data['mrr_at_10']:.3f} "
                f"NDCG@10={split_data['ndcg_at_10']:.3f} "
                f"GroupCoverage@10={split_data['evidence_group_coverage_at_10']:.3f}"
            )
        print(f"Artifacts: {args.output_dir}")
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


if __name__ == "__main__":
    raise SystemExit(main())
