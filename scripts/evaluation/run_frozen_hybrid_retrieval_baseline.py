#!/usr/bin/env python3
"""Run hybrid dense+sparse RRF retrieval on the frozen legal QA benchmark."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.hybrid_retrieval_baseline import (
    HybridBenchmarkConfig,
    HybridBenchmarkPaths,
    run_hybrid_benchmark,
)
from src.evaluation.benchmark.loader import BenchmarkFileSet
from src.evaluation.benchmark.retrieval_baseline import aggregate_case_metrics, build_breakdowns
from src.evaluation.qdrant import build_evaluation_qdrant_client
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.qdrant_collection import QdrantCollectionError
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.sparse_retriever import SparseBM25Retriever, SparseRetrieverError
from src.retrieval.workflows.common import DEFAULT_CONFIG, load_retrieval_config

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation/advanced_rag/hybrid_retrieval")
DEFAULT_COMPARISON_DIR = Path("artifacts/reports/evaluation/advanced_rag/retrieval_comparison")
DEFAULT_DENSE_REFERENCE_DIR = Path("artifacts/reports/evaluation/naive_rag_baseline/retrieval")
DEFAULT_SPARSE_REFERENCE_DIR = Path("artifacts/reports/evaluation/advanced_rag/sparse_retrieval")
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
    """Build the frozen hybrid retrieval baseline CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/run_frozen_hybrid_retrieval_baseline.py",
        description="Run read-only dense + offline sparse RRF retrieval over the frozen benchmark.",
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
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--collection-name", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default=None)
    parser.add_argument("--dense-candidate-k", type=int, default=50)
    parser.add_argument("--sparse-candidate-k", type=int, default=50)
    parser.add_argument("--final-top-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--comparison-dir", type=Path, default=DEFAULT_COMPARISON_DIR)
    parser.add_argument("--dense-reference-dir", type=Path, default=DEFAULT_DENSE_REFERENCE_DIR)
    parser.add_argument("--sparse-reference-dir", type=Path, default=DEFAULT_SPARSE_REFERENCE_DIR)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous frozen hybrid retrieval baseline command."""
    return asyncio.run(run_baseline(argv))


async def run_baseline(argv: list[str] | None = None) -> int:
    """Load the frozen benchmark, run hybrid retrieval, and write artifacts."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(args.output_dir)
        validate_cli_arguments(args.comparison_dir)
        retrieval_config = load_retrieval_config(args.config)
        collection_name = args.collection_name or retrieval_config.qdrant.collection_name
        url = args.url or retrieval_config.qdrant.url
        device = args.device or retrieval_config.embedding.device
        config = HybridBenchmarkConfig(
            dense_candidate_k=args.dense_candidate_k,
            sparse_candidate_k=args.sparse_candidate_k,
            final_top_k=args.final_top_k,
            rrf_k=args.rrf_k,
        )

        client = build_evaluation_qdrant_client(
            url=url,
            timeout_seconds=retrieval_config.qdrant.timeout_seconds,
        )
        collection_info = await read_collection_info(client, collection_name)
        embedding_model = BgeM3EmbeddingModel(
            model_name=retrieval_config.embedding.model_name,
            model_revision=retrieval_config.embedding.model_revision,
            device=device,
            normalize_embeddings=retrieval_config.embedding.normalize_embeddings,
            max_length=retrieval_config.embedding.max_length,
            dense_vector_name=retrieval_config.dense_retrieval.vector_name,
        )
        dense_retriever = DenseRetriever(
            qdrant_client=client,
            embedding_model=embedding_model,
            collection_name=collection_name,
            dense_vector_name=retrieval_config.dense_retrieval.vector_name,
            expected_vector_dim=retrieval_config.dense_retrieval.expected_vector_dim,
            default_top_k=config.dense_candidate_k,
            embedding_batch_size=retrieval_config.embedding.batch_size,
        )
        sparse_retriever = SparseBM25Retriever.from_jsonl(
            args.chunks,
            k1=config.bm25_k1,
            b=config.bm25_b,
            default_top_k=config.sparse_candidate_k,
        )

        case_results = await run_hybrid_benchmark(
            paths=HybridBenchmarkPaths(
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
                dense_config=args.config,
                dense_reference_dir=args.dense_reference_dir,
                sparse_reference_dir=args.sparse_reference_dir,
                output_dir=args.output_dir,
                comparison_dir=args.comparison_dir,
            ),
            config=config,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
            dense_config_payload=retrieval_config.model_dump(mode="json"),
            qdrant_collection_name=collection_name,
            qdrant_collection_info=collection_info,
            embedding_model=retrieval_config.embedding.model_name,
            vector_name=retrieval_config.dense_retrieval.vector_name,
            command=["python", *sys.argv],
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        ValidationError,
        EmbeddingModelError,
        QdrantCollectionError,
        DenseRetrieverError,
        SparseRetrieverError,
    ) as exc:
        print(f"Frozen hybrid retrieval baseline failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        metrics = aggregate_case_metrics(case_results)
        split_metrics = build_breakdowns(case_results)["split"]
        print("Retrieval method: hybrid_dense_sparse_rrf")
        print(f"Collection: {collection_name}")
        print(f"Vector: {retrieval_config.dense_retrieval.vector_name}")
        print(
            "Candidates: "
            f"dense={args.dense_candidate_k} sparse={args.sparse_candidate_k} "
            f"final={args.final_top_k} rrf_k={args.rrf_k}"
        )
        print(f"Queries: {metrics['query_count']} | Errors: {metrics['retrieval_error_count']}")
        for split_name, split_data in split_metrics.items():
            print(
                f"{split_name}: Recall@10={split_data['recall_at_10']:.3f} "
                f"MRR@10={split_data['mrr_at_10']:.3f} "
                f"NDCG@10={split_data['ndcg_at_10']:.3f} "
                f"GroupCoverage@10={split_data['evidence_group_coverage_at_10']:.3f}"
            )
        print(f"Artifacts: {args.output_dir}")
        print(f"Comparison: {args.comparison_dir}")
    return EXIT_SUCCESS


def validate_cli_arguments(output_dir: Path) -> None:
    """Reject output paths outside the approved evaluation report area."""
    resolved = output_dir.expanduser().resolve()
    if resolved != EVALUATION_REPORTS_ROOT and EVALUATION_REPORTS_ROOT not in resolved.parents:
        raise ValueError(
            "output-dir must be under artifacts/reports/evaluation for this benchmark run"
        )


async def read_collection_info(client: Any, collection_name: str) -> dict[str, Any]:
    """Read Qdrant collection metadata without mutating the collection."""
    collection = await client.get_collection(collection_name)
    points_count = getattr(collection, "points_count", None)
    vectors_count = getattr(collection, "vectors_count", None)
    config = getattr(collection, "config", None)
    params = getattr(config, "params", None)
    vectors = getattr(params, "vectors", None)
    vector_summary: dict[str, Any] = {}
    if isinstance(vectors, dict):
        for name, params_value in vectors.items():
            vector_summary[str(name)] = {
                "size": getattr(params_value, "size", None),
                "distance": str(getattr(params_value, "distance", "")),
            }
    elif vectors is not None:
        vector_summary["default"] = {
            "size": getattr(vectors, "size", None),
            "distance": str(getattr(vectors, "distance", "")),
        }
    return {
        "points_count": points_count,
        "vectors_count": vectors_count,
        "vectors": vector_summary,
    }


if __name__ == "__main__":
    raise SystemExit(main())
