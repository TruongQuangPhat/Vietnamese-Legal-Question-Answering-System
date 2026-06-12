#!/usr/bin/env python3
"""Run Phase 9A.4 retrieval-side evidence selection smoke tests."""

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
from src.retrieval.evaluation import RetrievalEvaluationError, load_manual_retrieval_queries
from src.retrieval.evidence import ContextAssemblyConfig
from src.retrieval.integration import (
    DEFAULT_CONTEXT_PREVIEW_CHARS,
    SelectionSmokeError,
    SelectionSmokeReport,
    filter_query_records,
    run_selection_smoke_suite,
)
from src.retrieval.models import RetrievalConfig
from src.retrieval.selection import EvidenceSelectionConfig
from src.services.retrieval_service import RetrievalService

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_CONFIG = Path("configs/retrieval/retrieval.yml")
DEFAULT_QUERIES = Path("data/eval/manual_retrieval_queries.jsonl")
DEFAULT_OUTPUT = Path("artifacts/reports/retrieval/selection_smoke_report.json")
PROTECTED_CORPUS_PATHS = (
    REPO_ROOT / "data/raw",
    REPO_ROOT / "data/interim",
    REPO_ROOT / "data/reports",
    REPO_ROOT / "data/processed",
)
REPORTS_ROOT = REPO_ROOT / "artifacts/reports"
RETRIEVAL_REPORTS_ROOT = REPORTS_ROOT / "retrieval"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the selection smoke CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/run_selection_smoke.py",
        description=(
            "Run read-only dense retrieval, evidence assembly, and evidence "
            "selection smoke tests over the manual retrieval dataset."
        ),
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
        help="JSON smoke report path under artifacts/reports/retrieval or /tmp.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also enforce evaluation risk flags during evidence selection.",
    )
    parser.add_argument(
        "--case-id",
        default=None,
        help="Run only one query_id from the manual dataset.",
    )
    parser.add_argument(
        "--max-selected-packets",
        type=int,
        default=5,
        help="Maximum selected evidence packets in each selection result.",
    )
    parser.add_argument(
        "--no-auxiliary-context",
        action="store_true",
        help="Suppress auxiliary parent context in rendered selected context.",
    )
    parser.add_argument(
        "--context-preview-chars",
        type=int,
        default=DEFAULT_CONTEXT_PREVIEW_CHARS,
        help="Maximum rendered context preview characters in the JSON report.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress console summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous selection smoke command."""
    return asyncio.run(run_selection_smoke(argv))


async def run_selection_smoke(argv: list[str] | None = None) -> int:
    """Load dependencies, run the smoke suite, and write a JSON report."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(
            queries_path=args.queries,
            output_path=args.output,
            top_k=args.top_k,
            max_selected_packets=args.max_selected_packets,
            context_preview_chars=args.context_preview_chars,
        )
        config = load_retrieval_config(args.config)
        records = filter_query_records(
            load_manual_retrieval_queries(args.queries),
            case_id=args.case_id,
        )
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
        evidence_config = ContextAssemblyConfig(max_packets=args.top_k)
        selection_config = build_selection_config(
            strict=args.strict,
            max_selected_packets=args.max_selected_packets,
            include_auxiliary_context=not args.no_auxiliary_context,
        )
        report = await run_selection_smoke_suite(
            records,
            service,
            collection_name=collection_name,
            vector_name=config.dense_retrieval.vector_name,
            top_k=args.top_k,
            evidence_config=evidence_config,
            selection_config=selection_config,
            enforce_risk_flags_in_selection=args.strict,
            context_preview_chars=args.context_preview_chars,
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
        SelectionSmokeError,
    ) as exc:
        print(f"Selection smoke failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        print_summary(report)
    return EXIT_SUCCESS


def build_selection_config(
    *,
    strict: bool,
    max_selected_packets: int,
    include_auxiliary_context: bool,
) -> EvidenceSelectionConfig:
    """Build evidence selection settings for smoke mode."""
    if strict:
        return EvidenceSelectionConfig(
            max_selected_packets=max_selected_packets,
            include_auxiliary_context_in_rendered_output=include_auxiliary_context,
        )
    return EvidenceSelectionConfig(
        max_selected_packets=max_selected_packets,
        fallback_on_parent_context_only=False,
        needs_review_on_all_evidence_caution=False,
        include_auxiliary_context_in_rendered_output=include_auxiliary_context,
    )


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
    max_selected_packets: int,
    context_preview_chars: int,
) -> None:
    """Validate CLI path safety and bounded smoke settings."""
    if top_k <= 0:
        raise ValueError("top-k must be positive")
    if max_selected_packets <= 0:
        raise ValueError("max-selected-packets must be positive")
    if context_preview_chars <= 0:
        raise ValueError("context-preview-chars must be positive")
    if is_protected_output(output_path):
        raise ValueError(
            f"refusing protected smoke output path {output_path}; use /tmp "
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


def write_report(path: Path, report: SelectionSmokeReport) -> None:
    """Write the selection smoke report atomically as UTF-8 JSON."""
    write_json_atomic(path, report.model_dump(mode="json"))


def print_summary(report: SelectionSmokeReport) -> None:
    """Print a compact aggregate and per-query smoke summary."""
    aggregate = report.aggregate_summary
    print("Selection Smoke Report")
    print(f"Collection: {report.collection_name}")
    print(f"Vector: {report.vector_name}")
    print(f"Top-k: {report.top_k}")
    print(
        f"Queries: {report.query_count} | Errors: {aggregate.error_count} | "
        f"Decision pass: {aggregate.decision_pass_count}/{report.query_count}"
    )
    for item in report.per_query:
        expected = "pass" if item.decision_passed else "fail"
        decision = item.decision.value if item.decision is not None else "error"
        reasons = "/".join(item.fallback_reasons) if item.fallback_reasons else "none"
        print(
            f"- {item.query_id}: decision={decision}, expected={expected}, "
            f"selected={item.selected_count}, reasons={reasons}"
        )
        if item.errors:
            print(f"  errors={'; '.join(item.errors)}")


if __name__ == "__main__":
    raise SystemExit(main())
