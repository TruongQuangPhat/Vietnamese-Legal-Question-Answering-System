"""Run retrieval-only dense baseline metrics on the frozen legal QA benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.evaluation.benchmark.fingerprinting import sha256_file
from src.evaluation.benchmark.loader import (
    BenchmarkFileSet,
    load_benchmark_dataset,
    load_benchmark_manifest,
    load_split_manifest,
)
from src.evaluation.benchmark.retrieval_baseline import (
    DEFAULT_RETRIEVAL_CUTOFFS,
    aggregate_case_metrics,
    build_benchmark_case_inputs,
    build_breakdowns,
    evaluate_case_retrieval,
)
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.official_artifacts import write_json_atomic
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client
from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.workflows.common import DEFAULT_CONFIG, load_retrieval_config
from src.services.retrieval_service import RetrievalService

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation/naive_rag_baseline_v0_1/retrieval")
DEFAULT_QUERIES = Path("data/eval/legal_qa_benchmark/benchmark_queries.jsonl")
DEFAULT_TARGETS = Path("data/eval/legal_qa_benchmark/benchmark_targets.jsonl")
DEFAULT_QRELS = Path("data/eval/legal_qa_benchmark/benchmark_qrels.jsonl")
DEFAULT_GROUPS = Path("data/eval/legal_qa_benchmark/evidence_groups.jsonl")
DEFAULT_REVIEWS = Path("data/eval/legal_qa_benchmark/review_records.jsonl")
DEFAULT_SPLIT_MANIFEST = Path("data/eval/legal_qa_benchmark/split_manifest.json")
DEFAULT_BENCHMARK_MANIFEST = Path("data/eval/legal_qa_benchmark/benchmark_manifest.json")
EVALUATION_REPORTS_ROOT = REPO_ROOT / "artifacts/reports/evaluation"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the frozen retrieval baseline CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/run_frozen_retrieval_baseline.py",
        description="Run read-only dense retrieval over the frozen legal QA benchmark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--legal-targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--evidence-judgments", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--evidence-groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument("--review-records", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--split-manifest", type=Path, default=DEFAULT_SPLIT_MANIFEST)
    parser.add_argument(
        "--benchmark-manifest",
        type=Path,
        default=DEFAULT_BENCHMARK_MANIFEST,
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--collection-name", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous frozen retrieval baseline command."""
    return asyncio.run(run_baseline(argv))


async def run_baseline(argv: list[str] | None = None) -> int:
    """Load the frozen benchmark, retrieve evidence, and write artifacts."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(args.output_dir)
        retrieval_config = load_retrieval_config(args.config)
        top_k = args.top_k or retrieval_config.dense_retrieval.top_k
        if top_k <= 0:
            raise ValueError("top-k must be positive")

        file_set = BenchmarkFileSet(
            queries=args.queries,
            legal_targets=args.legal_targets,
            evidence_judgments=args.evidence_judgments,
            evidence_groups=args.evidence_groups,
            review_records=args.review_records,
        )
        dataset = load_benchmark_dataset(file_set)
        split_manifest = load_split_manifest(args.split_manifest)
        benchmark_manifest = load_benchmark_manifest(args.benchmark_manifest)
        judgments_by_query, groups_by_query = build_benchmark_case_inputs(dataset)

        collection_name = args.collection_name or retrieval_config.qdrant.collection_name
        url = args.url or retrieval_config.qdrant.url
        device = args.device or retrieval_config.embedding.device

        client = build_qdrant_client(
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
        retriever = DenseRetriever(
            qdrant_client=client,
            embedding_model=embedding_model,
            collection_name=collection_name,
            dense_vector_name=retrieval_config.dense_retrieval.vector_name,
            expected_vector_dim=retrieval_config.dense_retrieval.expected_vector_dim,
            default_top_k=top_k,
            embedding_batch_size=retrieval_config.embedding.batch_size,
        )
        service = RetrievalService(retriever=retriever)

        case_results: list[dict[str, Any]] = []
        for query in dataset.queries:
            split = split_manifest.assignments[query.id]
            try:
                retrieval_result = await service.retrieve(
                    query=query.query,
                    top_k=top_k,
                    collection_name=collection_name,
                )
                case_results.append(
                    evaluate_case_retrieval(
                        query=query,
                        split=split,
                        retrieved=retrieval_result.results,
                        judgments=judgments_by_query.get(query.id, []),
                        groups=groups_by_query.get(query.id, []),
                        cutoffs=DEFAULT_RETRIEVAL_CUTOFFS,
                        elapsed_ms=retrieval_result.elapsed_ms,
                    )
                )
            except DenseRetrieverError as exc:
                case_results.append(
                    evaluate_case_retrieval(
                        query=query,
                        split=split,
                        retrieved=[],
                        judgments=judgments_by_query.get(query.id, []),
                        groups=groups_by_query.get(query.id, []),
                        cutoffs=DEFAULT_RETRIEVAL_CUTOFFS,
                        retrieval_error=str(exc),
                    )
                )

        output_dir = args.output_dir
        write_outputs(
            output_dir=output_dir,
            case_results=case_results,
            retrieval_config_path=args.config,
            retrieval_config=retrieval_config.model_dump(mode="json"),
            benchmark_manifest_path=args.benchmark_manifest,
            split_manifest_path=args.split_manifest,
            benchmark_version=benchmark_manifest.benchmark_version,
            collection_name=collection_name,
            collection_info=collection_info,
            embedding_model=retrieval_config.embedding.model_name,
            vector_name=retrieval_config.dense_retrieval.vector_name,
            top_k=top_k,
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
    ) as exc:
        print(f"Frozen retrieval baseline failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        metrics = aggregate_case_metrics(case_results)
        split_metrics = build_breakdowns(case_results)["split"]
        print(f"Benchmark version: {benchmark_manifest.benchmark_version}")
        print(f"Collection: {collection_name}")
        print(f"Vector: {retrieval_config.dense_retrieval.vector_name}")
        print(f"Top-k: {top_k}")
        print(f"Queries: {metrics['query_count']} | Errors: {metrics['retrieval_error_count']}")
        for split_name, split_data in split_metrics.items():
            print(
                f"{split_name}: Recall@10={split_data['recall_at_10']:.3f} "
                f"MRR@10={split_data['mrr_at_10']:.3f} "
                f"NDCG@10={split_data['ndcg_at_10']:.3f} "
                f"GroupCoverage@10={split_data['evidence_group_coverage_at_10']:.3f}"
            )
        print(f"Artifacts: {args.output_dir}")
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


def write_outputs(
    *,
    output_dir: Path,
    case_results: list[dict[str, Any]],
    retrieval_config_path: Path,
    retrieval_config: dict[str, Any],
    benchmark_manifest_path: Path,
    split_manifest_path: Path,
    benchmark_version: str,
    collection_name: str,
    collection_info: dict[str, Any],
    embedding_model: str,
    vector_name: str,
    top_k: int,
    command: list[str],
) -> None:
    """Write retrieval baseline artifacts into the runtime report directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics = aggregate_case_metrics(case_results)
    breakdowns = build_breakdowns(case_results)
    split_metrics = breakdowns["split"]

    case_results_path = output_dir / "case_results.jsonl"
    write_jsonl_atomic(case_results_path, case_results)
    write_json_atomic(output_dir / "metrics_all.json", all_metrics)
    write_json_atomic(output_dir / "metrics_development.json", split_metrics["development"])
    write_json_atomic(output_dir / "metrics_held_out_test.json", split_metrics["held_out_test"])

    manifest = {
        "report_type": "frozen_dense_retrieval_baseline_manifest",
        "benchmark_version": benchmark_version,
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "retrieval_config_path": str(retrieval_config_path),
        "retrieval_config_sha256": sha256_file(retrieval_config_path),
        "retrieval_config": retrieval_config,
        "qdrant_collection_name": collection_name,
        "qdrant_collection_info": collection_info,
        "embedding_model": embedding_model,
        "vector_name": vector_name,
        "top_k": top_k,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit_or_unknown(),
        "command": command,
        "artifacts_produced": [
            str(case_results_path),
            str(output_dir / "metrics_all.json"),
            str(output_dir / "metrics_development.json"),
            str(output_dir / "metrics_held_out_test.json"),
            str(output_dir / "baseline_manifest.json"),
            str(output_dir / "summary.md"),
        ],
        "known_limitations": [
            "retrieval-only baseline",
            "no generation",
            "no reranking",
            "no sparse retrieval",
            "no query rewriting",
            "held_out_test excludes high-risk sanction/criminal QA",
            "qualified human legal review has not occurred",
        ],
    }
    write_json_atomic(output_dir / "baseline_manifest.json", manifest)
    (output_dir / "summary.md").write_text(
        render_summary(
            all_metrics=all_metrics,
            split_metrics=split_metrics,
            breakdowns=breakdowns,
            manifest=manifest,
        ),
        encoding="utf-8",
    )


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL records atomically without modifying benchmark data."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def render_summary(
    *,
    all_metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    manifest: dict[str, Any],
) -> str:
    """Render a concise Markdown summary for the baseline run."""
    lines = [
        "# Frozen Dense Retrieval Baseline",
        "",
        "## Scope",
        "",
        "- Retrieval type: dense.",
        f"- Benchmark version: `{manifest['benchmark_version']}`.",
        f"- Qdrant collection: `{manifest['qdrant_collection_name']}`.",
        f"- Embedding model: `{manifest['embedding_model']}`.",
        f"- Vector name: `{manifest['vector_name']}`.",
        f"- Top-k: {manifest['top_k']}.",
        "- No answer generation, LLM call, sparse retrieval, fusion, reranking, or query rewriting.",
        "- `held_out_test` is scoped to low/medium-risk v0.1 cases only.",
        "",
        "## Headline Metrics",
        "",
        _metric_line("all", all_metrics),
        _metric_line("development", split_metrics["development"]),
        _metric_line("held_out_test", split_metrics["held_out_test"]),
        "",
        "## Fallback Diagnostics",
        "",
        _fallback_line("all", all_metrics),
        _fallback_line("development", split_metrics["development"]),
        _fallback_line("held_out_test", split_metrics["held_out_test"]),
        "",
        "## Weakest Breakdowns",
        "",
    ]
    lines.extend(_weak_breakdown_lines(breakdowns, metric_name="recall_at_10"))
    lines.extend(
        [
            "",
            "## Known Limitations",
            "",
            "- Retrieval-only baseline; no generation behavior is measured.",
            "- No reranking, sparse retrieval, RRF, fusion, or query rewriting.",
            "- `held_out_test` excludes high-risk sanction/criminal QA.",
            "- Qualified human legal review has not occurred.",
            "",
        ]
    )
    return "\n".join(lines)


def _metric_line(label: str, metrics: dict[str, Any]) -> str:
    return (
        f"- `{label}`: queries={metrics['query_count']}, "
        f"Recall@10={metrics['recall_at_10']:.3f}, "
        f"MRR@10={metrics['mrr_at_10']:.3f}, "
        f"NDCG@10={metrics['ndcg_at_10']:.3f}, "
        f"required_direct_coverage@10={metrics['required_direct_coverage_at_10']:.3f}, "
        f"evidence_group_coverage@10={metrics['evidence_group_coverage_at_10']:.3f}"
    )


def _fallback_line(label: str, metrics: dict[str, Any]) -> str:
    diagnostics = metrics["fallback_diagnostics"]
    near_miss = diagnostics["near_miss_retrieved_at_10"]
    supporting = diagnostics["supporting_retrieved_at_10"]
    direct = diagnostics["direct_evidence_retrieved_at_10"]
    return (
        f"- `{label}`: fallback_cases={diagnostics['fallback_case_count']}, "
        f"near_miss@10={near_miss['count']} ({near_miss['rate']:.3f}), "
        f"supporting@10={supporting['count']} ({supporting['rate']:.3f}), "
        f"direct_evidence@10={direct['count']} ({direct['rate']:.3f})"
    )


def _weak_breakdown_lines(
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    *,
    metric_name: str,
) -> list[str]:
    lines: list[str] = []
    for dimension in ("primary_domain", "question_types"):
        rows = sorted(
            (item for item in breakdowns[dimension].items() if item[1]["answer_allowed_count"] > 0),
            key=lambda item: (item[1][metric_name], item[1]["query_count"]),
        )[:5]
        lines.append(f"### {dimension}")
        lines.append("")
        for label, metrics in rows:
            lines.append(
                f"- `{label}`: {metric_name}={metrics[metric_name]:.3f}, "
                f"answer_allowed={metrics['answer_allowed_count']}, "
                f"queries={metrics['query_count']}, MRR@10={metrics['mrr_at_10']:.3f}"
            )
        if dimension == "question_types":
            lines.append(
                "- Buckets with no `answer_allowed` cases are excluded from direct-recall "
                "ranking and covered by fallback diagnostics."
            )
        lines.append("")
    return lines


def git_commit_or_unknown() -> str:
    """Return the current Git commit hash without exposing environment state."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
