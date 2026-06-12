"""Workflow for Phase 9B fallback-aware Naive RAG single-query generation."""

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
from src.retrieval.evaluation import ExpectedTarget, load_manual_retrieval_queries
from src.retrieval.evidence import ContextAssemblyConfig
from src.retrieval.generation import RagAnswerResult, RagGenerationConfig
from src.retrieval.llm_client import LLMClientError, OpenRouterLLMClient
from src.retrieval.openrouter_config import load_project_dotenv, resolve_openrouter_settings
from src.retrieval.rag_pipeline import run_naive_rag
from src.retrieval.selection import EvidenceSelectionConfig
from src.retrieval.workflows.common import (
    DEFAULT_CONFIG,
    DEFAULT_QUERIES,
    is_protected_output,
    load_retrieval_config,
    write_json_report,
)
from src.services.retrieval_service import RetrievalService

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT = Path("artifacts/reports/retrieval/naive_rag_single_query.json")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the fallback-aware Naive RAG CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/run_naive_rag.py",
        description="Run one fallback-aware Naive RAG legal QA query.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--query", required=True, help="Vietnamese legal query text.")
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
        "--provider",
        choices=["openrouter"],
        default="openrouter",
        help="LLM provider.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model override, for example google/gemini-2.5-flash.",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON result path under artifacts/reports/retrieval or /tmp.",
    )
    parser.add_argument(
        "--strict-citations",
        action="store_true",
        help="Return fallback when generated output cites unknown [E#] IDs.",
    )
    parser.add_argument(
        "--no-auxiliary-context",
        action="store_true",
        help="Suppress auxiliary parent context in the generation prompt.",
    )
    parser.add_argument(
        "--manual-queries",
        type=Path,
        default=DEFAULT_QUERIES,
        help="Optional manual query dataset used for exact target hints when the query matches.",
    )
    parser.add_argument(
        "--disable-manual-target-hints",
        action="store_true",
        help="Do not apply exact expected targets from the manual query dataset.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress console summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous Naive RAG workflow."""
    return asyncio.run(run_naive_rag_workflow(argv))


async def run_naive_rag_workflow(argv: list[str] | None = None) -> int:
    """Load dependencies, run fallback-aware Naive RAG, and write a JSON result."""
    load_project_dotenv()
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(
            query=args.query,
            top_k=args.top_k,
            output_path=args.output,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout_s,
        )
        config = load_retrieval_config(args.config)
        collection_name = args.collection_name or config.qdrant.collection_name
        url = args.url or config.qdrant.url
        device = args.device or config.embedding.device
        openrouter = resolve_openrouter_settings(cli_model=args.model)

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
        generation_config = RagGenerationConfig(
            provider=args.provider,
            model=openrouter.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout_s,
            include_auxiliary_context=not args.no_auxiliary_context,
            fail_on_invalid_citation=args.strict_citations,
        )
        result = await run_naive_rag(
            query=args.query,
            retriever=service,
            llm_client=OpenRouterLLMClient(
                base_url=openrouter.base_url,
                default_model=openrouter.model,
            ),
            collection_name=collection_name,
            top_k=args.top_k,
            evidence_config=ContextAssemblyConfig(max_packets=args.top_k),
            selection_config=EvidenceSelectionConfig(
                fallback_on_parent_context_only=False,
                needs_review_on_all_evidence_caution=False,
                include_auxiliary_context_in_rendered_output=not args.no_auxiliary_context,
            ),
            generation_config=generation_config,
            expected_targets=(
                None
                if args.disable_manual_target_hints
                else expected_targets_for_query(args.manual_queries, args.query)
            ),
        )
        write_report(args.output, result)
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        EmbeddingModelError,
        QdrantCollectionError,
        DenseRetrieverError,
        LLMClientError,
    ) as exc:
        print(f"Naive RAG failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        print_summary(result)
    return EXIT_FAILURE if result.errors else EXIT_SUCCESS


def validate_cli_arguments(
    *,
    query: str,
    top_k: int,
    output_path: Path,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
) -> None:
    """Validate CLI path safety and bounded generation settings."""
    if not query.strip():
        raise ValueError("query must not be blank")
    if top_k <= 0:
        raise ValueError("top-k must be positive")
    if max_tokens <= 0:
        raise ValueError("max-tokens must be positive")
    if timeout_s <= 0:
        raise ValueError("timeout-s must be positive")
    if not 0 <= temperature <= 2:
        raise ValueError("temperature must be between 0 and 2")
    if is_protected_output(output_path):
        raise ValueError(
            f"refusing protected Naive RAG output path {output_path}; use /tmp "
            "or artifacts/reports/retrieval"
        )


def expected_targets_for_query(path: Path, query: str) -> list[ExpectedTarget] | None:
    """Return manual expected targets when the query exactly matches a record."""
    if not path.exists():
        return None
    normalized_query = " ".join(query.split()).casefold()
    for record in load_manual_retrieval_queries(path):
        if " ".join(record.query.split()).casefold() == normalized_query:
            return record.expected
    return None


def write_report(path: Path, result: RagAnswerResult) -> None:
    """Write the Naive RAG result atomically as UTF-8 JSON."""
    write_json_report(path, result.model_dump(mode="json"))


def print_summary(result: RagAnswerResult) -> None:
    """Print a compact Naive RAG summary."""
    print("Naive RAG Result")
    print(f"Decision: {result.decision.value}")
    print(f"LLM called: {result.llm_called}")
    print(f"Model: {result.model or 'none'}")
    print(f"Provider: {result.provider or 'none'}")
    print(f"Citations: {len(result.citations)}")
    print(f"Citation issues: {len(result.citation_issues)}")
    if result.fallback_reasons:
        print(f"Fallback reasons: {'/'.join(result.fallback_reasons)}")
    if result.errors:
        print(f"Errors: {'; '.join(result.errors)}")
    print("")
    print(result.answer)
