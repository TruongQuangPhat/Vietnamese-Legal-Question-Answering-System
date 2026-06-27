"""Hybrid dense+sparse RRF benchmark artifacts for frozen legal QA evaluation."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

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
from src.evaluation.benchmark.sparse_retrieval_baseline import write_jsonl_atomic
from src.indexing.official_artifacts import write_json_atomic
from src.retrieval.dense_retriever import DenseRetrieverError
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.models import RetrievalResult
from src.retrieval.sparse_retriever import DEFAULT_BM25_B, DEFAULT_BM25_K1, SparseRetrieverError

SystemMetrics = dict[str, dict[str, Any]]


class RetrieverProtocol(Protocol):
    """Minimal retriever protocol used by the hybrid benchmark runner."""

    async def retrieve(self, query: str, *, top_k: int) -> RetrievalResult:
        """Retrieve ranked candidates for one query."""
        ...


@dataclass(frozen=True)
class HybridBenchmarkPaths:
    """Input, reference, and output paths for a hybrid benchmark run."""

    file_set: BenchmarkFileSet
    split_manifest: Path
    benchmark_manifest: Path
    chunk_source: Path
    dense_config: Path
    dense_reference_dir: Path
    sparse_reference_dir: Path
    output_dir: Path
    comparison_dir: Path


@dataclass(frozen=True)
class HybridBenchmarkConfig:
    """Fixed dense-sparse candidate and RRF settings."""

    dense_candidate_k: int = 50
    sparse_candidate_k: int = 50
    final_top_k: int = 10
    rrf_k: int = 60
    bm25_k1: float = DEFAULT_BM25_K1
    bm25_b: float = DEFAULT_BM25_B


async def run_hybrid_benchmark(
    *,
    paths: HybridBenchmarkPaths,
    config: HybridBenchmarkConfig,
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
    dense_config_payload: dict[str, Any],
    qdrant_collection_name: str,
    qdrant_collection_info: dict[str, Any],
    embedding_model: str,
    vector_name: str,
    command: list[str],
) -> list[dict[str, Any]]:
    """Run hybrid dense+sparse RRF retrieval and write benchmark artifacts.

    Args:
        paths: Canonical benchmark, reference, and artifact paths.
        config: Fixed candidate and RRF settings.
        dense_retriever: Read-only dense retriever backed by Qdrant.
        sparse_retriever: Local BM25 sparse retriever.
        dense_config_payload: Dense retrieval config recorded in manifest.
        qdrant_collection_name: Read-only Qdrant collection queried.
        qdrant_collection_info: Read-only collection metadata.
        embedding_model: Dense embedding model name.
        vector_name: Dense vector name.
        command: Command line recorded in the manifest.

    Returns:
        Per-query benchmark case results.
    """
    _validate_config(config)
    dataset = load_benchmark_dataset(paths.file_set)
    split_manifest = load_split_manifest(paths.split_manifest)
    benchmark_manifest = load_benchmark_manifest(paths.benchmark_manifest)
    judgments_by_query, groups_by_query = build_benchmark_case_inputs(dataset)

    case_results: list[dict[str, Any]] = []
    for query in dataset.queries:
        split = split_manifest.assignments[query.id]
        started = time.perf_counter()
        try:
            dense_result = await dense_retriever.retrieve(
                query.query,
                top_k=config.dense_candidate_k,
            )
            sparse_result = await sparse_retriever.retrieve(
                query.query,
                top_k=config.sparse_candidate_k,
            )
            fused = reciprocal_rank_fusion(
                dense_results=dense_result.results,
                sparse_results=sparse_result.results,
                final_top_k=config.final_top_k,
                rrf_k=config.rrf_k,
            )
            case_results.append(
                evaluate_case_retrieval(
                    query=query,
                    split=split,
                    retrieved=fused,
                    judgments=judgments_by_query.get(query.id, []),
                    groups=groups_by_query.get(query.id, []),
                    cutoffs=DEFAULT_RETRIEVAL_CUTOFFS,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )
            )
        except (DenseRetrieverError, SparseRetrieverError, ValueError) as exc:
            case_results.append(
                evaluate_case_retrieval(
                    query=query,
                    split=split,
                    retrieved=[],
                    judgments=judgments_by_query.get(query.id, []),
                    groups=groups_by_query.get(query.id, []),
                    cutoffs=DEFAULT_RETRIEVAL_CUTOFFS,
                    retrieval_error=str(exc),
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )
            )

    write_hybrid_outputs(
        output_dir=paths.output_dir,
        case_results=case_results,
        benchmark_version=benchmark_manifest.benchmark_version,
        benchmark_manifest_path=paths.benchmark_manifest,
        split_manifest_path=paths.split_manifest,
        chunk_source_path=paths.chunk_source,
        dense_config_path=paths.dense_config,
        dense_config_payload=dense_config_payload,
        dense_reference_dir=paths.dense_reference_dir,
        sparse_reference_dir=paths.sparse_reference_dir,
        config=config,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_collection_info=qdrant_collection_info,
        embedding_model=embedding_model,
        vector_name=vector_name,
        command=command,
    )
    write_retrieval_comparison(
        comparison_dir=paths.comparison_dir,
        dense_dir=paths.dense_reference_dir,
        sparse_dir=paths.sparse_reference_dir,
        hybrid_dir=paths.output_dir,
    )
    return case_results


def write_hybrid_outputs(
    *,
    output_dir: Path,
    case_results: list[dict[str, Any]],
    benchmark_version: str,
    benchmark_manifest_path: Path,
    split_manifest_path: Path,
    chunk_source_path: Path,
    dense_config_path: Path,
    dense_config_payload: dict[str, Any],
    dense_reference_dir: Path,
    sparse_reference_dir: Path,
    config: HybridBenchmarkConfig,
    qdrant_collection_name: str,
    qdrant_collection_info: dict[str, Any],
    embedding_model: str,
    vector_name: str,
    command: list[str],
) -> None:
    """Write hybrid retrieval artifacts in the frozen benchmark structure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics = aggregate_case_metrics(case_results)
    breakdowns = build_breakdowns(case_results)
    split_metrics = breakdowns["split"]
    dense_metrics = load_system_metrics(dense_reference_dir)
    sparse_metrics = load_system_metrics(sparse_reference_dir)

    case_results_path = output_dir / "case_results.jsonl"
    write_jsonl_atomic(case_results_path, case_results)
    write_json_atomic(output_dir / "metrics_all.json", all_metrics)
    write_json_atomic(output_dir / "metrics_development.json", split_metrics["development"])
    write_json_atomic(output_dir / "metrics_held_out_test.json", split_metrics["held_out_test"])
    write_json_atomic(output_dir / "breakdowns.json", breakdowns)

    manifest = {
        "report_type": "frozen_hybrid_retrieval_baseline_manifest",
        "benchmark_version": benchmark_version,
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "retrieval_method": "hybrid_dense_sparse_rrf",
        "dense_config_path": str(dense_config_path),
        "dense_config_sha256": sha256_file(dense_config_path),
        "dense_config": dense_config_payload,
        "sparse_config": {
            "retrieval_method": "sparse_bm25",
            "bm25": {"k1": config.bm25_k1, "b": config.bm25_b},
            "normalization": "Unicode NFC plus casefold",
            "tokenizer": "Python Unicode regex [^\\W_]+",
        },
        "dense_candidate_k": config.dense_candidate_k,
        "sparse_candidate_k": config.sparse_candidate_k,
        "final_top_k": config.final_top_k,
        "rrf_k": config.rrf_k,
        "qdrant_collection_name": qdrant_collection_name,
        "qdrant_collection_info": qdrant_collection_info,
        "vector_name": vector_name,
        "embedding_model": embedding_model,
        "chunk_source_path": str(chunk_source_path),
        "chunk_source_sha256": sha256_file(chunk_source_path),
        "dense_baseline_manifest_sha256": sha256_file(
            dense_reference_dir / "baseline_manifest.json"
        ),
        "sparse_baseline_manifest_sha256": sha256_file(
            sparse_reference_dir / "baseline_manifest.json"
        ),
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
            "retrieval-only evaluation",
            "no generation",
            "no reranking",
            "fixed RRF parameters",
            "held_out_test evaluated once and not used for tuning",
            "held_out_test excludes high-risk sanction/criminal QA",
            "qualified human legal review has not occurred",
        ],
    }
    write_json_atomic(output_dir / "baseline_manifest.json", manifest)
    (output_dir / "summary.md").write_text(
        render_hybrid_summary(
            all_metrics=all_metrics,
            split_metrics=split_metrics,
            breakdowns=breakdowns,
            dense_metrics=dense_metrics,
            sparse_metrics=sparse_metrics,
            manifest=manifest,
        ),
        encoding="utf-8",
    )


def write_retrieval_comparison(
    *,
    comparison_dir: Path,
    dense_dir: Path,
    sparse_dir: Path,
    hybrid_dir: Path,
) -> None:
    """Write comparison artifacts for dense, sparse, and fixed RRF retrieval."""
    comparison_dir.mkdir(parents=True, exist_ok=True)
    systems = {
        "dense_bge_m3_baseline": {
            "retrieval_method": "dense_bge_m3",
            "metrics": load_system_metrics(dense_dir),
            "breakdowns": load_system_breakdowns(dense_dir),
        },
        "sparse_bm25_baseline": {
            "retrieval_method": "sparse_bm25",
            "metrics": load_system_metrics(sparse_dir),
            "breakdowns": load_system_breakdowns(sparse_dir),
        },
        "fixed_rrf_hybrid": {
            "retrieval_method": "hybrid_dense_sparse_rrf",
            "metrics": load_system_metrics(hybrid_dir),
            "breakdowns": load_system_breakdowns(hybrid_dir),
        },
    }
    key_questions = _comparison_key_questions(systems)
    comparison = {
        "report_type": "advanced_retrieval_comparison",
        "systems": {
            label: {
                "retrieval_method": payload["retrieval_method"],
                "metrics": payload["metrics"],
                "weakest_primary_domains": _weak_rows(payload["breakdowns"], "primary_domain"),
                "weakest_question_types": _weak_rows(payload["breakdowns"], "question_types"),
            }
            for label, payload in systems.items()
        },
        "deltas": _comparison_deltas(systems),
        "key_questions": key_questions,
        "interpretation": _comparison_interpretation(key_questions),
        "recommendation": (
            "Proceed to reranking ablation if fixed RRF preserves or improves retrieval "
            "coverage sufficiently for the chosen adoption criteria."
        ),
    }
    write_json_atomic(comparison_dir / "comparison.json", comparison)
    (comparison_dir / "comparison.md").write_text(
        render_comparison_markdown(comparison),
        encoding="utf-8",
    )


def load_system_metrics(report_dir: Path) -> SystemMetrics:
    """Load all/development/held-out metric JSON files from a report directory."""
    return {
        "all": _load_json_object(report_dir / "metrics_all.json"),
        "development": _load_json_object(report_dir / "metrics_development.json"),
        "held_out_test": _load_json_object(report_dir / "metrics_held_out_test.json"),
    }


def load_system_breakdowns(report_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """Load or reconstruct benchmark breakdowns from a report directory."""
    breakdowns_path = report_dir / "breakdowns.json"
    if breakdowns_path.exists():
        return _load_json_object(breakdowns_path)
    case_results = _load_jsonl_objects(report_dir / "case_results.jsonl")
    return build_breakdowns(case_results)


def render_hybrid_summary(
    *,
    all_metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    dense_metrics: SystemMetrics,
    sparse_metrics: SystemMetrics,
    manifest: dict[str, Any],
) -> str:
    """Render a concise Markdown summary for the hybrid RRF baseline."""
    lines = [
        "# Frozen Hybrid Dense+Sparse RRF Retrieval Baseline",
        "",
        "## Scope",
        "",
        "- Retrieval type: hybrid dense+sparse RRF.",
        "- Benchmark version is recorded in `baseline_manifest.json`.",
        f"- Dense candidates: {manifest['dense_candidate_k']}.",
        f"- Sparse candidates: {manifest['sparse_candidate_k']}.",
        f"- Final top-k: {manifest['final_top_k']}.",
        f"- RRF k: {manifest['rrf_k']}.",
        "- No LLM call, generation, reranking, query rewriting, or fallback-gate change.",
        "",
        "## Headline Metrics",
        "",
        _metric_line("all", all_metrics),
        _metric_line("development", split_metrics["development"]),
        _metric_line("held_out_test", split_metrics["held_out_test"]),
        "",
        "## Comparison Against Dense and Sparse Baselines",
        "",
    ]
    lines.extend(
        _summary_delta_lines(
            all_metrics=all_metrics,
            split_metrics=split_metrics,
            dense_metrics=dense_metrics,
            sparse_metrics=sparse_metrics,
        )
    )
    lines.extend(["", "## Weakest Breakdowns", ""])
    lines.extend(_weak_breakdown_lines(breakdowns, metric_name="evidence_group_coverage_at_10"))
    lines.extend(
        [
            "",
            "## Known Limitations",
            "",
            "- Retrieval-only evaluation.",
            "- No generation or reranking.",
            "- Fixed RRF parameters.",
            "- `held_out_test` evaluated once and not used for tuning.",
            "- `held_out_test` excludes high-risk sanction/criminal QA.",
            "- Qualified human legal review has not occurred.",
            "",
            "## Next Action",
            "",
            "- Run reranking ablation as a separate controlled experiment.",
            "",
        ]
    )
    return "\n".join(lines)


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    """Render Markdown comparison for dense, sparse, and hybrid retrieval."""
    systems = comparison["systems"]
    lines = [
        "# Advanced Retrieval Comparison",
        "",
        "## Headline Metrics",
        "",
        "| System | Split | Recall@10 | MRR@10 | NDCG@10 | evidence_group_coverage@10 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for label, payload in systems.items():
        for split_name, metrics in payload["metrics"].items():
            lines.append(
                f"| `{label}` | `{split_name}` | {metrics['recall_at_10']:.3f} | "
                f"{metrics['mrr_at_10']:.3f} | {metrics['ndcg_at_10']:.3f} | "
                f"{metrics['evidence_group_coverage_at_10']:.3f} |"
            )
    lines.extend(["", "## Key Questions", ""])
    for key, value in comparison["key_questions"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Deltas", ""])
    for label, deltas in comparison["deltas"].items():
        lines.append(f"### {label}")
        lines.append("")
        for split_name, metrics in deltas.items():
            lines.append(
                f"- `{split_name}`: Recall@10 delta={metrics['recall_at_10_delta']:+.3f}; "
                f"evidence_group_coverage@10 delta={metrics['evidence_group_coverage_at_10_delta']:+.3f}."
            )
        lines.append("")
    lines.extend(["## Weakest Hybrid Breakdowns", ""])
    hybrid = systems["fixed_rrf_hybrid"]
    lines.append("### primary_domain")
    lines.append("")
    for row in hybrid["weakest_primary_domains"]:
        lines.append(_weak_row_line(row))
    lines.extend(["", "### question_types", ""])
    for row in hybrid["weakest_question_types"]:
        lines.append(_weak_row_line(row))
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            comparison["interpretation"],
            "",
            "## Recommendation",
            "",
            comparison["recommendation"],
            "",
        ]
    )
    return "\n".join(lines)


def _validate_config(config: HybridBenchmarkConfig) -> None:
    for field_name in ("dense_candidate_k", "sparse_candidate_k", "final_top_k", "rrf_k"):
        if getattr(config, field_name) <= 0:
            raise ValueError(f"{field_name} must be positive")


def _metric_line(label: str, metrics: dict[str, Any]) -> str:
    return (
        f"- `{label}`: queries={metrics['query_count']}, "
        f"Recall@10={metrics['recall_at_10']:.3f}, "
        f"MRR@10={metrics['mrr_at_10']:.3f}, "
        f"NDCG@10={metrics['ndcg_at_10']:.3f}, "
        f"required_direct_coverage@10={metrics['required_direct_coverage_at_10']:.3f}, "
        f"evidence_group_coverage@10={metrics['evidence_group_coverage_at_10']:.3f}"
    )


def _summary_delta_lines(
    *,
    all_metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    dense_metrics: SystemMetrics,
    sparse_metrics: SystemMetrics,
) -> list[str]:
    hybrid = {
        "all": all_metrics,
        "development": split_metrics["development"],
        "held_out_test": split_metrics["held_out_test"],
    }
    lines: list[str] = []
    for split_name, metrics in hybrid.items():
        lines.append(
            f"- `{split_name}` vs dense: Recall@10 "
            f"{metrics['recall_at_10'] - dense_metrics[split_name]['recall_at_10']:+.3f}; "
            f"group coverage "
            f"{metrics['evidence_group_coverage_at_10'] - dense_metrics[split_name]['evidence_group_coverage_at_10']:+.3f}. "
            f"Vs sparse: Recall@10 "
            f"{metrics['recall_at_10'] - sparse_metrics[split_name]['recall_at_10']:+.3f}; "
            f"group coverage "
            f"{metrics['evidence_group_coverage_at_10'] - sparse_metrics[split_name]['evidence_group_coverage_at_10']:+.3f}."
        )
    return lines


def _comparison_deltas(systems: dict[str, dict[str, Any]]) -> dict[str, SystemMetrics]:
    hybrid = systems["fixed_rrf_hybrid"]["metrics"]
    return {
        "hybrid_vs_dense": _delta_metrics(hybrid, systems["dense_bge_m3_baseline"]["metrics"]),
        "hybrid_vs_sparse": _delta_metrics(hybrid, systems["sparse_bm25_baseline"]["metrics"]),
    }


def _delta_metrics(hybrid: SystemMetrics, baseline: SystemMetrics) -> SystemMetrics:
    deltas: SystemMetrics = {}
    for split_name, metrics in hybrid.items():
        deltas[split_name] = {
            "recall_at_10_delta": metrics["recall_at_10"] - baseline[split_name]["recall_at_10"],
            "mrr_at_10_delta": metrics["mrr_at_10"] - baseline[split_name]["mrr_at_10"],
            "ndcg_at_10_delta": metrics["ndcg_at_10"] - baseline[split_name]["ndcg_at_10"],
            "evidence_group_coverage_at_10_delta": metrics["evidence_group_coverage_at_10"]
            - baseline[split_name]["evidence_group_coverage_at_10"],
        }
    return deltas


def _comparison_key_questions(systems: dict[str, dict[str, Any]]) -> dict[str, bool]:
    dense = systems["dense_bge_m3_baseline"]["metrics"]
    sparse = systems["sparse_bm25_baseline"]["metrics"]
    hybrid = systems["fixed_rrf_hybrid"]["metrics"]
    return {
        "hybrid_improves_all_recall_over_dense_and_sparse": hybrid["all"]["recall_at_10"]
        > max(dense["all"]["recall_at_10"], sparse["all"]["recall_at_10"]),
        "hybrid_improves_all_group_coverage_over_dense_and_sparse": hybrid["all"][
            "evidence_group_coverage_at_10"
        ]
        > max(
            dense["all"]["evidence_group_coverage_at_10"],
            sparse["all"]["evidence_group_coverage_at_10"],
        ),
        "hybrid_preserves_held_out_dense_recall_strength": hybrid["held_out_test"]["recall_at_10"]
        >= dense["held_out_test"]["recall_at_10"],
        "hybrid_keeps_sparse_development_group_coverage_gain": hybrid["development"][
            "evidence_group_coverage_at_10"
        ]
        >= sparse["development"]["evidence_group_coverage_at_10"],
    }


def _comparison_interpretation(key_questions: dict[str, bool]) -> str:
    if all(key_questions.values()):
        return (
            "Hybrid RRF improves the primary all-query metrics while preserving dense held-out "
            "strength and sparse development coverage, so it is a strong candidate for reranking."
        )
    return (
        "Hybrid RRF is useful for comparison, but at least one target condition was not met. "
        "Review split-level regressions before adopting it as the default candidate for reranking."
    )


def _weak_breakdown_lines(
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    *,
    metric_name: str,
) -> list[str]:
    lines: list[str] = []
    for dimension in ("primary_domain", "question_types"):
        rows = _weak_rows(breakdowns, dimension, metric_name=metric_name)
        lines.append(f"### {dimension}")
        lines.append("")
        for row in rows:
            lines.append(_weak_row_line(row))
        lines.append("")
    return lines


def _weak_rows(
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    dimension: str,
    *,
    metric_name: str = "evidence_group_coverage_at_10",
) -> list[dict[str, Any]]:
    rows = sorted(
        (
            {
                "label": label,
                "metric_name": metric_name,
                "metric_value": metrics[metric_name],
                "recall_at_10": metrics["recall_at_10"],
                "answer_allowed_count": metrics["answer_allowed_count"],
                "query_count": metrics["query_count"],
            }
            for label, metrics in breakdowns[dimension].items()
            if metrics["answer_allowed_count"] > 0
        ),
        key=lambda row: (row["metric_value"], row["query_count"]),
    )[:5]
    return rows


def _weak_row_line(row: dict[str, Any]) -> str:
    return (
        f"- `{row['label']}`: {row['metric_name']}={row['metric_value']:.3f}, "
        f"Recall@10={row['recall_at_10']:.3f}, "
        f"answer_allowed={row['answer_allowed_count']}, queries={row['query_count']}"
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL record must be an object at {path}:{line_number}")
            records.append(payload)
    return records


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
