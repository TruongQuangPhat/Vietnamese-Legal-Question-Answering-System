"""Workflow for Phase 9A.1 dense retrieval sanity evaluation."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.evaluation import (
    DEFAULT_EVAL_CUTOFFS,
    DenseRetrievalEvaluationReport,
    RetrievalEvaluationError,
    evaluate_dense_retrieval,
    load_manual_retrieval_queries,
)
from src.retrieval.workflows.common import (
    DEFAULT_CONFIG,
    DEFAULT_QUERIES,
    is_protected_output,
    is_protected_query_path,
    load_retrieval_config,
    write_json_report,
)
from src.services.retrieval_service import RetrievalService

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT = Path("artifacts/reports/retrieval/dense_retrieval_eval.json")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the dense retrieval evaluation parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/retrieval/evaluate_dense_retrieval.py",
        description="Run read-only dense retrieval evaluation over a manual JSONL dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Phase 9A retrieval configuration.",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERIES,
        help="Manual retrieval query JSONL dataset.",
    )
    parser.add_argument("--collection-name", default=None, help="Existing Qdrant collection.")
    parser.add_argument("--url", default=None, help="Qdrant HTTP URL.")
    parser.add_argument("--top-k", type=int, default=20, help="Dense results per query.")
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default=None,
        help="Device used by the BGE-M3 query embedder.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON evaluation report path under artifacts/reports/retrieval or /tmp.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress console summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous evaluation command."""
    return asyncio.run(run_evaluation(argv))


async def run_evaluation(argv: list[str] | None = None) -> int:
    """Load dependencies, evaluate dense retrieval, and write a JSON report."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(
            queries_path=args.queries,
            output_path=args.output,
            top_k=args.top_k,
        )
        config = load_retrieval_config(args.config)
        queries = load_manual_retrieval_queries(args.queries)
        collection_name = args.collection_name or config.qdrant.collection_name
        url = args.url or config.qdrant.url
        device = args.device or config.embedding.device

        client = build_qdrant_client(
            url=url,
            timeout_seconds=config.qdrant.timeout_seconds,
        )
        embedding_model = BgeM3EmbeddingModel(
            model_name=config.embedding.model_name,
            model_revision=config.embedding.model_revision,
            device=device,
            normalize_embeddings=config.embedding.normalize_embeddings,
            max_length=config.embedding.max_length,
            dense_vector_name=config.dense_retrieval.vector_name,
        )
        retriever = DenseRetriever(
            qdrant_client=client,
            embedding_model=embedding_model,
            collection_name=collection_name,
            dense_vector_name=config.dense_retrieval.vector_name,
            expected_vector_dim=config.dense_retrieval.expected_vector_dim,
            default_top_k=args.top_k,
            embedding_batch_size=config.embedding.batch_size,
        )
        service = RetrievalService(retriever=retriever)
        report = await evaluate_dense_retrieval(
            service,
            queries,
            collection_name=collection_name,
            vector_name=config.dense_retrieval.vector_name,
            top_k=args.top_k,
            cutoffs=DEFAULT_EVAL_CUTOFFS,
        )
        write_report(args.output, report)
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        EmbeddingModelError,
        QdrantCollectionError,
        DenseRetrieverError,
        RetrievalEvaluationError,
    ) as exc:
        print(f"Dense retrieval evaluation failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        print_summary(report)
    return EXIT_SUCCESS


def validate_cli_arguments(
    *,
    queries_path: Path,
    output_path: Path,
    top_k: int,
) -> None:
    """Validate CLI paths and bounded evaluation settings."""
    if top_k <= 0:
        raise ValueError("top-k must be positive")
    if is_protected_output(output_path):
        raise ValueError(
            f"refusing protected evaluation output path {output_path}; use /tmp "
            "or artifacts/reports/retrieval"
        )
    if is_protected_query_path(queries_path):
        raise ValueError(f"refusing protected query dataset path {queries_path}")


def write_report(path: Path, report: DenseRetrievalEvaluationReport) -> None:
    """Write the evaluation report atomically as UTF-8 JSON."""
    write_json_report(path, report.model_dump(mode="json"))


def print_summary(report: DenseRetrievalEvaluationReport) -> None:
    """Print a compact aggregate and per-query evaluation summary."""
    metrics = report.aggregate_metrics
    print(f"Collection: {report.collection_name}")
    print(f"Vector: {report.vector_name}")
    print(f"Top-k: {report.top_k}")
    print(f"Queries: {metrics.query_count} | Errors: {metrics.error_count}")
    print(
        "Exact recall: "
        f"@5={metrics.recall_at_5:.3f} "
        f"@10={metrics.recall_at_10:.3f} "
        f"@20={metrics.recall_at_20:.3f}"
    )
    print(
        "Article hit: "
        f"@5={metrics.article_hit_at_5:.3f} "
        f"@10={metrics.article_hit_at_10:.3f} "
        f"@20={metrics.article_hit_at_20:.3f}"
    )
    print(f"MRR@20: {metrics.mrr_at_20:.3f}")
    print(f"Risk flags: {metrics.risk_flag_count}")
    for item in report.per_query:
        best_exact = item.best_exact_rank if item.best_exact_rank is not None else "none"
        best_article = item.best_article_rank if item.best_article_rank is not None else "none"
        best_clause = item.clause_match_rank if item.clause_match_rank is not None else "none"
        best_point = item.point_match_rank if item.point_match_rank is not None else "none"
        exact_depth = item.exact_match_depth or "none"
        print(
            f"- {item.query_id}: exact_rank={best_exact}, "
            f"exact_depth={exact_depth}, article_rank={best_article}, "
            f"clause_rank={best_clause}, point_rank={best_point}, "
            f"risks={len(item.risk_flags)}"
        )
