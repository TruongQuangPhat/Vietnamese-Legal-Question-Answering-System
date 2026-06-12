#!/usr/bin/env python3
"""Run a safe read-only Phase 9A dense retrieval query."""

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
from src.retrieval.models import (
    RetrievalConfig,
    RetrievalFilters,
)
from src.services.retrieval_service import RetrievalService

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_CONFIG = Path("configs/retrieval/retrieval.yml")
PROTECTED_CORPUS_PATHS = (
    REPO_ROOT / "data/raw",
    REPO_ROOT / "data/interim",
    REPO_ROOT / "data/reports",
    REPO_ROOT / "data/processed",
)
REPORTS_ROOT = REPO_ROOT / "artifacts/reports"
RETRIEVAL_REPORTS_ROOT = REPORTS_ROOT / "retrieval"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the Phase 9A dense retrieval CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/run_dense_retrieval.py",
        description="Run one read-only BGE-M3 dense retrieval query against Qdrant.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Phase 9A retrieval configuration.",
    )
    parser.add_argument("--query", required=True, help="Vietnamese legal query text.")
    parser.add_argument(
        "--collection-name",
        default=None,
        help="Existing Qdrant collection to query.",
    )
    parser.add_argument("--url", default=None, help="Qdrant HTTP URL.")
    parser.add_argument("--top-k", type=int, default=None, help="Number of dense hits.")
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default=None,
        help="Device used by the BGE-M3 query embedder.",
    )
    parser.add_argument("--law-id", default=None, help="Exact law_id payload filter.")
    parser.add_argument("--chunk-kind", default=None, help="Exact chunk_kind payload filter.")
    parser.add_argument(
        "--level",
        choices=["article", "clause", "point"],
        default=None,
        help="Exact legal chunk level filter.",
    )
    parser.add_argument(
        "--article-number",
        default=None,
        help="Exact article_number payload filter.",
    )
    parser.add_argument(
        "--source-domain",
        default=None,
        help="Exact source_domain payload filter.",
    )
    parser.add_argument(
        "--exclude-repealed",
        action="store_true",
        help="Exclude chunks flagged as empty or repealed in indexed metadata.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON report path under artifacts/reports/retrieval or /tmp.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=280,
        help="Maximum text preview characters in console and JSON output.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress console summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous retrieval command."""
    return asyncio.run(run_retrieval(argv))


async def run_retrieval(argv: list[str] | None = None) -> int:
    """Load dependencies, execute read-only retrieval, and optionally write JSON."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(
            query=args.query,
            top_k=args.top_k,
            output_path=args.output,
            preview_chars=args.preview_chars,
        )
        config = load_retrieval_config(args.config)
        top_k = args.top_k or config.dense_retrieval.top_k
        collection_name = args.collection_name or config.qdrant.collection_name
        url = args.url or config.qdrant.url
        device = args.device or config.embedding.device
        validate_cli_arguments(
            query=args.query,
            top_k=top_k,
            output_path=args.output,
            preview_chars=args.preview_chars,
        )

        filters = RetrievalFilters(
            law_id=args.law_id,
            chunk_kind=args.chunk_kind,
            level=args.level,
            article_number=args.article_number,
            source_domain=args.source_domain,
            exclude_repealed=args.exclude_repealed,
        )
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
            default_top_k=top_k,
            embedding_batch_size=config.embedding.batch_size,
        )
        service = RetrievalService(retriever=retriever)
        result = await service.retrieve(
            query=args.query,
            top_k=top_k,
            collection_name=collection_name,
            filters=filters,
        )
        report = build_cli_report(result, preview_chars=args.preview_chars)
        if args.output is not None:
            write_json_atomic(args.output, report)
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        EmbeddingModelError,
        QdrantCollectionError,
        DenseRetrieverError,
    ) as exc:
        print(f"Dense retrieval failed: {exc}", file=sys.stderr)
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
    query: str,
    top_k: int | None,
    output_path: Path | None,
    preview_chars: int,
) -> None:
    """Validate CLI safety and bounded retrieval settings."""
    if not query.strip():
        raise ValueError("query must not be blank")
    if top_k is not None and top_k <= 0:
        raise ValueError("top-k must be positive")
    if preview_chars <= 0:
        raise ValueError("preview chars must be positive")
    if output_path is not None and is_protected_output(output_path):
        raise ValueError(
            f"refusing protected retrieval output path {output_path}; use /tmp "
            "or artifacts/reports/retrieval"
        )


def is_protected_output(path: Path) -> bool:
    """Return whether a retrieval JSON path violates repository boundaries."""
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


def build_cli_report(result: Any, *, preview_chars: int) -> dict[str, Any]:
    """Build the compact JSON report emitted by the manual retrieval CLI."""
    return {
        "query": result.query,
        "collection_name": result.collection_name,
        "vector_name": result.vector_name,
        "top_k": result.top_k,
        "elapsed_ms": result.elapsed_ms,
        "query_vector_dimension": result.query_vector_dimension,
        "filters": result.filters.model_dump(mode="json"),
        "result_count": len(result.results),
        "issues": [issue.model_dump(mode="json") for issue in result.issues],
        "results": [
            {
                "rank": chunk.rank,
                "score": chunk.score,
                "chunk_id": chunk.chunk_id,
                "citation": chunk.citation,
                "law_id": chunk.law_id,
                "law_name": chunk.law_name,
                "law_title": chunk.law_name,
                "level": chunk.level,
                "chunk_kind": chunk.chunk_kind,
                "article_number": chunk.article_number,
                "clause_number": chunk.clause_number,
                "point_label": chunk.point_label,
                "source_url": chunk.source_url,
                "source_domain": chunk.source_domain,
                "text_preview": preview(chunk.text, preview_chars),
                "parent_text_preview": preview(chunk.parent_text, preview_chars),
                "metadata": chunk.metadata,
                "warnings": chunk.warnings,
                "is_empty_or_repealed": chunk.is_empty_or_repealed,
                "is_source_unit_repealed": chunk.is_source_unit_repealed,
                "embedding_model": chunk.embedding_model,
                "indexing_run_id": chunk.indexing_run_id,
                "issues": [issue.model_dump(mode="json") for issue in chunk.issues],
            }
            for chunk in result.results
        ],
    }


def print_summary(report: dict[str, Any]) -> None:
    """Print a compact human-readable retrieval summary."""
    print(f"Query: {report['query']}")
    print(f"Collection: {report['collection_name']}")
    print(f"Top-k: {report['top_k']} | Results: {report['result_count']}")
    print(f"Elapsed: {report['elapsed_ms']:.2f} ms")
    for item in report["results"]:
        print("")
        print(f"#{item['rank']} score={item['score']:.6f} chunk_id={item['chunk_id']}")
        if item["citation"]:
            print(f"Citation: {item['citation']}")
        law_label = item["law_name"] or item["law_id"]
        if law_label:
            print(f"Law: {law_label}")
        hierarchy = _hierarchy_label(item)
        if hierarchy:
            print(f"Hierarchy: {hierarchy}")
        if item["source_url"]:
            print(f"Source: {item['source_url']}")
        if item["text_preview"]:
            print(f"Text: {item['text_preview']}")
        if item["issues"]:
            print(f"Issues: {len(item['issues'])}")
    if report["issues"]:
        print("")
        print(f"Retrieval issues: {len(report['issues'])}")


def preview(text: str | None, max_chars: int) -> str | None:
    """Return a whitespace-normalized preview without mutating source text."""
    if text is None:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _hierarchy_label(item: dict[str, Any]) -> str:
    parts: list[str] = []
    if item["article_number"]:
        parts.append(f"Điều {item['article_number']}")
    if item["clause_number"]:
        parts.append(f"Khoản {item['clause_number']}")
    if item["point_label"]:
        parts.append(f"Điểm {item['point_label']}")
    return ", ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
