#!/usr/bin/env python3
"""Run strict generation evaluation with coverage-aware quota retrieval."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from src.evaluation.benchmark.exceptions import BenchmarkLoadError
from src.evaluation.benchmark.loader import BenchmarkFileSet, load_benchmark_manifest
from src.evaluation.benchmark.strict_generation_evaluation import (
    StrictGenerationEvaluationError,
    StrictGenerationPaths,
    aggregate_strict_generation_metrics,
    build_strict_generation_breakdowns,
    run_strict_generation_cases,
    verify_coverage_retrieval_manifest,
)
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client
from src.retrieval.coverage_aware import (
    CoverageAwareQuotaRetriever,
    CoverageAwareRetrievalError,
)
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.generation import RagGenerationConfig
from src.retrieval.llm_client import OpenRouterLLMClient
from src.retrieval.openrouter_config import load_project_dotenv, resolve_openrouter_settings
from src.retrieval.selection import EvidenceSelectionConfig
from src.retrieval.sparse_retriever import SparseBM25Retriever, SparseRetrieverError
from src.retrieval.workflows.common import DEFAULT_CONFIG, load_retrieval_config

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_REPORTS_ROOT = REPO_ROOT / "artifacts/reports/evaluation"
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation")
DEFAULT_COVERAGE_RETRIEVAL_DIR = Path(
    "artifacts/reports/evaluation/advanced_rag/coverage_aware_retrieval"
)
DEFAULT_GENERATION_BASELINE_DIR = Path("artifacts/reports/evaluation/naive_rag_baseline/generation")
DEFAULT_QUERIES = Path("data/eval/legal_qa_benchmark/benchmark_queries.jsonl")
DEFAULT_TARGETS = Path("data/eval/legal_qa_benchmark/benchmark_targets.jsonl")
DEFAULT_QRELS = Path("data/eval/legal_qa_benchmark/benchmark_qrels.jsonl")
DEFAULT_GROUPS = Path("data/eval/legal_qa_benchmark/evidence_groups.jsonl")
DEFAULT_REVIEWS = Path("data/eval/legal_qa_benchmark/review_records.jsonl")
DEFAULT_SPLIT_MANIFEST = Path("data/eval/legal_qa_benchmark/split_manifest.json")
DEFAULT_BENCHMARK_MANIFEST = Path("data/eval/legal_qa_benchmark/benchmark_manifest.json")
DEFAULT_CHUNKS = Path("data/processed/legal_chunks.jsonl")
DEFAULT_LLM_CONFIG = Path("configs/llm/openrouter.yml")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the strict generation evaluation CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/run_strict_generation_evaluation.py",
        description=(
            "Evaluate strict legal generation with coverage-aware quota retrieval "
            "over the frozen benchmark."
        ),
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
    parser.add_argument("--retrieval-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--coverage-retrieval-dir",
        type=Path,
        default=DEFAULT_COVERAGE_RETRIEVAL_DIR,
    )
    parser.add_argument(
        "--generation-baseline-dir",
        type=Path,
        default=DEFAULT_GENERATION_BASELINE_DIR,
    )
    parser.add_argument("--llm-config", type=Path, default=DEFAULT_LLM_CONFIG)
    parser.add_argument("--provider", choices=["openrouter"], default="openrouter")
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--no-auxiliary-context", action="store_true")
    parser.add_argument("--collection-name", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments before loading credentials or runtime clients."""
    args = build_arg_parser().parse_args(argv)
    load_project_dotenv()
    return asyncio.run(run_command(args))


async def run_command(args: argparse.Namespace) -> int:
    """Construct read-only dependencies and run the strict evaluation."""
    client: Any | None = None
    try:
        validate_cli_arguments(args)
        retrieval_config = load_retrieval_config(args.retrieval_config)
        retrieval_manifest_path = args.coverage_retrieval_dir / "baseline_manifest.json"
        retrieval_manifest = load_json_object(retrieval_manifest_path)
        benchmark_manifest = load_benchmark_manifest(args.benchmark_manifest)
        fusion_config = verify_coverage_retrieval_manifest(
            manifest=retrieval_manifest,
            benchmark_version=benchmark_manifest.benchmark_version,
            benchmark_manifest_path=args.benchmark_manifest,
            split_manifest_path=args.split_manifest,
            retrieval_config_path=args.retrieval_config,
        )
        collection_name = args.collection_name or retrieval_config.qdrant.collection_name
        if collection_name != retrieval_manifest.get("qdrant_collection_name"):
            raise StrictGenerationEvaluationError(
                "collection name does not match coverage retrieval manifest"
            )
        url = args.url or retrieval_config.qdrant.url
        device = args.device or retrieval_config.embedding.device

        client = build_qdrant_client(
            url=url,
            timeout_seconds=retrieval_config.qdrant.timeout_seconds,
        )
        await client.get_collection(collection_name)
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
            default_top_k=fusion_config.dense_candidate_k,
            embedding_batch_size=retrieval_config.embedding.batch_size,
        )
        sparse_retriever = SparseBM25Retriever.from_jsonl(
            args.chunks,
            default_top_k=fusion_config.sparse_candidate_k,
        )
        coverage_retriever = CoverageAwareQuotaRetriever(
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
            config=fusion_config,
            collection_name=collection_name,
            vector_name=retrieval_config.dense_retrieval.vector_name,
        )

        provider_settings = resolve_openrouter_settings(
            cli_model=args.model,
            config_path=args.llm_config,
        )
        llm_client = OpenRouterLLMClient(
            base_url=provider_settings.base_url,
            default_model=provider_settings.model,
        )
        generation_config = RagGenerationConfig(
            provider=args.provider,
            model=provider_settings.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout_s,
            include_auxiliary_context=not args.no_auxiliary_context,
            fail_on_invalid_citation=True,
        )
        selection_config = EvidenceSelectionConfig(
            include_auxiliary_context_in_rendered_output=not args.no_auxiliary_context,
        )
        case_results = await run_strict_generation_cases(
            paths=_paths_from_args(args, retrieval_manifest_path),
            retriever=coverage_retriever,
            llm_client=llm_client,
            generation_config=generation_config,
            selection_config=selection_config,
            retrieval_manifest=retrieval_manifest,
            provider=args.provider,
            model=provider_settings.model,
            command=["python", *sys.argv],
        )
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValueError,
        ValidationError,
        BenchmarkLoadError,
        StrictGenerationEvaluationError,
        CoverageAwareRetrievalError,
        EmbeddingModelError,
        QdrantCollectionError,
        DenseRetrieverError,
        SparseRetrieverError,
    ) as exc:
        print(f"Strict generation evaluation failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        metrics = aggregate_strict_generation_metrics(case_results)
        split_metrics = build_strict_generation_breakdowns(case_results)["split"]
        print("Strict Generation Evaluation")
        print(
            f"Queries: {metrics['query_count']} | "
            f"Retrieval errors: {metrics['retrieval_error_count']} | "
            f"Generation errors: {metrics['generation_error_count']}"
        )
        for split_name, split_data in split_metrics.items():
            print(
                f"{split_name}: decision_accuracy={split_data['decision_accuracy']:.3f} "
                f"answer_rate={split_data['answer_allowed_answer_rate']:.3f} "
                f"fallback_rate={split_data['fallback_required_fallback_rate']:.3f} "
                f"group_coverage={split_data['selected_evidence_group_coverage']:.3f} "
                f"pass_rate={split_data['case_pass_rate']:.3f}"
            )
        print(f"Artifacts: {args.output_dir}")
    return EXIT_SUCCESS


def validate_cli_arguments(args: argparse.Namespace) -> None:
    """Validate paths and fixed strict evaluation settings without external I/O."""
    required_files = (
        args.queries,
        args.legal_targets,
        args.evidence_judgments,
        args.evidence_groups,
        args.review_records,
        args.split_manifest,
        args.benchmark_manifest,
        args.chunks,
        args.retrieval_config,
        args.llm_config,
    )
    for path in required_files:
        if not path.is_file():
            raise ValueError(f"required file not found: {path}")
    for report_dir, label in (
        (args.coverage_retrieval_dir, "coverage retrieval"),
        (args.generation_baseline_dir, "generation baseline"),
    ):
        if not (report_dir / "baseline_manifest.json").is_file():
            raise ValueError(f"{label} baseline_manifest.json is missing")
    for filename in (
        "metrics_all.json",
        "metrics_development.json",
        "metrics_held_out_test.json",
    ):
        if not (args.generation_baseline_dir / filename).is_file():
            raise ValueError(f"generation baseline {filename} is missing")
    if args.max_tokens <= 0:
        raise ValueError("max-tokens must be positive")
    if args.timeout_s <= 0:
        raise ValueError("timeout-s must be positive")
    if not 0 <= args.temperature <= 2:
        raise ValueError("temperature must be between 0 and 2")
    resolved = args.output_dir.expanduser().resolve()
    root = EVALUATION_REPORTS_ROOT.resolve()
    if root not in (resolved, *resolved.parents):
        raise ValueError(f"output directory must be under {root}")


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _paths_from_args(
    args: argparse.Namespace,
    retrieval_manifest_path: Path,
) -> StrictGenerationPaths:
    return StrictGenerationPaths(
        file_set=BenchmarkFileSet(
            queries=args.queries,
            legal_targets=args.legal_targets,
            evidence_judgments=args.evidence_judgments,
            evidence_groups=args.evidence_groups,
            review_records=args.review_records,
        ),
        split_manifest=args.split_manifest,
        benchmark_manifest=args.benchmark_manifest,
        retrieval_config=args.retrieval_config,
        coverage_retrieval_manifest=retrieval_manifest_path,
        generation_baseline_dir=args.generation_baseline_dir,
        llm_config=args.llm_config,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
