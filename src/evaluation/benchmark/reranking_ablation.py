"""Cross-encoder reranking ablation over coverage-aware hybrid retrieval."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from src.retrieval.fusion import QuotaSelectionConfig, reciprocal_rank_fusion
from src.retrieval.reranker import RerankerProtocol, rerank_candidates
from src.retrieval.sparse_retriever import SparseRetrieverError

G3_DENSE_CANDIDATE_K = 50
G3_SPARSE_CANDIDATE_K = 50
G3_FINAL_TOP_K = 10
G3_RRF_K = 60
G3_DENSE_WEIGHT = 1.0
G3_SPARSE_WEIGHT = 1.5
G3_QUOTA = QuotaSelectionConfig(fused_best=5, sparse_quota=4, dense_quota=1)


class RerankingAblationError(RuntimeError):
    """Raised when the reranking ablation cannot complete safely."""


@dataclass(frozen=True)
class RerankingConfig:
    """One fixed reranking ablation configuration."""

    config_id: str
    candidate_pool_k: int
    final_top_k: int
    reranker_weight: float
    g3_weight: float
    preserve_source_quota: bool = False
    sparse_quota: int = 0
    dense_quota: int = 0
    no_rerank: bool = False
    simplicity_rank: int = 0

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-compatible configuration."""
        return {
            "config_id": self.config_id,
            "candidate_pool_k": self.candidate_pool_k,
            "final_top_k": self.final_top_k,
            "reranker_weight": self.reranker_weight,
            "g3_weight": self.g3_weight,
            "score_combination": _score_combination(self),
            "normalization_method": "per-query min-max" if self.g3_weight > 0 else "none",
            "quota_preservation": {
                "enabled": self.preserve_source_quota,
                "sparse_quota": self.sparse_quota,
                "dense_quota": self.dense_quota,
            },
            "no_rerank": self.no_rerank,
            "simplicity_rank": self.simplicity_rank,
        }


@dataclass(frozen=True)
class RerankingBenchmarkPaths:
    """Canonical benchmark, baseline, and output paths for reranking."""

    file_set: BenchmarkFileSet
    split_manifest: Path
    benchmark_manifest: Path
    chunk_source: Path
    dense_config: Path
    dense_reference_dir: Path
    sparse_reference_dir: Path
    g2_reference_dir: Path
    g3_reference_dir: Path
    output_dir: Path


def default_reranking_configs() -> list[RerankingConfig]:
    """Return the fixed development-only reranking search space."""
    return [
        RerankingConfig("H0", 10, 10, 0.0, 1.0, no_rerank=True, simplicity_rank=0),
        RerankingConfig("H1", 30, 10, 1.0, 0.0, simplicity_rank=1),
        RerankingConfig("H2", 30, 10, 0.7, 0.3, simplicity_rank=2),
        RerankingConfig("H3", 30, 10, 0.5, 0.5, simplicity_rank=3),
        RerankingConfig("H4", 50, 10, 1.0, 0.0, simplicity_rank=4),
        RerankingConfig("H5", 50, 10, 0.7, 0.3, simplicity_rank=5),
        RerankingConfig(
            "H6",
            50,
            10,
            1.0,
            0.0,
            preserve_source_quota=True,
            sparse_quota=4,
            dense_quota=1,
            simplicity_rank=6,
        ),
    ]


async def run_development_reranking_ablation(
    *,
    paths: RerankingBenchmarkPaths,
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
    reranker: RerankerProtocol,
    reranker_device: str,
    reranker_dependency: str,
    qdrant_collection_name: str,
    vector_name: str,
    embedding_model: str,
    command: list[str],
) -> dict[str, Any]:
    """Run the fixed reranking variants on the development split only."""
    dataset = load_benchmark_dataset(paths.file_set)
    split_manifest = load_split_manifest(paths.split_manifest)
    benchmark_manifest = load_benchmark_manifest(paths.benchmark_manifest)
    judgments_by_query, groups_by_query = build_benchmark_case_inputs(dataset)
    development_queries = [
        query
        for query in dataset.queries
        if split_manifest.assignments[query.id] == BenchmarkSplit.DEVELOPMENT
    ]
    candidate_cache = await _retrieve_candidate_cache(
        queries=development_queries,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
    )
    configs = default_reranking_configs()
    prepared_cache = _prepare_reranker_cache(
        queries=development_queries,
        candidate_cache=candidate_cache,
        reranker=reranker,
        pool_sizes={config.candidate_pool_k for config in configs if not config.no_rerank},
    )

    variants: list[dict[str, Any]] = []
    for config in configs:
        cases = _evaluate_config(
            config=config,
            queries=development_queries,
            candidate_cache=candidate_cache,
            prepared_cache=prepared_cache,
            judgments_by_query=judgments_by_query,
            groups_by_query=groups_by_query,
            split_by_query={query.id: BenchmarkSplit.DEVELOPMENT for query in development_queries},
            reranker_model=reranker.model_name,
        )
        variants.append(
            {
                "config": config.model_dump(),
                "development_metrics": aggregate_case_metrics(cases),
                "query_count": len(cases),
            }
        )

    base_metrics = load_system_metrics(paths.g3_reference_dir)["development"]
    selection = select_reranking_config(variants, g3_development_metrics=base_metrics)
    report = {
        "report_type": "development_reranking_ablation_results",
        "benchmark_version": benchmark_manifest.benchmark_version,
        "selection_split": BenchmarkSplit.DEVELOPMENT.value,
        "held_out_test_used_for_selection": False,
        "selection_rule": {
            "eligibility": {
                "evidence_group_coverage_at_10_min": base_metrics["evidence_group_coverage_at_10"]
                - 0.01,
                "recall_at_10_min": base_metrics["recall_at_10"] - 0.01,
            },
            "tie_breakers": [
                "NDCG@10",
                "MRR@10",
                "evidence_group_coverage@5",
                "Recall@5",
                "lower mean retrieval latency",
                "simpler config",
            ],
        },
        "g3_development_metrics": base_metrics,
        **selection,
        "variants": variants,
    }
    manifest = {
        "report_type": "development_reranking_ablation_manifest",
        "benchmark_version": benchmark_manifest.benchmark_version,
        "benchmark_manifest_sha256": sha256_file(paths.benchmark_manifest),
        "split_manifest_sha256": sha256_file(paths.split_manifest),
        "base_retrieval_method": "coverage_aware_quota",
        "base_retrieval_config_id": "C4",
        "base_retrieval_manifest_sha256": sha256_file(
            paths.g3_reference_dir / "baseline_manifest.json"
        ),
        "selection_split": BenchmarkSplit.DEVELOPMENT.value,
        "reranker_model": reranker.model_name,
        "reranker_device": reranker_device,
        "reranker_dependency": reranker_dependency,
        "normalization_method": "per-query min-max for mixed-score variants",
        "candidate_query_count": len(development_queries),
        "qdrant_collection_name": qdrant_collection_name,
        "vector_name": vector_name,
        "embedding_model": embedding_model,
        "chunk_source_path": str(paths.chunk_source),
        "chunk_source_sha256": sha256_file(paths.chunk_source),
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit_or_unknown(),
        "command": command,
        "known_limitations": [
            "development-only ablation",
            "retrieval-only evaluation",
            "no generation",
            "no fallback gate change",
            "fixed ablation search space",
            "held_out_test not used for config selection",
            "reranker model dependency may affect reproducibility",
        ],
    }
    assert_manifest_has_no_secret_keys(manifest)
    assert_manifest_has_no_secret_keys(report)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(paths.output_dir / "ablation_manifest.json", manifest)
    write_json_atomic(paths.output_dir / "ablation_results.json", report)
    (paths.output_dir / "ablation_summary.md").write_text(
        render_ablation_summary(report),
        encoding="utf-8",
    )
    return report


async def run_final_reranked_report(
    *,
    paths: RerankingBenchmarkPaths,
    ablation_dir: Path,
    comparison_dir: Path,
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
    reranker: RerankerProtocol,
    reranker_device: str,
    reranker_dependency: str,
    dense_config_payload: dict[str, Any],
    qdrant_collection_name: str,
    qdrant_collection_info: dict[str, Any],
    vector_name: str,
    embedding_model: str,
    command: list[str],
) -> list[dict[str, Any]]:
    """Run the development-selected reranker once over the frozen benchmark."""
    ablation_report = _load_json_object(ablation_dir / "ablation_results.json")
    if not ablation_report.get("adopted"):
        raise RerankingAblationError("reranking was not adopted by the development-only ablation")
    selected_payload = ablation_report.get("selected_config")
    if not isinstance(selected_payload, dict):
        raise RerankingAblationError("ablation report has no selected reranking config")
    config = config_from_payload(selected_payload)

    dataset = load_benchmark_dataset(paths.file_set)
    split_manifest = load_split_manifest(paths.split_manifest)
    benchmark_manifest = load_benchmark_manifest(paths.benchmark_manifest)
    judgments_by_query, groups_by_query = build_benchmark_case_inputs(dataset)
    candidate_cache = await _retrieve_candidate_cache(
        queries=dataset.queries,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
    )
    prepared_cache = _prepare_reranker_cache(
        queries=dataset.queries,
        candidate_cache=candidate_cache,
        reranker=reranker,
        pool_sizes={config.candidate_pool_k},
    )
    case_results = _evaluate_config(
        config=config,
        queries=dataset.queries,
        candidate_cache=candidate_cache,
        prepared_cache=prepared_cache,
        judgments_by_query=judgments_by_query,
        groups_by_query=groups_by_query,
        split_by_query=split_manifest.assignments,
        reranker_model=reranker.model_name,
    )
    _write_final_outputs(
        paths=paths,
        ablation_dir=ablation_dir,
        case_results=case_results,
        benchmark_version=benchmark_manifest.benchmark_version,
        config=config,
        reranker=reranker,
        reranker_device=reranker_device,
        reranker_dependency=reranker_dependency,
        dense_config_payload=dense_config_payload,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_collection_info=qdrant_collection_info,
        vector_name=vector_name,
        embedding_model=embedding_model,
        command=command,
    )
    write_reranking_comparison(
        comparison_dir=comparison_dir,
        dense_dir=paths.dense_reference_dir,
        sparse_dir=paths.sparse_reference_dir,
        g2_dir=paths.g2_reference_dir,
        g3_dir=paths.g3_reference_dir,
        reranked_dir=paths.output_dir,
        ablation_report=ablation_report,
    )
    return case_results


def select_reranking_config(
    variants: list[dict[str, Any]],
    *,
    g3_development_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Select an eligible reranker using development metrics only."""
    reranked = [variant for variant in variants if variant["config"]["config_id"] != "H0"]
    eligible = [
        variant
        for variant in reranked
        if variant["development_metrics"]["evidence_group_coverage_at_10"]
        >= g3_development_metrics["evidence_group_coverage_at_10"] - 0.01
        and variant["development_metrics"]["recall_at_10"]
        >= g3_development_metrics["recall_at_10"] - 0.01
    ]
    if not eligible:
        return {
            "eligible_config_ids": [],
            "selected_config_id": None,
            "selected_config": None,
            "selected_development_metrics": None,
            "adopted": False,
            "decision": "no_adoption_no_eligible_reranker",
        }
    selected = max(eligible, key=_selection_key)
    metrics = selected["development_metrics"]
    improves_rank_quality = metrics["ndcg_at_10"] > g3_development_metrics["ndcg_at_10"] or (
        math_isclose(metrics["ndcg_at_10"], g3_development_metrics["ndcg_at_10"])
        and metrics["mrr_at_10"] > g3_development_metrics["mrr_at_10"]
    )
    return {
        "eligible_config_ids": [variant["config"]["config_id"] for variant in eligible],
        "selected_config_id": selected["config"]["config_id"] if improves_rank_quality else None,
        "selected_config": selected["config"] if improves_rank_quality else None,
        "selected_development_metrics": metrics if improves_rank_quality else None,
        "best_eligible_config_id": selected["config"]["config_id"],
        "best_eligible_development_metrics": metrics,
        "adopted": improves_rank_quality,
        "decision": "adopt_reranker" if improves_rank_quality else "no_adoption_no_rank_gain",
    }


def config_from_payload(payload: dict[str, Any]) -> RerankingConfig:
    """Build a typed reranking config from an artifact payload."""
    quota = payload.get("quota_preservation") or {}
    return RerankingConfig(
        config_id=str(payload["config_id"]),
        candidate_pool_k=int(payload["candidate_pool_k"]),
        final_top_k=int(payload["final_top_k"]),
        reranker_weight=float(payload["reranker_weight"]),
        g3_weight=float(payload["g3_weight"]),
        preserve_source_quota=bool(quota.get("enabled", False)),
        sparse_quota=int(quota.get("sparse_quota", 0)),
        dense_quota=int(quota.get("dense_quota", 0)),
        no_rerank=bool(payload.get("no_rerank", False)),
        simplicity_rank=int(payload.get("simplicity_rank", 999)),
    )


def assert_manifest_has_no_secret_keys(payload: Any) -> None:
    """Reject secret-shaped keys in durable reranking artifacts."""
    forbidden = ("api_key", "authorization", "bearer", "password", "secret", "token")
    if isinstance(payload, dict):
        for key, value in payload.items():
            if any(fragment in str(key).lower() for fragment in forbidden):
                raise RerankingAblationError(f"manifest contains secret-shaped key: {key}")
            assert_manifest_has_no_secret_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_manifest_has_no_secret_keys(item)


async def _retrieve_candidate_cache(
    *,
    queries: list[Any],
    dense_retriever: RetrieverProtocol,
    sparse_retriever: RetrieverProtocol,
) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for query in queries:
        started = time.perf_counter()
        try:
            dense = await dense_retriever.retrieve(query.query, top_k=G3_DENSE_CANDIDATE_K)
            sparse = await sparse_retriever.retrieve(query.query, top_k=G3_SPARSE_CANDIDATE_K)
            cache[query.id] = {
                "dense": dense.results,
                "sparse": sparse.results,
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


def _prepare_reranker_cache(
    *,
    queries: list[Any],
    candidate_cache: dict[str, dict[str, Any]],
    reranker: RerankerProtocol,
    pool_sizes: set[int],
) -> dict[tuple[str, int], dict[str, Any]]:
    prepared: dict[tuple[str, int], dict[str, Any]] = {}
    for query in queries:
        cached = candidate_cache[query.id]
        if cached["retrieval_error"] is not None:
            continue
        for pool_size in sorted(pool_sizes):
            pool = _build_g3_pool(cached, final_top_k=pool_size)
            started = time.perf_counter()
            scores = reranker.score(query.query, pool)
            prepared[(query.id, pool_size)] = {
                "pool": pool,
                "scores": scores,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
            }
    return prepared


def _evaluate_config(
    *,
    config: RerankingConfig,
    queries: list[Any],
    candidate_cache: dict[str, dict[str, Any]],
    prepared_cache: dict[tuple[str, int], dict[str, Any]],
    judgments_by_query: dict[str, list[Any]],
    groups_by_query: dict[str, list[Any]],
    split_by_query: dict[str, BenchmarkSplit],
    reranker_model: str,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for query in queries:
        cached = candidate_cache[query.id]
        split = split_by_query[query.id]
        if cached["retrieval_error"] is not None:
            retrieved = []
            error = cached["retrieval_error"]
            elapsed_ms = cached["elapsed_ms"]
        elif config.no_rerank:
            retrieved = _build_g3_pool(cached, final_top_k=config.final_top_k)
            error = None
            elapsed_ms = cached["elapsed_ms"]
        else:
            prepared = prepared_cache[(query.id, config.candidate_pool_k)]
            retrieved = rerank_candidates(
                candidates=prepared["pool"],
                reranker_scores=prepared["scores"],
                final_top_k=config.final_top_k,
                reranker_weight=config.reranker_weight,
                g3_weight=config.g3_weight,
                preserve_source_quota=config.preserve_source_quota,
                sparse_quota=config.sparse_quota,
                dense_quota=config.dense_quota,
                model_name=reranker_model,
            )
            error = None
            elapsed_ms = cached["elapsed_ms"] + prepared["elapsed_ms"]
        cases.append(
            evaluate_case_retrieval(
                query=query,
                split=split,
                retrieved=retrieved,
                judgments=judgments_by_query.get(query.id, []),
                groups=groups_by_query.get(query.id, []),
                cutoffs=DEFAULT_RETRIEVAL_CUTOFFS,
                retrieval_error=error,
                elapsed_ms=elapsed_ms,
            )
        )
    return cases


def _build_g3_pool(cached: dict[str, Any], *, final_top_k: int) -> list[Any]:
    return reciprocal_rank_fusion(
        dense_results=cached["dense"],
        sparse_results=cached["sparse"],
        final_top_k=final_top_k,
        rrf_k=G3_RRF_K,
        dense_weight=G3_DENSE_WEIGHT,
        sparse_weight=G3_SPARSE_WEIGHT,
        quota_config=G3_QUOTA,
    )


def _write_final_outputs(
    *,
    paths: RerankingBenchmarkPaths,
    ablation_dir: Path,
    case_results: list[dict[str, Any]],
    benchmark_version: str,
    config: RerankingConfig,
    reranker: RerankerProtocol,
    reranker_device: str,
    reranker_dependency: str,
    dense_config_payload: dict[str, Any],
    qdrant_collection_name: str,
    qdrant_collection_info: dict[str, Any],
    vector_name: str,
    embedding_model: str,
    command: list[str],
) -> None:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics = aggregate_case_metrics(case_results)
    breakdowns = build_breakdowns(case_results)
    split_metrics = breakdowns["split"]
    write_jsonl_atomic(paths.output_dir / "case_results.jsonl", case_results)
    write_json_atomic(paths.output_dir / "metrics_all.json", all_metrics)
    write_json_atomic(paths.output_dir / "metrics_development.json", split_metrics["development"])
    write_json_atomic(
        paths.output_dir / "metrics_held_out_test.json", split_metrics["held_out_test"]
    )
    write_json_atomic(paths.output_dir / "breakdowns.json", breakdowns)
    manifest = {
        "report_type": "frozen_reranked_retrieval_manifest",
        "benchmark_version": benchmark_version,
        "benchmark_manifest_sha256": sha256_file(paths.benchmark_manifest),
        "split_manifest_sha256": sha256_file(paths.split_manifest),
        "retrieval_method": "cross_encoder_reranked_coverage_aware_retrieval",
        "base_retrieval_method": "coverage_aware_quota",
        "base_retrieval_config_id": "C4",
        "base_retrieval_manifest_sha256": sha256_file(
            paths.g3_reference_dir / "baseline_manifest.json"
        ),
        "selected_reranking_config_id": config.config_id,
        "selected_by": "development eligibility gates then NDCG@10 and MRR@10",
        "candidate_pool_k": config.candidate_pool_k,
        "final_top_k": config.final_top_k,
        "reranker_model": reranker.model_name,
        "reranker_device": reranker_device,
        "reranker_dependency": reranker_dependency,
        "score_combination": _score_combination(config),
        "normalization_method": "per-query min-max" if config.g3_weight > 0 else "none",
        "quota_preservation": config.model_dump()["quota_preservation"],
        "qdrant_collection_name": qdrant_collection_name,
        "qdrant_collection_info": qdrant_collection_info,
        "vector_name": vector_name,
        "embedding_model": embedding_model,
        "dense_config_path": str(paths.dense_config),
        "dense_config_sha256": sha256_file(paths.dense_config),
        "dense_config": dense_config_payload,
        "chunk_source_path": str(paths.chunk_source),
        "chunk_source_sha256": sha256_file(paths.chunk_source),
        "reranking_ablation_manifest_sha256": sha256_file(ablation_dir / "ablation_manifest.json"),
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit_or_unknown(),
        "command": command,
        "query_count": len(case_results),
        "artifacts_produced": [
            str(paths.output_dir / filename)
            for filename in (
                "case_results.jsonl",
                "metrics_all.json",
                "metrics_development.json",
                "metrics_held_out_test.json",
                "breakdowns.json",
                "baseline_manifest.json",
                "summary.md",
            )
        ],
        "known_limitations": [
            "retrieval-only evaluation",
            "no generation",
            "no fallback gate change",
            "development-selected reranking config",
            "held_out_test evaluated once after selection",
            "fixed ablation search space",
            "reranker model dependency may affect reproducibility",
            "held_out_test excludes high-risk sanction/criminal QA",
            "qualified human legal review has not occurred",
        ],
    }
    assert_manifest_has_no_secret_keys(manifest)
    write_json_atomic(paths.output_dir / "baseline_manifest.json", manifest)
    (paths.output_dir / "summary.md").write_text(
        render_final_summary(
            manifest=manifest,
            all_metrics=all_metrics,
            split_metrics=split_metrics,
            g3_metrics=load_system_metrics(paths.g3_reference_dir),
            breakdowns=breakdowns,
        ),
        encoding="utf-8",
    )


def write_reranking_comparison(
    *,
    comparison_dir: Path,
    dense_dir: Path,
    sparse_dir: Path,
    g2_dir: Path,
    g3_dir: Path,
    reranked_dir: Path,
    ablation_report: dict[str, Any],
) -> None:
    """Write the advanced retrieval comparison including reranking."""
    systems = {
        "f1_dense": ("dense_bge_m3", dense_dir),
        "g1_sparse_bm25": ("sparse_bm25", sparse_dir),
        "g2_hybrid_rrf": ("hybrid_dense_sparse_rrf", g2_dir),
        "g3_coverage_aware": ("coverage_aware_hybrid", g3_dir),
        "h_reranked": ("cross_encoder_reranked_coverage_aware", reranked_dir),
    }
    payload = {
        "report_type": "advanced_retrieval_comparison",
        "systems": {
            label: {
                "retrieval_method": method,
                "metrics": load_system_metrics(path),
                "weakest_primary_domains": _weak_rows(
                    load_system_breakdowns(path), "primary_domain"
                ),
                "weakest_question_types": _weak_rows(
                    load_system_breakdowns(path), "question_types"
                ),
            }
            for label, (method, path) in systems.items()
        },
        "stage_h_ablation": {
            "adopted": ablation_report["adopted"],
            "selected_config_id": ablation_report["selected_config_id"],
            "held_out_test_used_for_selection": False,
        },
    }
    payload["deltas"] = {
        "h_vs_g3": _delta_metrics(
            payload["systems"]["h_reranked"]["metrics"],
            payload["systems"]["g3_coverage_aware"]["metrics"],
        )
    }
    payload["interpretation"] = (
        "Reranking was selected on development metrics subject to G3 recall and "
        "evidence-group coverage preservation gates."
    )
    payload["recommendation"] = (
        "Proceed to strict advanced generation comparison while preserving the "
        "existing evidence-selection and fallback policies."
    )
    assert_manifest_has_no_secret_keys(payload)
    comparison_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(comparison_dir / "comparison.json", payload)
    (comparison_dir / "comparison.md").write_text(
        render_comparison_markdown(payload),
        encoding="utf-8",
    )


def render_ablation_summary(report: dict[str, Any]) -> str:
    """Render a concise development-only reranking ablation summary."""
    lines = [
        "# Reranking Ablation",
        "",
        "- Selection split: `development`.",
        "- Held-out test used for selection: `false`.",
        f"- Decision: `{report['decision']}`.",
        f"- Selected config: `{report['selected_config_id']}`.",
        "",
        "| Config | Pool | NDCG@10 | MRR@10 | Group@10 | Recall@10 | Group@5 | Recall@5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in report["variants"]:
        config = variant["config"]
        metrics = variant["development_metrics"]
        lines.append(
            f"| `{config['config_id']}` | {config['candidate_pool_k']} | "
            f"{metrics['ndcg_at_10']:.3f} | {metrics['mrr_at_10']:.3f} | "
            f"{metrics['evidence_group_coverage_at_10']:.3f} | "
            f"{metrics['recall_at_10']:.3f} | "
            f"{metrics['evidence_group_coverage_at_5']:.3f} | "
            f"{metrics['recall_at_5']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_final_summary(
    *,
    manifest: dict[str, Any],
    all_metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    g3_metrics: dict[str, dict[str, Any]],
    breakdowns: dict[str, dict[str, dict[str, Any]]],
) -> str:
    """Render the final selected reranked retrieval summary."""
    lines = [
        "# Frozen Reranked Retrieval",
        "",
        f"- Selected config: `{manifest['selected_reranking_config_id']}`.",
        f"- Reranker model: `{manifest['reranker_model']}`.",
        "- Retrieval-only; no generation or fallback-gate change.",
        "",
        "## Headline Metrics",
        "",
    ]
    for label, metrics in (
        ("all", all_metrics),
        ("development", split_metrics["development"]),
        ("held_out_test", split_metrics["held_out_test"]),
    ):
        lines.append(_metric_line(label, metrics))
    lines.extend(["", "## Delta vs G3", ""])
    current = {
        "all": all_metrics,
        "development": split_metrics["development"],
        "held_out_test": split_metrics["held_out_test"],
    }
    for split_name, deltas in _delta_metrics(current, g3_metrics).items():
        lines.append(
            f"- `{split_name}`: NDCG@10={deltas['ndcg_at_10_delta']:+.3f}; "
            f"MRR@10={deltas['mrr_at_10_delta']:+.3f}; "
            f"Group@10={deltas['evidence_group_coverage_at_10_delta']:+.3f}; "
            f"Recall@10={deltas['recall_at_10_delta']:+.3f}."
        )
    lines.extend(["", "## Weakest Breakdowns", ""])
    for dimension in ("primary_domain", "question_types"):
        lines.extend([f"### {dimension}", ""])
        for row in _weak_rows(breakdowns, dimension):
            lines.append(
                f"- `{row['label']}`: Group@10={row['metric_value']:.3f}, "
                f"Recall@10={row['recall_at_10']:.3f}, queries={row['query_count']}."
            )
        lines.append("")
    return "\n".join(lines)


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    """Render comparison Markdown including the selected reranker."""
    lines = [
        "# Advanced Retrieval Comparison",
        "",
        "| System | Split | Recall@10 | MRR@10 | NDCG@10 | Group@10 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for label, system in comparison["systems"].items():
        for split_name, metrics in system["metrics"].items():
            lines.append(
                f"| `{label}` | `{split_name}` | {metrics['recall_at_10']:.3f} | "
                f"{metrics['mrr_at_10']:.3f} | {metrics['ndcg_at_10']:.3f} | "
                f"{metrics['evidence_group_coverage_at_10']:.3f} |"
            )
    lines.extend(
        [
            "",
            "## Stage H Decision",
            "",
            f"- Adopted: `{comparison['stage_h_ablation']['adopted']}`.",
            f"- Selected config: `{comparison['stage_h_ablation']['selected_config_id']}`.",
            "- Held-out test used for selection: `false`.",
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


def _selection_key(variant: dict[str, Any]) -> tuple[float, float, float, float, float, int]:
    metrics = variant["development_metrics"]
    return (
        metrics["ndcg_at_10"],
        metrics["mrr_at_10"],
        metrics["evidence_group_coverage_at_5"],
        metrics["recall_at_5"],
        -metrics["mean_retrieval_latency_ms"],
        -variant["config"]["simplicity_rank"],
    )


def _score_combination(config: RerankingConfig) -> str:
    if config.no_rerank:
        return "g3_c4_unchanged"
    if config.g3_weight == 0:
        return "reranker_score"
    return f"{config.reranker_weight} * normalized_reranker + {config.g3_weight} * normalized_g3"


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RerankingAblationError(f"expected JSON object: {path}")
    return payload


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
) -> dict[str, dict[str, float]]:
    return {
        split_name: {
            f"{metric}_delta": metrics[metric] - baseline[split_name][metric]
            for metric in (
                "recall_at_10",
                "mrr_at_10",
                "ndcg_at_10",
                "evidence_group_coverage_at_10",
            )
        }
        for split_name, metrics in current.items()
    }


def _metric_line(label: str, metrics: dict[str, Any]) -> str:
    return (
        f"- `{label}`: Recall@10={metrics['recall_at_10']:.3f}, "
        f"MRR@10={metrics['mrr_at_10']:.3f}, NDCG@10={metrics['ndcg_at_10']:.3f}, "
        f"evidence_group_coverage@10={metrics['evidence_group_coverage_at_10']:.3f}"
    )


def math_isclose(left: float, right: float) -> bool:
    """Return deterministic near-equality for metric tie handling."""
    return abs(left - right) <= 1e-12


def git_commit_or_unknown() -> str:
    """Return the current Git commit without exposing environment state."""
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
