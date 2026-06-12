#!/usr/bin/env python3
"""Run Phase 9A.1 dense retrieval sanity evaluation and evidence-risk audit."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.official_artifacts import write_json_atomic
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.evaluation import (
    DEFAULT_EVAL_CUTOFFS,
    DenseRetrievalEvaluationReport,
    RetrievalEvaluationError,
    evaluate_dense_retrieval,
    load_manual_retrieval_queries,
)
from src.retrieval.models import RetrievalConfig
from src.services.retrieval_service import RetrievalService

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_CONFIG = Path("configs/retrieval/retrieval.yml")
DEFAULT_QUERIES = Path("data/eval/manual_retrieval_queries.jsonl")
DEFAULT_OUTPUT = Path("artifacts/reports/retrieval/dense_retrieval_eval.json")
PROTECTED_CORPUS_PATHS = (
    REPO_ROOT / "data/raw",
    REPO_ROOT / "data/interim",
    REPO_ROOT / "data/reports",
    REPO_ROOT / "data/processed",
)
REPORTS_ROOT = REPO_ROOT / "artifacts/reports"
RETRIEVAL_REPORTS_ROOT = REPORTS_ROOT / "retrieval"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the dense retrieval evaluation parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluate_dense_retrieval.py",
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


def load_retrieval_config(path: Path) -> RetrievalConfig:
    """Load and validate the Phase 9A retrieval YAML configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("retrieval config root must be a YAML object")
    return RetrievalConfig.model_validate(payload)


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


def is_protected_output(path: Path) -> bool:
    """Return whether a report output path violates repository boundaries."""
    resolved = path.expanduser().resolve()
    if any(
        resolved == protected or protected in resolved.parents
        for protected in PROTECTED_CORPUS_PATHS
    ):
        return True
    if resolved == REPORTS_ROOT or REPORTS_ROOT in resolved.parents:
        return not (
            resolved == RETRIEVAL_REPORTS_ROOT or RETRIEVAL_REPORTS_ROOT in resolved.parents
        )
    return False


def is_protected_query_path(path: Path) -> bool:
    """Return whether the query dataset is under a protected corpus path."""
    resolved = path.expanduser().resolve()
    return any(
        resolved == protected or protected in resolved.parents
        for protected in PROTECTED_CORPUS_PATHS
    )


def write_report(path: Path, report: DenseRetrievalEvaluationReport) -> None:
    """Write the evaluation report atomically as UTF-8 JSON."""
    write_json_atomic(path, report.model_dump(mode="json"))


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


if __name__ == "__main__":
    raise SystemExit(main())
