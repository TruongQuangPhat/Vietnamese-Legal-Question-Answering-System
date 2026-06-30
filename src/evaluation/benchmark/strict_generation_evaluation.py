"""Strict generation evaluation over coverage-aware quota retrieval."""

from __future__ import annotations

import json
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.evaluation.benchmark.enums import ExpectedDecision, TargetRole
from src.evaluation.benchmark.fingerprinting import sha256_file
from src.evaluation.benchmark.fusion_ablation import (
    config_from_payload,
)
from src.evaluation.benchmark.generation_baseline import (
    aggregate_generation_metrics,
    build_generation_breakdowns,
    evaluate_generation_case,
    status_counts,
)
from src.evaluation.benchmark.loader import (
    BenchmarkFileSet,
    LoadedBenchmarkDataset,
    load_benchmark_dataset,
    load_benchmark_manifest,
    load_split_manifest,
)
from src.evaluation.benchmark.schemas import BenchmarkQuery, EvidenceGroup, EvidenceJudgment
from src.indexing.official_artifacts import write_json_atomic
from src.retrieval.coverage_aware import (
    CoverageAwareFusionConfig,
    CoverageAwareRetrievalError,
)
from src.retrieval.dense_retriever import DenseRetrieverError
from src.retrieval.evaluation import ExpectedTarget
from src.retrieval.generation import RagAnswerResult, RagGenerationConfig
from src.retrieval.generation_evaluation import find_secret_leak_labels
from src.retrieval.llm_client import LLMClientError, LLMClientProtocol
from src.retrieval.models import RetrievalResult
from src.retrieval.rag_pipeline import RagRetrieverProtocol, run_naive_rag
from src.retrieval.selection import EvidenceSelectionConfig
from src.retrieval.sparse_retriever import SparseRetrieverError

RETRIEVAL_STRATEGY = "coverage_aware_quota"
WORKFLOW_NAME = "strict_generation_evaluation"
BASE_GENERATION_BASELINE = "generation_baseline"


@dataclass(frozen=True)
class StrictGenerationPaths:
    """Frozen benchmark inputs and generation report destinations."""

    file_set: BenchmarkFileSet
    split_manifest: Path
    benchmark_manifest: Path
    retrieval_config: Path
    coverage_retrieval_manifest: Path
    generation_baseline_dir: Path
    llm_config: Path
    output_dir: Path


class StrictGenerationEvaluationError(RuntimeError):
    """Raised when strict generation evaluation cannot run safely."""


class FrozenResultRetriever:
    """Return one already-computed result to the generation pipeline."""

    def __init__(self, result: RetrievalResult) -> None:
        self._result = result

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        """Return the injected retrieval result without external I/O."""
        return self._result


async def run_strict_generation_cases(
    *,
    paths: StrictGenerationPaths,
    retriever: RagRetrieverProtocol,
    llm_client: LLMClientProtocol,
    generation_config: RagGenerationConfig,
    selection_config: EvidenceSelectionConfig,
    retrieval_manifest: dict[str, Any],
    provider: str,
    model: str,
    command: list[str],
) -> list[dict[str, Any]]:
    """Run strict generation over the frozen benchmark and write reports.

    The caller injects read-only retrieval and the provider client. This
    function does not construct infrastructure clients or mutate the corpus.
    """
    dataset = load_benchmark_dataset(paths.file_set)
    split_manifest = load_split_manifest(paths.split_manifest)
    benchmark_manifest = load_benchmark_manifest(paths.benchmark_manifest)
    verify_coverage_retrieval_manifest(
        manifest=retrieval_manifest,
        benchmark_version=benchmark_manifest.benchmark_version,
        benchmark_manifest_path=paths.benchmark_manifest,
        split_manifest_path=paths.split_manifest,
        retrieval_config_path=paths.retrieval_config,
    )
    targets_by_query = _targets_by_query(dataset)
    judgments_by_query = _judgments_by_query(dataset.evidence_judgments)
    groups_by_query = _groups_by_query(dataset.evidence_groups)

    case_results: list[dict[str, Any]] = []
    for query in dataset.queries:
        case_results.append(
            await evaluate_strict_generation_query(
                query=query,
                split=split_manifest.assignments[query.id].value,
                retriever=retriever,
                llm_client=llm_client,
                generation_config=generation_config,
                selection_config=selection_config,
                collection_name=str(retrieval_manifest["qdrant_collection_name"]),
                final_top_k=int(retrieval_manifest["final_top_k"]),
                expected_targets=_expected_targets_for_query(query, targets_by_query),
                judgments=judgments_by_query.get(query.id, []),
                groups=groups_by_query.get(query.id, []),
            )
        )

    write_strict_generation_outputs(
        paths=paths,
        case_results=case_results,
        benchmark_version=benchmark_manifest.benchmark_version,
        retrieval_manifest=retrieval_manifest,
        generation_config=generation_config,
        selection_config=selection_config,
        provider=provider,
        model=model,
        command=command,
    )
    return case_results


async def evaluate_strict_generation_query(
    *,
    query: BenchmarkQuery,
    split: str,
    retriever: RagRetrieverProtocol,
    llm_client: LLMClientProtocol,
    generation_config: RagGenerationConfig,
    selection_config: EvidenceSelectionConfig,
    collection_name: str,
    final_top_k: int,
    expected_targets: list[ExpectedTarget] | None,
    judgments: list[EvidenceJudgment],
    groups: list[EvidenceGroup],
) -> dict[str, Any]:
    """Evaluate one query while separating retrieval and generation errors."""
    started = time.perf_counter()
    retrieval_error: str | None = None
    generation_error: str | None = None
    retrieval_result: RetrievalResult | None = None
    rag_result: RagAnswerResult | None = None
    try:
        retrieval_result = await retriever.retrieve(
            query=query.query,
            top_k=final_top_k,
            collection_name=collection_name,
        )
    except (
        DenseRetrieverError,
        CoverageAwareRetrievalError,
        SparseRetrieverError,
        StrictGenerationEvaluationError,
        ValueError,
        ValidationError,
    ) as exc:
        retrieval_error = str(exc)

    if retrieval_result is not None:
        try:
            rag_result = await run_naive_rag(
                query=query.query,
                retriever=FrozenResultRetriever(retrieval_result),
                llm_client=llm_client,
                collection_name=collection_name,
                top_k=final_top_k,
                selection_config=selection_config,
                generation_config=generation_config,
                expected_targets=expected_targets,
            )
        except (LLMClientError, ValueError, ValidationError) as exc:
            generation_error = str(exc)
        else:
            if rag_result.errors:
                generation_error = "; ".join(rag_result.errors)

    elapsed_ms = (time.perf_counter() - started) * 1000
    case = evaluate_generation_case(
        query=query,
        split=split,
        result=rag_result,
        retrieved_chunks=[
            {
                "chunk_id": chunk.chunk_id,
                "rank": chunk.rank,
                "score": chunk.score,
            }
            for chunk in retrieval_result.results
        ]
        if retrieval_result is not None
        else [],
        judgments=judgments,
        groups=groups,
        elapsed_ms=elapsed_ms,
        error=generation_error or retrieval_error,
    )
    case["retrieval_error"] = retrieval_error
    case["generation_error"] = generation_error
    return case


def aggregate_strict_generation_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate canonical generation metrics plus retrieval failures."""
    metrics = aggregate_generation_metrics(cases)
    metrics["generation_error_count"] = sum(1 for case in cases if case.get("generation_error"))
    metrics["retrieval_error_count"] = sum(1 for case in cases if case.get("retrieval_error"))
    return metrics


def build_strict_generation_breakdowns(
    cases: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build canonical breakdowns with strict retrieval error counts."""
    canonical = build_generation_breakdowns(cases)
    dimensions = {
        "split": lambda case: [case["split"]],
        "primary_domain": lambda case: [case["primary_domain"]],
        "expected_decision": lambda case: [case["expected_decision"]],
        "question_types": lambda case: case["question_types"],
        "blocking": lambda case: [str(bool(case.get("blocking", False)))],
    }
    for dimension, labels_getter in dimensions.items():
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in cases:
            for label in labels_getter(case):
                buckets[str(label)].append(case)
        canonical[dimension] = {
            label: aggregate_strict_generation_metrics(bucket)
            for label, bucket in sorted(buckets.items())
        }
    return canonical


def verify_coverage_retrieval_manifest(
    *,
    manifest: dict[str, Any],
    benchmark_version: str,
    benchmark_manifest_path: Path,
    split_manifest_path: Path,
    retrieval_config_path: Path,
) -> CoverageAwareFusionConfig:
    """Validate the fixed retrieval strategy and frozen input fingerprints."""
    if manifest.get("retrieval_method") != RETRIEVAL_STRATEGY:
        raise StrictGenerationEvaluationError(f"retrieval_method must be {RETRIEVAL_STRATEGY}")
    if manifest.get("benchmark_version") != benchmark_version:
        raise StrictGenerationEvaluationError("retrieval benchmark_version mismatch")
    checks = {
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "dense_config_sha256": sha256_file(retrieval_config_path),
    }
    for key, expected_hash in checks.items():
        if manifest.get(key) != expected_hash:
            raise StrictGenerationEvaluationError(f"retrieval {key} mismatch")
    selected = manifest.get("selected_config")
    if not isinstance(selected, dict):
        raise StrictGenerationEvaluationError("retrieval selected_config is missing")
    config = config_from_payload(selected)
    if config.mode != "quota" or config.config_id != "selected_coverage_aware_quota":
        raise StrictGenerationEvaluationError(
            "retrieval selected_config must be selected_coverage_aware_quota"
        )
    if manifest.get("final_top_k") != config.final_top_k:
        raise StrictGenerationEvaluationError("retrieval final_top_k mismatch")
    return config


def write_strict_generation_outputs(
    *,
    paths: StrictGenerationPaths,
    case_results: list[dict[str, Any]],
    benchmark_version: str,
    retrieval_manifest: dict[str, Any],
    generation_config: RagGenerationConfig,
    selection_config: EvidenceSelectionConfig,
    provider: str,
    model: str,
    command: list[str],
) -> None:
    """Write strict generation metrics, manifest, summary, and comparison."""
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    metrics = aggregate_strict_generation_metrics(case_results)
    breakdowns = build_strict_generation_breakdowns(case_results)
    split_metrics = breakdowns["split"]
    _write_jsonl_atomic(paths.output_dir / "case_results.jsonl", case_results)
    write_json_atomic(paths.output_dir / "metrics_all.json", metrics)
    write_json_atomic(
        paths.output_dir / "metrics_development.json",
        split_metrics.get("development", {}),
    )
    write_json_atomic(
        paths.output_dir / "metrics_held_out_test.json",
        split_metrics.get("held_out_test", {}),
    )
    write_json_atomic(paths.output_dir / "breakdowns.json", breakdowns)
    manifest = build_strict_generation_manifest(
        paths=paths,
        benchmark_version=benchmark_version,
        retrieval_manifest=retrieval_manifest,
        generation_config=generation_config,
        selection_config=selection_config,
        provider=provider,
        model=model,
        command=command,
        query_count=len(case_results),
    )
    write_json_atomic(paths.output_dir / "baseline_manifest.json", manifest)
    (paths.output_dir / "generation_summary.md").write_text(
        render_generation_summary(
            metrics=metrics,
            split_metrics=split_metrics,
            statuses=status_counts(case_results),
            provider=provider,
            model=model,
        ),
        encoding="utf-8",
    )
    comparison = build_generation_comparison(
        current_dir=paths.output_dir,
        baseline_dir=paths.generation_baseline_dir,
    )
    write_json_atomic(paths.output_dir / "comparison.json", comparison)
    (paths.output_dir / "comparison.md").write_text(
        render_generation_comparison(comparison),
        encoding="utf-8",
    )
    _assert_no_secret_artifacts(paths.output_dir)


def build_strict_generation_manifest(
    *,
    paths: StrictGenerationPaths,
    benchmark_version: str,
    retrieval_manifest: dict[str, Any],
    generation_config: RagGenerationConfig,
    selection_config: EvidenceSelectionConfig,
    provider: str,
    model: str,
    command: list[str],
    query_count: int,
) -> dict[str, Any]:
    """Build functional, secret-free strict evaluation metadata."""
    manifest = {
        "report_type": WORKFLOW_NAME,
        "workflow_name": WORKFLOW_NAME,
        "retrieval_strategy": RETRIEVAL_STRATEGY,
        "base_generation_baseline": BASE_GENERATION_BASELINE,
        "benchmark_version": benchmark_version,
        "benchmark_manifest_sha256": sha256_file(paths.benchmark_manifest),
        "split_manifest_sha256": sha256_file(paths.split_manifest),
        "coverage_retrieval_manifest_sha256": sha256_file(paths.coverage_retrieval_manifest),
        "generation_baseline_manifest_sha256": sha256_file(
            paths.generation_baseline_dir / "baseline_manifest.json"
        ),
        "retrieval_config_path": str(paths.retrieval_config),
        "retrieval_config_sha256": sha256_file(paths.retrieval_config),
        "llm_provider_config_path": str(paths.llm_config),
        "llm_provider_config_sha256": sha256_file(paths.llm_config),
        "qdrant_collection_name": retrieval_manifest["qdrant_collection_name"],
        "vector_name": retrieval_manifest["vector_name"],
        "embedding_model": retrieval_manifest["embedding_model"],
        "retrieval_settings": {
            "dense_candidate_k": retrieval_manifest["dense_candidate_k"],
            "sparse_candidate_k": retrieval_manifest["sparse_candidate_k"],
            "final_top_k": retrieval_manifest["final_top_k"],
            "rrf_k": retrieval_manifest["rrf_k"],
            "dense_weight": retrieval_manifest["dense_weight"],
            "sparse_weight": retrieval_manifest["sparse_weight"],
            "quota": retrieval_manifest["quota"],
        },
        "generation_config": {
            "provider": provider,
            "model": model,
            "temperature": generation_config.temperature,
            "max_tokens": generation_config.max_tokens,
            "timeout_s": generation_config.timeout_s,
            "include_auxiliary_context": generation_config.include_auxiliary_context,
            "fail_on_invalid_citation": generation_config.fail_on_invalid_citation,
        },
        "evidence_selection_config": selection_config.model_dump(mode="json"),
        "reranking_used": False,
        "held_out_used_for_tuning": False,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "command": command,
        "query_count": query_count,
        "artifacts_produced": [
            str(paths.output_dir / name)
            for name in (
                "baseline_manifest.json",
                "metrics_all.json",
                "metrics_development.json",
                "metrics_held_out_test.json",
                "breakdowns.json",
                "case_results.jsonl",
                "generation_summary.md",
                "comparison.json",
                "comparison.md",
            )
        ],
        "known_limitations": [
            "retrieval and generation evaluation only",
            "no reranking",
            "no claim-level human semantic faithfulness review",
            "provider output may be nondeterministic",
            "held_out_test is reported only after the retrieval and generation policy is fixed",
            "held_out_test excludes high-risk sanction/criminal QA",
            "qualified human legal review has not occurred",
        ],
    }
    if not generation_config.fail_on_invalid_citation:
        raise StrictGenerationEvaluationError("strict citation fallback must remain enabled")
    _assert_no_secret_keys(manifest)
    return manifest


def build_generation_comparison(
    *,
    current_dir: Path,
    baseline_dir: Path,
) -> dict[str, Any]:
    """Compare strict generation metrics with the frozen generation baseline."""
    systems = {
        BASE_GENERATION_BASELINE: _load_metric_set(baseline_dir),
        WORKFLOW_NAME: _load_metric_set(current_dir),
    }
    deltas = {
        split: _metric_deltas(
            systems[WORKFLOW_NAME][split],
            systems[BASE_GENERATION_BASELINE][split],
        )
        for split in ("all", "development", "held_out_test")
    }
    current = systems[WORKFLOW_NAME]["all"]
    baseline = systems[BASE_GENERATION_BASELINE]["all"]
    questions = {
        "decision_accuracy_improved": current["decision_accuracy"] > baseline["decision_accuracy"],
        "answer_allowed_answer_rate_improved": current["answer_allowed_answer_rate"]
        > baseline["answer_allowed_answer_rate"],
        "fallback_required_fallback_rate_remained_safe": current["fallback_required_fallback_rate"]
        >= baseline["fallback_required_fallback_rate"],
        "selected_evidence_group_coverage_improved": current["selected_evidence_group_coverage"]
        > baseline["selected_evidence_group_coverage"],
        "case_pass_rate_improved": current["case_pass_rate"] > baseline["case_pass_rate"],
        "citation_validity_remained_strict": current["citation_id_validity_rate"]
        >= baseline["citation_id_validity_rate"],
        "retrieval_error_count_acceptable": current["retrieval_error_count"] == 0,
        "generation_error_count_acceptable": current["generation_error_count"]
        <= baseline["generation_error_count"],
    }
    return {
        "report_type": "strict_generation_comparison",
        "workflow_name": WORKFLOW_NAME,
        "retrieval_strategy": RETRIEVAL_STRATEGY,
        "base_generation_baseline": BASE_GENERATION_BASELINE,
        "systems": systems,
        "deltas": deltas,
        "key_questions": questions,
    }


def render_generation_summary(
    *,
    metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    statuses: dict[str, int],
    provider: str,
    model: str,
) -> str:
    """Render the strict generation summary."""
    lines = [
        "# Strict Generation Evaluation",
        "",
        "## Scope",
        "",
        f"- Retrieval strategy: `{RETRIEVAL_STRATEGY}`.",
        f"- Provider/model: `{provider}` / `{model}`.",
        "- Evidence gate defaults are preserved.",
        "- Invalid or unselected citation IDs force fallback.",
        "- Reranking is disabled.",
        "- Held-out results are reporting-only.",
        "",
        "## Metrics",
        "",
        _metric_line("all", metrics),
    ]
    for split in ("development", "held_out_test"):
        if split in split_metrics:
            lines.append(_metric_line(split, split_metrics[split]))
    lines.extend(
        [
            "",
            "## Case Status",
            "",
            f"- pass: {statuses.get('pass', 0)}",
            f"- partial: {statuses.get('partial', 0)}",
            f"- fail: {statuses.get('fail', 0)}",
            "",
        ]
    )
    return "\n".join(lines)


def render_generation_comparison(comparison: dict[str, Any]) -> str:
    """Render the generation baseline comparison."""
    lines = [
        "# Strict Generation Comparison",
        "",
        "| System | Split | Decision accuracy | Answer rate | Safe fallback rate | "
        "Group coverage | Pass rate | Citation validity | Retrieval errors | "
        "Generation errors |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for system_name, split_metrics in comparison["systems"].items():
        for split_name, metrics in split_metrics.items():
            lines.append(
                f"| `{system_name}` | `{split_name}` | "
                f"{metrics['decision_accuracy']:.3f} | "
                f"{metrics['answer_allowed_answer_rate']:.3f} | "
                f"{metrics['fallback_required_fallback_rate']:.3f} | "
                f"{metrics['selected_evidence_group_coverage']:.3f} | "
                f"{metrics['case_pass_rate']:.3f} | "
                f"{metrics['citation_id_validity_rate']:.3f} | "
                f"{metrics['retrieval_error_count']} | "
                f"{metrics['generation_error_count']} |"
            )
    lines.extend(["", "## Key Questions", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in comparison["key_questions"].items())
    lines.append("")
    return "\n".join(lines)


def _metric_line(label: str, metrics: dict[str, Any]) -> str:
    return (
        f"- `{label}`: queries={metrics.get('query_count', 0)}, "
        f"decision_accuracy={metrics.get('decision_accuracy', 0.0):.3f}, "
        f"answer_rate={metrics.get('answer_allowed_answer_rate', 0.0):.3f}, "
        f"fallback_rate={metrics.get('fallback_required_fallback_rate', 0.0):.3f}, "
        f"group_coverage={metrics.get('selected_evidence_group_coverage', 0.0):.3f}, "
        f"pass_rate={metrics.get('case_pass_rate', 0.0):.3f}, "
        f"citation_validity={metrics.get('citation_id_validity_rate', 0.0):.3f}, "
        f"retrieval_errors={metrics.get('retrieval_error_count', 0)}, "
        f"generation_errors={metrics.get('generation_error_count', 0)}"
    )


def _metric_deltas(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, float | int]:
    names = (
        "decision_accuracy",
        "answer_allowed_answer_rate",
        "fallback_required_fallback_rate",
        "selected_evidence_group_coverage",
        "case_pass_rate",
        "citation_id_validity_rate",
        "retrieval_error_count",
        "generation_error_count",
    )
    return {f"{name}_delta": current[name] - baseline[name] for name in names}


def _load_metric_set(report_dir: Path) -> dict[str, dict[str, Any]]:
    files = {
        "all": "metrics_all.json",
        "development": "metrics_development.json",
        "held_out_test": "metrics_held_out_test.json",
    }
    metrics: dict[str, dict[str, Any]] = {}
    for label, filename in files.items():
        payload = json.loads((report_dir / filename).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise StrictGenerationEvaluationError(f"invalid metrics object: {filename}")
        normalized = dict(payload)
        normalized.setdefault("retrieval_error_count", 0)
        metrics[label] = normalized
    return metrics


def _judgments_by_query(
    records: list[EvidenceJudgment],
) -> dict[str, list[EvidenceJudgment]]:
    grouped: dict[str, list[EvidenceJudgment]] = defaultdict(list)
    for record in records:
        grouped[record.query_id].append(record)
    return grouped


def _groups_by_query(records: list[EvidenceGroup]) -> dict[str, list[EvidenceGroup]]:
    grouped: dict[str, list[EvidenceGroup]] = defaultdict(list)
    for record in records:
        grouped[record.query_id].append(record)
    return grouped


def _targets_by_query(
    dataset: LoadedBenchmarkDataset,
) -> dict[str, list[ExpectedTarget]]:
    grouped: dict[str, list[ExpectedTarget]] = defaultdict(list)
    for target in dataset.legal_targets:
        if target.target_role not in {TargetRole.REQUIRED, TargetRole.ALTERNATIVE}:
            continue
        grouped[target.query_id].append(
            ExpectedTarget(
                law_id=target.law_id,
                article_number=target.article_number,
                clause_number=target.clause_number,
                point_label=target.point_label,
                match_level=target.match_level.value,
            )
        )
    return grouped


def _expected_targets_for_query(
    query: BenchmarkQuery,
    targets_by_query: dict[str, list[ExpectedTarget]],
) -> list[ExpectedTarget] | None:
    """Return strict evaluation targets while preserving fallback-required intent."""
    if query.expected_decision == ExpectedDecision.FALLBACK_REQUIRED:
        return []
    return targets_by_query.get(query.id)


def _write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def _assert_no_secret_artifacts(output_dir: Path) -> None:
    for path in output_dir.iterdir():
        if path.is_file() and find_secret_leak_labels(path.read_text(encoding="utf-8")):
            raise StrictGenerationEvaluationError(
                f"refusing artifact with secret-like content: {path}"
            )


def _assert_no_secret_keys(value: Any) -> None:
    forbidden = ("api_key", "authorization", "access_token", "secret")
    if isinstance(value, dict):
        for key, item in value.items():
            if any(marker in key.lower() for marker in forbidden):
                raise StrictGenerationEvaluationError(f"manifest contains secret-shaped key: {key}")
            _assert_no_secret_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_secret_keys(item)


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None
