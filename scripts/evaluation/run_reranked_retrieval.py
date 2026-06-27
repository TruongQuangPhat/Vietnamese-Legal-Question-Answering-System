#!/usr/bin/env python3
"""Run the development-selected reranker on the frozen benchmark."""

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

from scripts.evaluation.run_reranking_ablation import (
    DEFAULT_BENCHMARK_MANIFEST,
    DEFAULT_CHUNKS,
    DEFAULT_DENSE_REFERENCE_DIR,
    DEFAULT_G2_REFERENCE_DIR,
    DEFAULT_G3_REFERENCE_DIR,
    DEFAULT_GROUPS,
    DEFAULT_QRELS,
    DEFAULT_QUERIES,
    DEFAULT_RERANKER_MODEL,
    DEFAULT_REVIEWS,
    DEFAULT_SPARSE_REFERENCE_DIR,
    DEFAULT_SPLIT_MANIFEST,
    DEFAULT_TARGETS,
    _paths_from_args,
    validate_output_dir,
)
from src.evaluation.benchmark.reranking_ablation import (
    RerankingAblationError,
    run_final_reranked_report,
)
from src.evaluation.benchmark.retrieval_baseline import aggregate_case_metrics, build_breakdowns
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.reranker import (
    FlagEmbeddingReranker,
    RerankerError,
    resolve_local_model_path,
)
from src.retrieval.sparse_retriever import SparseBM25Retriever, SparseRetrieverError
from src.retrieval.workflows.common import DEFAULT_CONFIG, load_retrieval_config

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_ABLATION_DIR = Path("artifacts/reports/evaluation/advanced_rag/reranking_ablation")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation/advanced_rag/reranked_retrieval")
DEFAULT_COMPARISON_DIR = Path("artifacts/reports/evaluation/advanced_rag/retrieval_comparison")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the final reranked retrieval CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/run_reranked_retrieval.py",
        description="Run the development-selected reranker on the frozen benchmark.",
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
    parser.add_argument("--ablation-dir", type=Path, default=DEFAULT_ABLATION_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--comparison-dir", type=Path, default=DEFAULT_COMPARISON_DIR)
    parser.add_argument("--dense-reference-dir", type=Path, default=DEFAULT_DENSE_REFERENCE_DIR)
    parser.add_argument("--sparse-reference-dir", type=Path, default=DEFAULT_SPARSE_REFERENCE_DIR)
    parser.add_argument("--g2-reference-dir", type=Path, default=DEFAULT_G2_REFERENCE_DIR)
    parser.add_argument("--g3-reference-dir", type=Path, default=DEFAULT_G3_REFERENCE_DIR)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous final reranked retrieval command."""
    return asyncio.run(run_command(argv))


async def run_command(argv: list[str] | None = None) -> int:
    """Run the selected reranker and write frozen benchmark artifacts."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_output_dir(args.ablation_dir)
        validate_output_dir(args.output_dir)
        validate_output_dir(args.comparison_dir)
        model_path = resolve_local_model_path(args.reranker_model)
        reranker = FlagEmbeddingReranker(
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
        collection_info = await read_collection_info(client, collection_name)
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
        case_results = await run_final_reranked_report(
            paths=_paths_from_args(args),
            ablation_dir=args.ablation_dir,
            comparison_dir=args.comparison_dir,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
            reranker=reranker,
            reranker_device=args.device,
            reranker_dependency="flagembedding==1.4.0",
            dense_config_payload=retrieval_config.model_dump(mode="json"),
            qdrant_collection_name=collection_name,
            qdrant_collection_info=collection_info,
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
        print(f"Reranked retrieval failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()
    if not args.quiet:
        metrics = aggregate_case_metrics(case_results)
        split_metrics = build_breakdowns(case_results)["split"]
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


async def read_collection_info(client: Any, collection_name: str) -> dict[str, Any]:
    """Read collection metadata without mutating Qdrant."""
    collection = await client.get_collection(collection_name)
    return {
        "points_count": getattr(collection, "points_count", None),
        "vectors_count": getattr(collection, "vectors_count", None),
    }


if __name__ == "__main__":
    raise SystemExit(main())
