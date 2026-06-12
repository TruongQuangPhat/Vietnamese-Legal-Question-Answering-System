"""Workflow for Phase 9C repeatable Naive RAG generation evaluation."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.evaluation import (
    ExpectedTarget,
    ManualRetrievalQuery,
    load_manual_retrieval_queries,
)
from src.retrieval.evidence import ContextAssemblyConfig
from src.retrieval.generation import RagAnswerResult, RagGenerationConfig
from src.retrieval.generation_evaluation import (
    DEFAULT_EVIDENCE_PREVIEW_CHARS,
    GenerationEvalCaseResult,
    GenerationEvalQuery,
    GenerationEvalReport,
    build_generation_eval_report,
    find_secret_leak_labels,
    load_generation_eval_queries,
    validate_generation_result,
)
from src.retrieval.llm_client import LLMClientError, OpenRouterLLMClient
from src.retrieval.openrouter_config import load_project_dotenv, resolve_openrouter_settings
from src.retrieval.rag_pipeline import run_naive_rag
from src.retrieval.selection import EvidenceSelectionConfig
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
DEFAULT_GENERATION_QUERIES = Path("data/eval/manual_naive_rag_generation_queries.jsonl")
DEFAULT_OUTPUT = Path("artifacts/reports/retrieval/naive_rag_generation_eval.json")
GenerationCaseRunner = Callable[[GenerationEvalQuery], Awaitable[RagAnswerResult]]


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the Phase 9C generation evaluation CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluate_naive_rag_generation.py",
        description="Run deterministic safety evaluation over Naive RAG generation cases.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_GENERATION_QUERIES,
        help="Manual Phase 9C generation evaluation JSONL dataset.",
    )
    parser.add_argument(
        "--manual-retrieval-queries",
        type=Path,
        default=DEFAULT_QUERIES,
        help="Phase 9A manual dataset used for expected target hints.",
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
    parser.add_argument("--provider", choices=["openrouter"], default="openrouter")
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override; flash-lite is recommended for smoke/dev evaluation.",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument(
        "--include-evidence-preview",
        action="store_true",
        help="Include short safe-citable child evidence previews in the report.",
    )
    parser.add_argument(
        "--evidence-preview-chars",
        type=int,
        default=DEFAULT_EVIDENCE_PREVIEW_CHARS,
        help="Maximum characters per selected evidence preview.",
    )
    parser.add_argument(
        "--no-auxiliary-context",
        action="store_true",
        help="Suppress auxiliary parent context in generation prompts.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON report path under artifacts/reports/retrieval or /tmp.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress console summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load project dotenv and run the asynchronous Phase 9C workflow."""
    load_project_dotenv()
    return asyncio.run(run_naive_rag_generation_eval(argv))


async def run_naive_rag_generation_eval(argv: list[str] | None = None) -> int:
    """Run all configured generation cases and write a deterministic report."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(
            queries_path=args.queries,
            manual_retrieval_queries_path=args.manual_retrieval_queries,
            output_path=args.output,
            top_k=args.top_k,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout_s,
            evidence_preview_chars=args.evidence_preview_chars,
        )
        retrieval_config = load_retrieval_config(args.config)
        cases = load_generation_eval_queries(args.queries)
        manual_queries = load_manual_retrieval_queries(args.manual_retrieval_queries)
        target_lookup = _expected_target_lookup(manual_queries)
        collection_name = args.collection_name or retrieval_config.qdrant.collection_name
        url = args.url or retrieval_config.qdrant.url
        device = args.device or retrieval_config.embedding.device
        openrouter = resolve_openrouter_settings(cli_model=args.model)

        client = build_qdrant_client(
            url=url,
            timeout_seconds=retrieval_config.qdrant.timeout_seconds,
        )
        embedding_model = BgeM3EmbeddingModel(
            model_name=retrieval_config.embedding.model_name,
            model_revision=retrieval_config.embedding.model_revision,
            device=device,
            normalize_embeddings=retrieval_config.embedding.normalize_embeddings,
            max_length=retrieval_config.embedding.max_length,
            dense_vector_name=retrieval_config.dense_retrieval.vector_name,
        )
        retriever = DenseRetriever(
            qdrant_client=client,
            embedding_model=embedding_model,
            collection_name=collection_name,
            dense_vector_name=retrieval_config.dense_retrieval.vector_name,
            expected_vector_dim=retrieval_config.dense_retrieval.expected_vector_dim,
            default_top_k=args.top_k,
            embedding_batch_size=retrieval_config.embedding.batch_size,
        )
        service = RetrievalService(retriever=retriever)
        llm_client = OpenRouterLLMClient(
            base_url=openrouter.base_url,
            default_model=openrouter.model,
        )
        generation_config = RagGenerationConfig(
            provider=args.provider,
            model=openrouter.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout_s,
            include_auxiliary_context=not args.no_auxiliary_context,
            fail_on_invalid_citation=False,
        )
        evidence_config = ContextAssemblyConfig(max_packets=args.top_k)
        selection_config = EvidenceSelectionConfig(
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=False,
            include_auxiliary_context_in_rendered_output=not args.no_auxiliary_context,
        )

        async def runner(case: GenerationEvalQuery) -> RagAnswerResult:
            return await run_naive_rag(
                query=case.query,
                retriever=service,
                llm_client=llm_client,
                collection_name=collection_name,
                top_k=args.top_k,
                evidence_config=evidence_config,
                selection_config=selection_config,
                generation_config=generation_config,
                expected_targets=_expected_targets_for_case(case, target_lookup),
            )

        report = await run_generation_eval_suite(
            cases,
            runner,
            dataset_path=args.queries,
            collection_name=collection_name,
            vector_name=retrieval_config.dense_retrieval.vector_name,
            top_k=args.top_k,
            provider=args.provider,
            model=openrouter.model,
            include_evidence_preview=args.include_evidence_preview,
            evidence_preview_chars=args.evidence_preview_chars,
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
        LLMClientError,
    ) as exc:
        print(f"Naive RAG generation evaluation failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        print_summary(report)
    return EXIT_SUCCESS if report.failed_cases == 0 else EXIT_FAILURE


async def run_generation_eval_suite(
    cases: Sequence[GenerationEvalQuery],
    runner: GenerationCaseRunner,
    *,
    dataset_path: Path,
    collection_name: str,
    vector_name: str,
    top_k: int,
    provider: str,
    model: str,
    include_evidence_preview: bool = False,
    evidence_preview_chars: int = DEFAULT_EVIDENCE_PREVIEW_CHARS,
) -> GenerationEvalReport:
    """Run injected Naive RAG cases and aggregate deterministic validation."""
    if not cases:
        raise ValueError("generation evaluation requires at least one case")
    started_at = datetime.now(UTC)
    results: list[GenerationEvalCaseResult] = []
    for case in cases:
        result = await runner(case)
        results.append(
            validate_generation_result(
                case,
                result,
                include_evidence_preview=include_evidence_preview,
                evidence_preview_chars=evidence_preview_chars,
            )
        )
    return build_generation_eval_report(
        cases=results,
        started_at=started_at,
        dataset_path=dataset_path,
        collection_name=collection_name,
        vector_name=vector_name,
        top_k=top_k,
        provider=provider,
        model=model,
    )


def validate_cli_arguments(
    *,
    queries_path: Path,
    manual_retrieval_queries_path: Path,
    output_path: Path,
    top_k: int,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    evidence_preview_chars: int,
) -> None:
    """Validate Phase 9C paths and bounded generation settings."""
    if not queries_path.is_file():
        raise ValueError(f"generation evaluation dataset not found: {queries_path}")
    if not manual_retrieval_queries_path.is_file():
        raise ValueError(f"manual retrieval dataset not found: {manual_retrieval_queries_path}")
    if is_protected_query_path(queries_path):
        raise ValueError(f"refusing protected generation query path: {queries_path}")
    if is_protected_output(output_path):
        raise ValueError(
            f"refusing protected generation evaluation output path {output_path}; "
            "use /tmp or artifacts/reports/retrieval"
        )
    if top_k <= 0:
        raise ValueError("top-k must be positive")
    if max_tokens <= 0:
        raise ValueError("max-tokens must be positive")
    if timeout_s <= 0:
        raise ValueError("timeout-s must be positive")
    if evidence_preview_chars <= 0:
        raise ValueError("evidence-preview-chars must be positive")
    if not 0 <= temperature <= 2:
        raise ValueError("temperature must be between 0 and 2")


def write_report(path: Path, report: GenerationEvalReport) -> None:
    """Write a secret-screened Phase 9C JSON report."""
    payload = report.model_dump(mode="json")
    serialized = report.model_dump_json()
    if find_secret_leak_labels(serialized):
        raise ValueError("refusing to write generation report containing secret-like content")
    write_json_report(path, payload)


def print_summary(report: GenerationEvalReport) -> None:
    """Print a compact secret-free Phase 9C summary."""
    print("Naive RAG Generation Evaluation")
    print(f"Status: {report.status}")
    print(f"Cases: {report.passed_cases}/{report.total_cases} passed")
    print(
        "Manual review: "
        f"{report.manual_review_required_count} cases "
        f"({report.non_blocking_case_count} non-blocking)"
    )
    print(f"Decision pass rate: {report.decision_pass_rate:.3f}")
    print(f"LLM call policy pass rate: {report.llm_call_policy_pass_rate:.3f}")
    print(f"Citation ID coverage rate: {report.citation_id_coverage_rate:.3f}")
    print(f"Unknown citation IDs: {report.unknown_citation_id_count}")
    print(f"Missing citation IDs: {report.missing_citation_id_count}")
    print(f"Evidence previews: {report.evidence_preview_total_count}")
    print(f"Missing cited evidence previews: {report.evidence_preview_missing_count}")
    print(f"Secret leak failures: {report.secret_leak_failures}")


def _expected_target_lookup(
    records: Sequence[ManualRetrievalQuery],
) -> dict[str, list[ExpectedTarget]]:
    lookup: dict[str, list[ExpectedTarget]] = {}
    for record in records:
        lookup[record.query_id] = record.expected
        lookup[_normalize_query(record.query)] = record.expected
    return lookup


def _expected_targets_for_case(
    case: GenerationEvalQuery,
    lookup: dict[str, list[ExpectedTarget]],
) -> list[ExpectedTarget] | None:
    if case.manual_query_id and case.manual_query_id in lookup:
        return lookup[case.manual_query_id]
    return lookup.get(_normalize_query(case.query))


def _normalize_query(query: str) -> str:
    return " ".join(query.split()).casefold()
