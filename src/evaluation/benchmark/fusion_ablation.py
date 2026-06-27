"""Coverage-aware hybrid fusion ablation for frozen legal QA retrieval."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from src.evaluation.benchmark.enums import BenchmarkSplit
from src.evaluation.benchmark.fingerprinting import sha256_file
from src.evaluation.benchmark.hybrid_retrieval_baseline import (
    RetrieverProtocol,
    load_system_breakdowns,
    load_system_metrics,
)
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
from src.retrieval.fusion import (
    DiversitySelectionConfig,
    QuotaSelectionConfig,
    reciprocal_rank_fusion,
)
from src.retrieval.sparse_retriever import SparseRetrieverError

FusionMode = Literal["weighted_rrf", "quota", "diversity"]


@dataclass(frozen=True)
class CoverageAwareFusionConfig:
    """One coverage-aware fusion ablation configuration."""

    config_id: str
    mode: FusionMode
    dense_candidate_k: int = 50
    sparse_candidate_k: int = 50
    final_top_k: int = 10
    rrf_k: int = 60
    dense_weight: float = 1.0
    sparse_weight: float = 1.0
    fused_best: int | None = None
    sparse_quota: int | None = None
    dense_quota: int | None = None
    diversity_penalty: float | None = None
    prefer_distinct_clause_point: bool = False
    simplicity_rank: int = 0

    def quota_config(self) -> QuotaSelectionConfig | None:
        """Return quota selector settings when this variant uses quotas."""
        if self.mode != "quota":
            return None
        if self.fused_best is None or self.sparse_quota is None or self.dense_quota is None:
            raise ValueError(f"quota config {self.config_id} is incomplete")
        return QuotaSelectionConfig(
            fused_best=self.fused_best,
            sparse_quota=self.sparse_quota,
            dense_quota=self.dense_quota,
        )

    def diversity_config(self) -> DiversitySelectionConfig | None:
        """Return diversity selector settings when this variant uses diversity."""
        if self.mode != "diversity":
            return None
        if self.diversity_penalty is None:
            raise ValueError(f"diversity config {self.config_id} is incomplete")
        return DiversitySelectionConfig(
            penalty=self.diversity_penalty,
            prefer_distinct_clause_point=self.prefer_distinct_clause_point,
        )

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-compatible config dictionary."""
        return {
            "config_id": self.config_id,
            "mode": self.mode,
            "dense_candidate_k": self.dense_candidate_k,
            "sparse_candidate_k": self.sparse_candidate_k,
            "final_top_k": self.final_top_k,
            "rrf_k": self.rrf_k,
            "dense_weight": self.dense_weight,
            "sparse_weight": self.sparse_weight,
            "quota": {
                "fused_best": self.fused_best,
                "sparse_quota": self.sparse_quota,
                "dense_quota": self.dense_quota,
            }
            if self.mode == "quota"
            else None,
            "diversity": {
                "diversity_penalty": self.diversity_penalty,
                "prefer_distinct_clause_point": self.prefer_distinct_clause_point,
            }
            if self.mode == "diversity"
            else None,
            "simplicity_rank": self.simplicity_rank,
        }


@dataclass(frozen=True)
class FusionAblationPaths:
    """Paths used by the development-only fusion ablation runner."""

    file_set: BenchmarkFileSet
    split_manifest: Path
    benchmark_manifest: Path
    chunk_source: Path
    dense_config: Path
    dense_reference_dir: Path
    sparse_reference_dir: Path
    fixed_rrf_reference_dir: Path
    output_dir: Path


class FusionAblationError(RuntimeError):
    """Raised when coverage-aware fusion ablation cannot safely complete."""


def default_ablation_configs() -> list[CoverageAwareFusionConfig]:
    """Return the fixed development-only fusion ablation search space."""
    configs = [
        CoverageAwareFusionConfig(
            "equal_weight_rrf", "weighted_rrf", 50, 50, 10, 60, 1.0, 1.0, simplicity_rank=0
        ),
        CoverageAwareFusionConfig(
            "sparse_weight_1_25", "weighted_rrf", 50, 50, 10, 60, 1.0, 1.25, simplicity_rank=1
        ),
        CoverageAwareFusionConfig(
            "sparse_weight_1_5", "weighted_rrf", 50, 50, 10, 60, 1.0, 1.5, simplicity_rank=2
        ),
        CoverageAwareFusionConfig(
            "sparse_weight_2", "weighted_rrf", 50, 50, 10, 60, 1.0, 2.0, simplicity_rank=3
        ),
        CoverageAwareFusionConfig(
            "dense_weight_1_25", "weighted_rrf", 50, 50, 10, 60, 1.25, 1.0, simplicity_rank=4
        ),
        CoverageAwareFusionConfig(
            "sparse_weight_1_5_pool_50_100",
            "weighted_rrf",
            50,
            100,
            10,
            60,
            1.0,
            1.5,
            simplicity_rank=5,
        ),
        CoverageAwareFusionConfig(
            "sparse_weight_1_5_pool_100_100",
            "weighted_rrf",
            100,
            100,
            10,
            60,
            1.0,
            1.5,
            simplicity_rank=6,
        ),
        CoverageAwareFusionConfig(
            "sparse_weight_2_pool_50_100",
            "weighted_rrf",
            50,
            100,
            10,
            60,
            1.0,
            2.0,
            simplicity_rank=7,
        ),
        CoverageAwareFusionConfig(
            "sparse_weight_2_pool_100_100",
            "weighted_rrf",
            100,
            100,
            10,
            60,
            1.0,
            2.0,
            simplicity_rank=8,
        ),
        CoverageAwareFusionConfig(
            "quota_fused6_sparse3_dense1",
            "quota",
            50,
            50,
            10,
            60,
            1.0,
            1.5,
            6,
            3,
            1,
            simplicity_rank=9,
        ),
        CoverageAwareFusionConfig(
            "quota_fused5_sparse3_dense2",
            "quota",
            50,
            50,
            10,
            60,
            1.0,
            1.5,
            5,
            3,
            2,
            simplicity_rank=10,
        ),
        CoverageAwareFusionConfig(
            "quota_fused4_sparse4_dense2",
            "quota",
            50,
            50,
            10,
            60,
            1.0,
            1.5,
            4,
            4,
            2,
            simplicity_rank=11,
        ),
        CoverageAwareFusionConfig(
            "selected_coverage_aware_quota",
            "quota",
            50,
            50,
            10,
            60,
            1.0,
            1.5,
            5,
            4,
            1,
            simplicity_rank=12,
        ),
        CoverageAwareFusionConfig(
            "diversity_penalty_0_001",
            "diversity",
            50,
            50,
            10,
            60,
            1.0,
            1.5,
            diversity_penalty=0.001,
            simplicity_rank=13,
        ),
        CoverageAwareFusionConfig(
            "diversity_penalty_0_002",
            "diversity",
            50,
            50,
            10,
            60,
            1.0,
            1.5,
            diversity_penalty=0.002,
            simplicity_rank=14,
        ),
        CoverageAwareFusionConfig(
            "diversity_penalty_0_001_distinct_detail",
            "diversity",
            50,
            50,
            10,
            60,
            1.0,
            1.5,
            diversity_penalty=0.001,
            prefer_distinct_clause_point=True,
            simplicity_rank=15,
        ),
    ]
    return configs


async def run_development_ablation(
    *,
    paths: FusionAblationPaths,
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
    qdrant_collection_name: str,
    vector_name: str,
    embedding_model: str,
    command: list[str],
) -> dict[str, Any]:
    """Run development-only fusion ablation and write artifacts."""
    dataset = load_benchmark_dataset(paths.file_set)
    split_manifest = load_split_manifest(paths.split_manifest)
    benchmark_manifest = load_benchmark_manifest(paths.benchmark_manifest)
    judgments_by_query, groups_by_query = build_benchmark_case_inputs(dataset)
    configs = default_ablation_configs()
    max_dense_k = max(config.dense_candidate_k for config in configs)
    max_sparse_k = max(config.sparse_candidate_k for config in configs)
    development_queries = [
        query
        for query in dataset.queries
        if split_manifest.assignments[query.id] == BenchmarkSplit.DEVELOPMENT
    ]
    candidate_cache = await _retrieve_candidate_cache(
        queries=development_queries,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        dense_k=max_dense_k,
        sparse_k=max_sparse_k,
    )

    variant_results: list[dict[str, Any]] = []
    case_results_by_config: dict[str, list[dict[str, Any]]] = {}
    for config in configs:
        case_results = _evaluate_config_from_cache(
            config=config,
            queries=development_queries,
            candidate_cache=candidate_cache,
            judgments_by_query=judgments_by_query,
            groups_by_query=groups_by_query,
            split=BenchmarkSplit.DEVELOPMENT,
        )
        metrics = aggregate_case_metrics(case_results)
        variant_results.append(
            {
                "config": config.model_dump(),
                "development_metrics": metrics,
                "query_count": len(case_results),
                "retrieval_error_count": metrics["retrieval_error_count"],
            }
        )
        case_results_by_config[config.config_id] = case_results

    selected = _select_best_config(variant_results)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    selected_config = _config_by_id(selected["config"]["config_id"], configs)
    manifest = {
        "report_type": "development_fusion_ablation_manifest",
        "benchmark_version": benchmark_manifest.benchmark_version,
        "benchmark_manifest_sha256": sha256_file(paths.benchmark_manifest),
        "split_manifest_sha256": sha256_file(paths.split_manifest),
        "retrieval_method": "coverage_aware_hybrid_ablation",
        "selection_split": BenchmarkSplit.DEVELOPMENT.value,
        "selected_by": "development evidence_group_coverage@10",
        "selected_config_id": selected_config.config_id,
        "selected_config": selected_config.model_dump(),
        "candidate_query_count": len(development_queries),
        "dense_config_path": str(paths.dense_config),
        "dense_config_sha256": sha256_file(paths.dense_config),
        "qdrant_collection_name": qdrant_collection_name,
        "vector_name": vector_name,
        "embedding_model": embedding_model,
        "chunk_source_path": str(paths.chunk_source),
        "chunk_source_sha256": sha256_file(paths.chunk_source),
        "dense_baseline_manifest_sha256": sha256_file(
            paths.dense_reference_dir / "baseline_manifest.json"
        ),
        "sparse_baseline_manifest_sha256": sha256_file(
            paths.sparse_reference_dir / "baseline_manifest.json"
        ),
        "fixed_rrf_baseline_manifest_sha256": sha256_file(
            paths.fixed_rrf_reference_dir / "baseline_manifest.json"
        ),
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit_or_unknown(),
        "command": command,
        "known_limitations": [
            "development-only ablation",
            "retrieval-only evaluation",
            "no generation",
            "no reranking",
            "fixed ablation search space",
            "held_out_test not used for config selection",
            "coverage-aware ranking uses metadata proxies, not gold evidence groups",
        ],
    }
    report = {
        "report_type": "development_fusion_ablation_results",
        "benchmark_version": benchmark_manifest.benchmark_version,
        "selection_rule": {
            "primary": "highest development evidence_group_coverage@10",
            "tie_breakers": [
                "required_direct_coverage@10",
                "Recall@10",
                "MRR@10",
                "NDCG@10",
                "lower mean retrieval latency",
                "simpler config",
            ],
        },
        "held_out_test_used_for_selection": False,
        "selected_config_id": selected_config.config_id,
        "selected_config": selected_config.model_dump(),
        "selected_development_metrics": selected["development_metrics"],
        "variants": variant_results,
    }
    assert_manifest_has_no_secret_keys(manifest)
    assert_manifest_has_no_secret_keys(report)
    write_json_atomic(paths.output_dir / "ablation_manifest.json", manifest)
    write_json_atomic(paths.output_dir / "ablation_results.json", report)
    (paths.output_dir / "ablation_summary.md").write_text(
        render_ablation_summary(report),
        encoding="utf-8",
    )
    return report


async def run_final_coverage_aware_report(
    *,
    paths: FusionAblationPaths,
    ablation_dir: Path,
    output_dir: Path,
    comparison_dir: Path,
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
    dense_config_payload: dict[str, Any],
    qdrant_collection_name: str,
    qdrant_collection_info: dict[str, Any],
    embedding_model: str,
    vector_name: str,
    command: list[str],
) -> list[dict[str, Any]]:
    """Run the selected coverage-aware config on all benchmark splits once."""
    ablation_results = load_ablation_results(ablation_dir / "ablation_results.json")
    selected_config = config_from_payload(ablation_results["selected_config"])
    dataset = load_benchmark_dataset(paths.file_set)
    split_manifest = load_split_manifest(paths.split_manifest)
    benchmark_manifest = load_benchmark_manifest(paths.benchmark_manifest)
    judgments_by_query, groups_by_query = build_benchmark_case_inputs(dataset)
    candidate_cache = await _retrieve_candidate_cache(
        queries=dataset.queries,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        dense_k=selected_config.dense_candidate_k,
        sparse_k=selected_config.sparse_candidate_k,
    )
    case_results: list[dict[str, Any]] = []
    for query in dataset.queries:
        split = split_manifest.assignments[query.id]
        case_results.extend(
            _evaluate_config_from_cache(
                config=selected_config,
                queries=[query],
                candidate_cache=candidate_cache,
                judgments_by_query=judgments_by_query,
                groups_by_query=groups_by_query,
                split=split,
            )
        )
    write_coverage_aware_outputs(
        output_dir=output_dir,
        case_results=case_results,
        benchmark_version=benchmark_manifest.benchmark_version,
        benchmark_manifest_path=paths.benchmark_manifest,
        split_manifest_path=paths.split_manifest,
        chunk_source_path=paths.chunk_source,
        dense_config_path=paths.dense_config,
        dense_config_payload=dense_config_payload,
        dense_reference_dir=paths.dense_reference_dir,
        sparse_reference_dir=paths.sparse_reference_dir,
        fixed_rrf_reference_dir=paths.fixed_rrf_reference_dir,
        fusion_ablation_manifest=ablation_dir / "ablation_manifest.json",
        config=selected_config,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_collection_info=qdrant_collection_info,
        embedding_model=embedding_model,
        vector_name=vector_name,
        command=command,
    )
    write_coverage_aware_comparison(
        comparison_dir=comparison_dir,
        dense_dir=paths.dense_reference_dir,
        sparse_dir=paths.sparse_reference_dir,
        fixed_rrf_dir=paths.fixed_rrf_reference_dir,
        coverage_aware_dir=output_dir,
    )
    return case_results


def write_coverage_aware_outputs(
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
    fixed_rrf_reference_dir: Path,
    fusion_ablation_manifest: Path,
    config: CoverageAwareFusionConfig,
    qdrant_collection_name: str,
    qdrant_collection_info: dict[str, Any],
    embedding_model: str,
    vector_name: str,
    command: list[str],
) -> None:
    """Write final selected coverage-aware retrieval artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics = aggregate_case_metrics(case_results)
    breakdowns = build_breakdowns(case_results)
    split_metrics = breakdowns["split"]
    write_jsonl_atomic(output_dir / "case_results.jsonl", case_results)
    write_json_atomic(output_dir / "metrics_all.json", all_metrics)
    write_json_atomic(output_dir / "metrics_development.json", split_metrics["development"])
    write_json_atomic(output_dir / "metrics_held_out_test.json", split_metrics["held_out_test"])
    write_json_atomic(output_dir / "breakdowns.json", breakdowns)
    manifest = {
        "report_type": "frozen_coverage_aware_retrieval_manifest",
        "benchmark_version": benchmark_version,
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "retrieval_method": f"coverage_aware_{config.mode}",
        "selected_config_id": config.config_id,
        "selected_by": "development evidence_group_coverage@10",
        "selected_config": config.model_dump(),
        "dense_candidate_k": config.dense_candidate_k,
        "sparse_candidate_k": config.sparse_candidate_k,
        "final_top_k": config.final_top_k,
        "rrf_k": config.rrf_k,
        "dense_weight": config.dense_weight,
        "sparse_weight": config.sparse_weight,
        "quota": config.model_dump()["quota"],
        "diversity": config.model_dump()["diversity"],
        "dense_config_path": str(dense_config_path),
        "dense_config_sha256": sha256_file(dense_config_path),
        "dense_config": dense_config_payload,
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
        "fixed_rrf_baseline_manifest_sha256": sha256_file(
            fixed_rrf_reference_dir / "baseline_manifest.json"
        ),
        "fusion_ablation_manifest_sha256": sha256_file(fusion_ablation_manifest),
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit_or_unknown(),
        "command": command,
        "query_count": len(case_results),
        "artifacts_produced": [
            str(output_dir / "case_results.jsonl"),
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
            "development-selected config",
            "fixed ablation search space",
            "held_out_test evaluated once after selection",
            "held_out_test excludes high-risk sanction/criminal QA",
            "qualified human legal review has not occurred",
            "coverage-aware ranking uses metadata proxies, not gold evidence groups",
        ],
    }
    assert_manifest_has_no_secret_keys(manifest)
    write_json_atomic(output_dir / "baseline_manifest.json", manifest)
    (output_dir / "summary.md").write_text(
        render_coverage_aware_summary(
            all_metrics=all_metrics,
            split_metrics=split_metrics,
            breakdowns=breakdowns,
            manifest=manifest,
        ),
        encoding="utf-8",
    )


def write_coverage_aware_comparison(
    *,
    comparison_dir: Path,
    dense_dir: Path,
    sparse_dir: Path,
    fixed_rrf_dir: Path,
    coverage_aware_dir: Path,
) -> None:
    """Write comparison artifacts for the active retrieval strategies."""
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
            "metrics": load_system_metrics(fixed_rrf_dir),
            "breakdowns": load_system_breakdowns(fixed_rrf_dir),
        },
        "coverage_aware_quota": {
            "retrieval_method": "coverage_aware_quota",
            "metrics": load_system_metrics(coverage_aware_dir),
            "breakdowns": load_system_breakdowns(coverage_aware_dir),
        },
    }
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
        "deltas": {
            "coverage_aware_vs_dense": _delta_metrics(
                systems["coverage_aware_quota"]["metrics"],
                systems["dense_bge_m3_baseline"]["metrics"],
            ),
            "coverage_aware_vs_sparse": _delta_metrics(
                systems["coverage_aware_quota"]["metrics"],
                systems["sparse_bm25_baseline"]["metrics"],
            ),
            "coverage_aware_vs_fixed_rrf": _delta_metrics(
                systems["coverage_aware_quota"]["metrics"],
                systems["fixed_rrf_hybrid"]["metrics"],
            ),
        },
        "key_questions": {
            "coverage_aware_improves_development_group_coverage_over_fixed_rrf": systems[
                "coverage_aware_quota"
            ]["metrics"]["development"]["evidence_group_coverage_at_10"]
            > systems["fixed_rrf_hybrid"]["metrics"]["development"][
                "evidence_group_coverage_at_10"
            ],
            "coverage_aware_recovers_sparse_development_group_coverage": systems[
                "coverage_aware_quota"
            ]["metrics"]["development"]["evidence_group_coverage_at_10"]
            >= systems["sparse_bm25_baseline"]["metrics"]["development"][
                "evidence_group_coverage_at_10"
            ],
            "coverage_aware_preserves_fixed_rrf_all_recall": systems["coverage_aware_quota"][
                "metrics"
            ]["all"]["recall_at_10"]
            >= systems["fixed_rrf_hybrid"]["metrics"]["all"]["recall_at_10"],
            "coverage_aware_preserves_dense_held_out_recall": systems["coverage_aware_quota"][
                "metrics"
            ]["held_out_test"]["recall_at_10"]
            >= systems["dense_bge_m3_baseline"]["metrics"]["held_out_test"]["recall_at_10"],
        },
        "interpretation": "Coverage-aware quota retrieval is selected on development evidence-group coverage only; held_out_test is reported once after selection.",
        "recommendation": "Use reranking only as a separate controlled ablation; keep gate or selection-policy changes separately safety-scoped.",
    }
    assert_manifest_has_no_secret_keys(comparison)
    write_json_atomic(comparison_dir / "comparison.json", comparison)
    (comparison_dir / "comparison.md").write_text(
        render_coverage_aware_comparison_markdown(comparison), encoding="utf-8"
    )


def load_ablation_results(path: Path) -> dict[str, Any]:
    """Load coverage-aware fusion ablation result JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FusionAblationError(f"ablation result root must be an object: {path}")
    return payload


def config_from_payload(payload: dict[str, Any]) -> CoverageAwareFusionConfig:
    """Build a typed config from a JSON-compatible payload."""
    quota = payload.get("quota") or {}
    diversity = payload.get("diversity") or {}
    return CoverageAwareFusionConfig(
        config_id=str(payload["config_id"]),
        mode=payload["mode"],
        dense_candidate_k=payload["dense_candidate_k"],
        sparse_candidate_k=payload["sparse_candidate_k"],
        final_top_k=payload["final_top_k"],
        rrf_k=payload["rrf_k"],
        dense_weight=payload["dense_weight"],
        sparse_weight=payload["sparse_weight"],
        fused_best=quota.get("fused_best"),
        sparse_quota=quota.get("sparse_quota"),
        dense_quota=quota.get("dense_quota"),
        diversity_penalty=diversity.get("diversity_penalty"),
        prefer_distinct_clause_point=bool(diversity.get("prefer_distinct_clause_point", False)),
        simplicity_rank=payload.get("simplicity_rank", 999),
    )


def assert_manifest_has_no_secret_keys(payload: Any) -> None:
    """Reject manifest payloads that expose secret-shaped keys."""
    forbidden_fragments = (
        "api_key",
        "authorization",
        "bearer",
        "password",
        "secret",
        "token",
    )
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = str(key).lower()
            if any(fragment in normalized_key for fragment in forbidden_fragments):
                raise FusionAblationError(f"manifest contains secret-shaped key: {key}")
            assert_manifest_has_no_secret_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_manifest_has_no_secret_keys(item)


def render_ablation_summary(report: dict[str, Any]) -> str:
    """Render Markdown summary for development-only ablation."""
    lines = [
        "# Fusion Ablation",
        "",
        "- Split used for selection: `development`.",
        "- Held-out test used for selection: `false`.",
        f"- Selected config: `{report['selected_config_id']}`.",
        "",
        "## Selected Development Metrics",
        "",
        _metric_line("selected", report["selected_development_metrics"]),
        "",
        "## Variants",
        "",
        "| Config | Mode | Group@10 | Required@10 | Recall@10 | MRR@10 | NDCG@10 | Latency ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in report["variants"]:
        metrics = variant["development_metrics"]
        config = variant["config"]
        lines.append(
            f"| `{config['config_id']}` | `{config['mode']}` | "
            f"{metrics['evidence_group_coverage_at_10']:.3f} | "
            f"{metrics['required_direct_coverage_at_10']:.3f} | "
            f"{metrics['recall_at_10']:.3f} | {metrics['mrr_at_10']:.3f} | "
            f"{metrics['ndcg_at_10']:.3f} | {metrics['mean_retrieval_latency_ms']:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_coverage_aware_summary(
    *,
    all_metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    manifest: dict[str, Any],
) -> str:
    """Render Markdown summary for selected coverage-aware retrieval."""
    lines = [
        "# Frozen Coverage-Aware Hybrid Retrieval",
        "",
        f"- Selected config: `{manifest['selected_config_id']}`.",
        f"- Retrieval method: `{manifest['retrieval_method']}`.",
        "- No generation, LLM call, reranking, or fallback-gate change.",
        "",
        "## Headline Metrics",
        "",
        _metric_line("all", all_metrics),
        _metric_line("development", split_metrics["development"]),
        _metric_line("held_out_test", split_metrics["held_out_test"]),
        "",
        "## Weakest Breakdowns",
        "",
    ]
    lines.extend(_weak_breakdown_lines(breakdowns, "primary_domain"))
    lines.extend(_weak_breakdown_lines(breakdowns, "question_types"))
    lines.extend(
        [
            "",
            "## Known Limitations",
            "",
            "- Retrieval-only evaluation.",
            "- No generation or reranking.",
            "- Development-selected config.",
            "- Fixed ablation search space.",
            "- Held-out test evaluated once after selection.",
            "- Coverage-aware ranking uses metadata proxies, not gold evidence groups.",
            "",
        ]
    )
    return "\n".join(lines)


def render_coverage_aware_comparison_markdown(comparison: dict[str, Any]) -> str:
    """Render comparison Markdown including coverage-aware retrieval."""
    lines = [
        "# Advanced Retrieval Comparison",
        "",
        "| System | Split | Recall@10 | MRR@10 | NDCG@10 | evidence_group_coverage@10 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for label, payload in comparison["systems"].items():
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
        for split_name, metrics in deltas.items():
            lines.append(
                f"- `{split_name}`: Recall@10 delta={metrics['recall_at_10_delta']:+.3f}; "
                f"group coverage delta={metrics['evidence_group_coverage_at_10_delta']:+.3f}."
            )
        lines.append("")
    lines.extend(
        [
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


def _retrieve_candidate_cache(
    *,
    queries: list[Any],
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
    dense_k: int,
    sparse_k: int,
) -> AwaitableCandidateCache:
    return _retrieve_candidate_cache_impl(
        queries=queries,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        dense_k=dense_k,
        sparse_k=sparse_k,
    )


async def _retrieve_candidate_cache_impl(
    *,
    queries: list[Any],
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
    dense_k: int,
    sparse_k: int,
) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for query in queries:
        started = time.perf_counter()
        try:
            dense_result = await dense_retriever.retrieve(query.query, top_k=dense_k)
            sparse_result = await sparse_retriever.retrieve(query.query, top_k=sparse_k)
            cache[query.id] = {
                "dense": dense_result.results,
                "sparse": sparse_result.results,
                "retrieval_error": None,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
            }
        except (DenseRetrieverError, SparseRetrieverError, ValueError) as exc:
            cache[query.id] = {
                "dense": [],
                "sparse": [],
                "retrieval_error": str(exc),
                "elapsed_ms": (time.perf_counter() - started) * 1000,
            }
    return cache


AwaitableCandidateCache = Any


def _evaluate_config_from_cache(
    *,
    config: CoverageAwareFusionConfig,
    queries: list[Any],
    candidate_cache: dict[str, dict[str, Any]],
    judgments_by_query: dict[str, list[Any]],
    groups_by_query: dict[str, list[Any]],
    split: BenchmarkSplit,
) -> list[dict[str, Any]]:
    case_results: list[dict[str, Any]] = []
    for query in queries:
        cached = candidate_cache[query.id]
        if cached["retrieval_error"] is not None:
            case_results.append(
                evaluate_case_retrieval(
                    query=query,
                    split=split,
                    retrieved=[],
                    judgments=judgments_by_query.get(query.id, []),
                    groups=groups_by_query.get(query.id, []),
                    cutoffs=DEFAULT_RETRIEVAL_CUTOFFS,
                    retrieval_error=cached["retrieval_error"],
                    elapsed_ms=cached["elapsed_ms"],
                )
            )
            continue
        dense_results = cached["dense"][: config.dense_candidate_k]
        sparse_results = cached["sparse"][: config.sparse_candidate_k]
        fused = reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            final_top_k=config.final_top_k,
            rrf_k=config.rrf_k,
            dense_weight=config.dense_weight,
            sparse_weight=config.sparse_weight,
            quota_config=config.quota_config(),
            diversity_config=config.diversity_config(),
        )
        case_results.append(
            evaluate_case_retrieval(
                query=query,
                split=split,
                retrieved=fused,
                judgments=judgments_by_query.get(query.id, []),
                groups=groups_by_query.get(query.id, []),
                cutoffs=DEFAULT_RETRIEVAL_CUTOFFS,
                elapsed_ms=cached["elapsed_ms"],
            )
        )
    return case_results


def _select_best_config(variant_results: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        variant_results,
        key=lambda item: (
            item["development_metrics"]["evidence_group_coverage_at_10"],
            item["development_metrics"]["required_direct_coverage_at_10"],
            item["development_metrics"]["recall_at_10"],
            item["development_metrics"]["mrr_at_10"],
            item["development_metrics"]["ndcg_at_10"],
            -item["development_metrics"]["mean_retrieval_latency_ms"],
            -item["config"]["simplicity_rank"],
        ),
    )


def _config_by_id(
    config_id: str,
    configs: list[CoverageAwareFusionConfig],
) -> CoverageAwareFusionConfig:
    for config in configs:
        if config.config_id == config_id:
            return config
    raise FusionAblationError(f"unknown config id: {config_id}")


def _metric_line(label: str, metrics: dict[str, Any]) -> str:
    return (
        f"- `{label}`: queries={metrics['query_count']}, "
        f"Recall@10={metrics['recall_at_10']:.3f}, "
        f"MRR@10={metrics['mrr_at_10']:.3f}, "
        f"NDCG@10={metrics['ndcg_at_10']:.3f}, "
        f"required_direct_coverage@10={metrics['required_direct_coverage_at_10']:.3f}, "
        f"evidence_group_coverage@10={metrics['evidence_group_coverage_at_10']:.3f}"
    )


def _weak_breakdown_lines(
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    dimension: str,
) -> list[str]:
    lines = [f"### {dimension}", ""]
    for row in _weak_rows(breakdowns, dimension):
        lines.append(
            f"- `{row['label']}`: evidence_group_coverage_at_10={row['metric_value']:.3f}, "
            f"Recall@10={row['recall_at_10']:.3f}, "
            f"answer_allowed={row['answer_allowed_count']}, queries={row['query_count']}"
        )
    lines.append("")
    return lines


def _weak_rows(
    breakdowns: dict[str, dict[str, dict[str, Any]]],
    dimension: str,
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "label": label,
                "metric_value": metrics["evidence_group_coverage_at_10"],
                "recall_at_10": metrics["recall_at_10"],
                "answer_allowed_count": metrics["answer_allowed_count"],
                "query_count": metrics["query_count"],
            }
            for label, metrics in breakdowns[dimension].items()
            if metrics["answer_allowed_count"] > 0
        ),
        key=lambda row: (row["metric_value"], row["query_count"]),
    )[:5]


def _delta_metrics(
    current: dict[str, dict[str, Any]],
    baseline: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        split_name: {
            "recall_at_10_delta": metrics["recall_at_10"] - baseline[split_name]["recall_at_10"],
            "mrr_at_10_delta": metrics["mrr_at_10"] - baseline[split_name]["mrr_at_10"],
            "ndcg_at_10_delta": metrics["ndcg_at_10"] - baseline[split_name]["ndcg_at_10"],
            "evidence_group_coverage_at_10_delta": metrics["evidence_group_coverage_at_10"]
            - baseline[split_name]["evidence_group_coverage_at_10"],
        }
        for split_name, metrics in current.items()
    }


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
