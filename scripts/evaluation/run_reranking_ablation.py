#!/usr/bin/env python3
"""Run development-only reranking ablation over coverage-aware retrieval."""

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

from src.evaluation.benchmark.loader import BenchmarkFileSet
from src.evaluation.benchmark.reranking_ablation import (
    RerankingAblationError,
    RerankingBenchmarkPaths,
    run_development_reranking_ablation,
)
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.reranker import (
    NativeTransformersReranker,
    RerankerError,
    resolve_local_model_path,
)
from src.retrieval.sparse_retriever import SparseBM25Retriever, SparseRetrieverError
from src.retrieval.workflows.common import DEFAULT_CONFIG, load_retrieval_config

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation/advanced_rag/reranking_ablation")
DEFAULT_DENSE_REFERENCE_DIR = Path("artifacts/reports/evaluation/naive_rag_baseline/retrieval")
DEFAULT_SPARSE_REFERENCE_DIR = Path("artifacts/reports/evaluation/advanced_rag/sparse_retrieval")
DEFAULT_G2_REFERENCE_DIR = Path("artifacts/reports/evaluation/advanced_rag/hybrid_retrieval")
DEFAULT_BASE_REFERENCE_DIR = Path(
    "artifacts/reports/evaluation/advanced_rag/coverage_aware_retrieval"
)
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
    """Build the development-only reranking ablation CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/run_reranking_ablation.py",
        description="Run development-only reranking ablation over coverage-aware retrieval.",
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
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="cpu")
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--reranker-batch-size", type=int, default=16)
    parser.add_argument("--reranker-max-length", type=int, default=512)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dense-reference-dir", type=Path, default=DEFAULT_DENSE_REFERENCE_DIR)
    parser.add_argument("--sparse-reference-dir", type=Path, default=DEFAULT_SPARSE_REFERENCE_DIR)
    parser.add_argument("--g2-reference-dir", type=Path, default=DEFAULT_G2_REFERENCE_DIR)
    parser.add_argument(
        "--base-reference-dir",
        type=Path,
        default=DEFAULT_BASE_REFERENCE_DIR,
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous reranking ablation command."""
    return asyncio.run(run_command(argv))


async def run_command(argv: list[str] | None = None) -> int:
    """Construct read-only retrievers and run development ablation."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_output_dir(args.output_dir)
        model_path = resolve_local_model_path(args.reranker_model)
        reranker = NativeTransformersReranker(
            model_name=args.reranker_model,
            model_path=model_path,
            device=args.device,
            batch_size=args.reranker_batch_size,
            max_length=args.reranker_max_length,
        )
        retrieval_config = load_retrieval_config(args.config)
        collection_name = args.collection_name or retrieval_config.qdrant.collection_name
        url = args.url or retrieval_config.qdrant.url
        client = build_qdrant_client(
            url=url,
            timeout_seconds=retrieval_config.qdrant.timeout_seconds,
        )
        await client.get_collection(collection_name)
        embedding_model = BgeM3EmbeddingModel(
            model_name=retrieval_config.embedding.model_name,
            model_revision=retrieval_config.embedding.model_revision,
            device=args.device,
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
            default_top_k=50,
            embedding_batch_size=retrieval_config.embedding.batch_size,
        )
        sparse_retriever = SparseBM25Retriever.from_jsonl(args.chunks, default_top_k=50)
        report = await run_development_reranking_ablation(
            paths=_paths_from_args(args),
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
            reranker=reranker,
            reranker_device=args.device,
            reranker_dependency="transformers==5.10.2; torch",
            qdrant_collection_name=collection_name,
            vector_name=retrieval_config.dense_retrieval.vector_name,
            embedding_model=retrieval_config.embedding.model_name,
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
        RerankerError,
        RerankingAblationError,
    ) as exc:
        print(f"Reranking ablation failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()
    if not args.quiet:
        print(f"Decision: {report['decision']}")
        print(f"Selected config: {report['selected_config_id']}")
        print(f"Artifacts: {args.output_dir}")
    return EXIT_SUCCESS


def _paths_from_args(args: argparse.Namespace) -> RerankingBenchmarkPaths:
    return RerankingBenchmarkPaths(
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
        g2_reference_dir=args.g2_reference_dir,
        base_reference_dir=args.base_reference_dir,
        output_dir=args.output_dir,
    )


def validate_output_dir(output_dir: Path) -> None:
    """Reject outputs outside the approved evaluation report tree."""
    resolved = output_dir.expanduser().resolve()
    if resolved != EVALUATION_REPORTS_ROOT and EVALUATION_REPORTS_ROOT not in resolved.parents:
        raise ValueError("output-dir must be under artifacts/reports/evaluation")


if __name__ == "__main__":
    raise SystemExit(main())
