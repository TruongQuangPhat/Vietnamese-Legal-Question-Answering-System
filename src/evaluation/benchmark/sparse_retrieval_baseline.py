"""Sparse BM25 benchmark runner and artifacts for frozen legal QA evaluation."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from src.indexing.official_artifacts import write_json_atomic
from src.retrieval.sparse_retriever import (
    DEFAULT_BM25_B,
    DEFAULT_BM25_K1,
    SparseBM25Retriever,
    SparseRetrieverError,
)

F1_DENSE_REFERENCE = {
    "all": {
        "recall_at_10": 0.8454545455,
        "evidence_group_coverage_at_10": 0.5691489362,
    },
    "development": {
        "recall_at_10": 0.7941176471,
        "evidence_group_coverage_at_10": 0.5039370079,
    },
    "held_out_test": {
        "recall_at_10": 0.9285714286,
        "evidence_group_coverage_at_10": 0.7049180328,
    },
}


@dataclass(frozen=True)
class SparseBenchmarkPaths:
    """Input and output paths for a frozen sparse retrieval benchmark run."""

    file_set: BenchmarkFileSet
    split_manifest: Path
    benchmark_manifest: Path
    chunk_source: Path
    output_dir: Path
    dense_reference_dir: Path | None = None


@dataclass(frozen=True)
class SparseBenchmarkConfig:
    """Deterministic sparse retrieval settings captured in the manifest."""

    top_k: int = 10
    k1: float = DEFAULT_BM25_K1
    b: float = DEFAULT_BM25_B


async def run_sparse_benchmark(
    *,
    paths: SparseBenchmarkPaths,
    config: SparseBenchmarkConfig,
    command: list[str],
) -> list[dict[str, Any]]:
    """Run sparse BM25 retrieval and write frozen benchmark artifacts.

    Args:
        paths: Canonical benchmark, corpus, reference, and output paths.
        config: Sparse BM25 scoring and evaluation settings.
        command: Command line recorded in the manifest.

    Returns:
        Per-query benchmark case results.

    Raises:
        SparseRetrieverError: If the sparse index cannot be built or queried.
    """
    if config.top_k <= 0:
        raise SparseRetrieverError("top_k must be positive")

    dataset = load_benchmark_dataset(paths.file_set)
    split_manifest = load_split_manifest(paths.split_manifest)
    benchmark_manifest = load_benchmark_manifest(paths.benchmark_manifest)
    judgments_by_query, groups_by_query = build_benchmark_case_inputs(dataset)
    retriever = SparseBM25Retriever.from_jsonl(
        paths.chunk_source,
        k1=config.k1,
        b=config.b,
        default_top_k=config.top_k,
    )

    case_results: list[dict[str, Any]] = []
    for query in dataset.queries:
        split = split_manifest.assignments[query.id]
        try:
            retrieval_result = await retriever.retrieve(query.query, top_k=config.top_k)
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
        except SparseRetrieverError as exc:
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

    write_sparse_outputs(
        output_dir=paths.output_dir,
        case_results=case_results,
        benchmark_version=benchmark_manifest.benchmark_version,
        benchmark_manifest_path=paths.benchmark_manifest,
        split_manifest_path=paths.split_manifest,
        chunk_source_path=paths.chunk_source,
        dense_reference_dir=paths.dense_reference_dir,
        config=config,
        document_count=retriever.document_count,
        average_document_length=retriever.average_document_length,
        command=command,
    )
    return case_results


def write_sparse_outputs(
    *,
    output_dir: Path,
    case_results: list[dict[str, Any]],
    benchmark_version: str,
    benchmark_manifest_path: Path,
    split_manifest_path: Path,
    chunk_source_path: Path,
    dense_reference_dir: Path | None,
    config: SparseBenchmarkConfig,
    document_count: int,
    average_document_length: float,
    command: list[str],
) -> None:
    """Write sparse retrieval artifacts in the F1-compatible structure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics = aggregate_case_metrics(case_results)
    breakdowns = build_breakdowns(case_results)
    split_metrics = breakdowns["split"]
    dense_reference = load_dense_reference_metrics(dense_reference_dir)

    case_results_path = output_dir / "case_results.jsonl"
    write_jsonl_atomic(case_results_path, case_results)
    write_json_atomic(output_dir / "metrics_all.json", all_metrics)
    write_json_atomic(output_dir / "metrics_development.json", split_metrics["development"])
    write_json_atomic(output_dir / "metrics_held_out_test.json", split_metrics["held_out_test"])
    write_json_atomic(output_dir / "breakdowns.json", breakdowns)

    manifest = {
        "report_type": "frozen_sparse_retrieval_baseline_manifest",
        "benchmark_version": benchmark_version,
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "retrieval_method": "sparse_bm25",
        "chunk_source_path": str(chunk_source_path),
        "chunk_source_sha256": sha256_file(chunk_source_path),
        "top_k": config.top_k,
        "bm25": {
            "k1": config.k1,
            "b": config.b,
            "document_count": document_count,
            "average_document_length": average_document_length,
        },
        "tokenization_normalization": {
            "normalization": "Unicode NFC plus casefold",
            "tokenizer": "Python Unicode regex [^\\W_]+",
            "vietnamese_diacritics": "preserved",
            "stemming": "none",
            "stopwords": "none",
        },
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit_or_unknown(),
        "command": command,
        "query_count": len(case_results),
        "artifacts_produced": [
            str(case_results_path),
            str(output_dir / "metrics_all.json"),
            str(output_dir / "metrics_development.json"),
            str(output_dir / "metrics_held_out_test.json"),
            str(output_dir / "breakdowns.json"),
            str(output_dir / "baseline_manifest.json"),
            str(output_dir / "summary.md"),
        ],
        "known_limitations": [
            "sparse lexical retrieval only",
            "no dense retrieval in this run",
            "no hybrid fusion",
            "no reranking",
            "no LLM generation",
            "BM25 may miss semantic paraphrases",
            "held_out_test is evaluated once and must not be used for tuning",
            "held_out_test excludes high-risk sanction/criminal QA",
            "qualified human legal review has not occurred",
        ],
    }
    write_json_atomic(output_dir / "baseline_manifest.json", manifest)
    (output_dir / "summary.md").write_text(
        render_sparse_summary(
            all_metrics=all_metrics,
            split_metrics=split_metrics,
            breakdowns=breakdowns,
            manifest=manifest,
            dense_reference=dense_reference,
        ),
        encoding="utf-8",
    )


def load_dense_reference_metrics(reference_dir: Path | None) -> dict[str, dict[str, Any]]:
    """Load F1 dense metrics for read-only summary comparison when available."""
    if reference_dir is None:
        return F1_DENSE_REFERENCE
    files = {
        "all": reference_dir / "metrics_all.json",
        "development": reference_dir / "metrics_development.json",
        "held_out_test": reference_dir / "metrics_held_out_test.json",
    }
    loaded: dict[str, dict[str, Any]] = {}
    for label, path in files.items():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return F1_DENSE_REFERENCE
        if not isinstance(payload, dict):
            return F1_DENSE_REFERENCE
        loaded[label] = payload
    return loaded


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL records atomically without modifying benchmark data."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def render_sparse_summary(
    *,
    all_metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    manifest: dict[str, Any],
    dense_reference: dict[str, dict[str, Any]],
) -> str:
    """Render a concise Markdown report for the sparse BM25 baseline."""
    lines = [
        "# Frozen Sparse BM25 Retrieval Baseline",
        "",
        "## Scope",
        "",
        "- Retrieval type: sparse BM25.",
        "- Benchmark version is recorded in `baseline_manifest.json`.",
        f"- Chunk source: `{manifest['chunk_source_path']}`.",
        f"- Top-k: {manifest['top_k']}.",
        "- No dense retrieval, Qdrant, Docker, LLM call, hybrid fusion, reranking, or generation.",
        "- `held_out_test` is evaluated once and must not be used for tuning.",
        "",
        "## Headline Metrics",
        "",
        _metric_line("all", all_metrics),
        _metric_line("development", split_metrics["development"]),
        _metric_line("held_out_test", split_metrics["held_out_test"]),
        "",
        "## Comparison Against F1 Dense Baseline",
        "",
    ]
    lines.extend(_comparison_lines(all_metrics, split_metrics, dense_reference))
    lines.extend(
        [
            "",
            "## Weakest Breakdowns",
            "",
        ]
    )
    lines.extend(_weak_breakdown_lines(breakdowns, metric_name="evidence_group_coverage_at_10"))
    lines.extend(
        [
            "",
            "## Known Limitations",
            "",
            "- Sparse lexical retrieval only.",
            "- No dense retrieval in this run.",
            "- No hybrid fusion, reranking, query rewriting, or LLM generation.",
            "- BM25 may miss semantic paraphrases and broad conceptual matches.",
            "- `held_out_test` excludes high-risk sanction/criminal QA.",
            "- Qualified human legal review has not occurred.",
            "",
            "## Next Action",
            "",
            "- Run G2 hybrid dense+sparse retrieval with RRF as a separate controlled ablation.",
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


def _comparison_lines(
    all_metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    dense_reference: dict[str, dict[str, Any]],
) -> list[str]:
    sparse_by_label = {
        "all": all_metrics,
        "development": split_metrics["development"],
        "held_out_test": split_metrics["held_out_test"],
    }
    lines: list[str] = []
    for label, sparse_metrics in sparse_by_label.items():
        dense_metrics = dense_reference[label]
        recall_delta = sparse_metrics["recall_at_10"] - dense_metrics["recall_at_10"]
        group_delta = (
            sparse_metrics["evidence_group_coverage_at_10"]
            - dense_metrics["evidence_group_coverage_at_10"]
        )
        lines.append(
            f"- `{label}`: Recall@10 delta={recall_delta:+.3f}; "
            f"evidence_group_coverage@10 delta={group_delta:+.3f}."
        )
    return lines


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
                f"Recall@10={metrics['recall_at_10']:.3f}, "
                f"answer_allowed={metrics['answer_allowed_count']}, "
                f"queries={metrics['query_count']}"
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
