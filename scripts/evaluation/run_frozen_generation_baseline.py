#!/usr/bin/env python3
"""Run frozen Naive RAG generation baseline using dense retrieval artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml
from pydantic import ValidationError

from src.evaluation.benchmark.enums import TargetRole
from src.evaluation.benchmark.exceptions import BenchmarkLoadError
from src.evaluation.benchmark.fingerprinting import (
    add_benchmark_output_policy_argument,
    sha256_file,
    validate_benchmark_output_dir,
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
from src.retrieval.evaluation import ExpectedTarget
from src.retrieval.generation import RagGenerationConfig
from src.retrieval.generation_evaluation import find_secret_leak_labels
from src.retrieval.llm_client import LLMClientError, OpenRouterLLMClient
from src.retrieval.models import RetrievalResult, RetrievedChunk
from src.retrieval.openrouter_config import load_project_dotenv, resolve_openrouter_settings
from src.retrieval.rag_pipeline import run_naive_rag
from src.retrieval.selection import EvidenceSelectionConfig
from src.retrieval.workflows.common import DEFAULT_CONFIG

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_REPORTS_ROOT = REPO_ROOT / "artifacts/reports/evaluation"
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation/naive_rag_baseline/generation")
DEFAULT_RETRIEVAL_DIR = Path("artifacts/reports/evaluation/naive_rag_baseline/retrieval")
DEFAULT_QUERIES = Path("data/eval/legal_qa_benchmark/benchmark_queries.jsonl")
DEFAULT_TARGETS = Path("data/eval/legal_qa_benchmark/benchmark_targets.jsonl")
DEFAULT_QRELS = Path("data/eval/legal_qa_benchmark/benchmark_qrels.jsonl")
DEFAULT_GROUPS = Path("data/eval/legal_qa_benchmark/evidence_groups.jsonl")
DEFAULT_REVIEWS = Path("data/eval/legal_qa_benchmark/review_records.jsonl")
DEFAULT_SPLIT_MANIFEST = Path("data/eval/legal_qa_benchmark/split_manifest.json")
DEFAULT_BENCHMARK_MANIFEST = Path("data/eval/legal_qa_benchmark/benchmark_manifest.json")
DEFAULT_PROCESSED_CHUNKS = Path("data/processed/legal_chunks.jsonl")
DEFAULT_LLM_CONFIG = Path("configs/llm/openrouter.yml")


class FrozenRetrievalService:
    """Retriever adapter returning one frozen dense result without Qdrant."""

    def __init__(self, retrieval_result: RetrievalResult) -> None:
        self._retrieval_result = retrieval_result

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        """Return the precomputed retrieval result for the current case."""
        return self._retrieval_result


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the frozen generation baseline CLI parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/evaluation/run_frozen_generation_baseline.py",
        description=(
            "Run Naive RAG generation over the frozen legal QA benchmark using dense retrieval."
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
    parser.add_argument("--processed-chunks", type=Path, default=DEFAULT_PROCESSED_CHUNKS)
    parser.add_argument("--retrieval-dir", type=Path, default=DEFAULT_RETRIEVAL_DIR)
    parser.add_argument("--retrieval-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--llm-config", type=Path, default=DEFAULT_LLM_CONFIG)
    parser.add_argument("--provider", choices=["openrouter"], default="openrouter")
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--no-auxiliary-context", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    add_benchmark_output_policy_argument(parser)
    parser.add_argument("--sample-development", type=int, default=None)
    parser.add_argument("--sample-held-out", type=int, default=None)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load project dotenv and run the asynchronous generation baseline."""
    load_project_dotenv()
    return asyncio.run(run_baseline(argv))


async def run_baseline(argv: list[str] | None = None) -> int:
    """Run frozen benchmark generation using compatible dense retrieval results."""
    args = build_arg_parser().parse_args(argv)
    try:
        validate_cli_arguments(args)
        dataset = load_benchmark_dataset(
            BenchmarkFileSet(
                queries=args.queries,
                legal_targets=args.legal_targets,
                evidence_judgments=args.evidence_judgments,
                evidence_groups=args.evidence_groups,
                review_records=args.review_records,
            )
        )
        split_manifest = load_split_manifest(args.split_manifest)
        benchmark_manifest = load_benchmark_manifest(args.benchmark_manifest)
        retrieval_manifest_path = args.retrieval_dir / "baseline_manifest.json"
        retrieval_cases_path = args.retrieval_dir / "case_results.jsonl"
        retrieval_manifest = load_json_object(retrieval_manifest_path)
        retrieval_cases = load_jsonl_objects(retrieval_cases_path)
        verify_retrieval_compatibility(
            retrieval_manifest=retrieval_manifest,
            retrieval_cases=retrieval_cases,
            benchmark_version=benchmark_manifest.benchmark_version,
            benchmark_manifest_path=args.benchmark_manifest,
            split_manifest_path=args.split_manifest,
            retrieval_config_path=args.retrieval_config,
            expected_query_count=len(dataset.queries),
        )
        chunk_lookup = load_processed_chunk_lookup(args.processed_chunks)
        selected_queries = select_queries(
            dataset.queries,
            split_manifest.assignments,
            sample_development=args.sample_development,
            sample_held_out=args.sample_held_out,
        )
        judgments_by_query = _judgments_by_query(dataset.evidence_judgments)
        groups_by_query = _groups_by_query(dataset.evidence_groups)
        targets_by_query = _targets_by_query(dataset)
        retrieval_by_query = {case["query_id"]: case for case in retrieval_cases}
        openrouter = resolve_openrouter_settings(cli_model=args.model, config_path=args.llm_config)
        llm_client = OpenRouterLLMClient(
            base_url=openrouter.base_url, default_model=openrouter.model
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
        selection_config = EvidenceSelectionConfig(
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=False,
            include_auxiliary_context_in_rendered_output=not args.no_auxiliary_context,
        )

        case_results: list[dict[str, Any]] = []
        for query in selected_queries:
            started = perf_counter()
            error: str | None = None
            rag_result: Any | None = None
            dense_baseline_case = retrieval_by_query[query.id]
            try:
                retrieval_result = build_retrieval_result(
                    query=query,
                    dense_baseline_case=dense_baseline_case,
                    chunk_lookup=chunk_lookup,
                    collection_name=retrieval_manifest["qdrant_collection_name"],
                    vector_name=retrieval_manifest["vector_name"],
                    top_k=int(retrieval_manifest["top_k"]),
                    query_vector_dimension=int(
                        retrieval_manifest["retrieval_config"]["dense_retrieval"][
                            "expected_vector_dim"
                        ]
                    ),
                )
                rag_result = await run_naive_rag(
                    query=query.query,
                    retriever=FrozenRetrievalService(retrieval_result),
                    llm_client=llm_client,
                    collection_name=retrieval_manifest["qdrant_collection_name"],
                    top_k=int(retrieval_manifest["top_k"]),
                    selection_config=selection_config,
                    generation_config=generation_config,
                    expected_targets=targets_by_query.get(query.id),
                )
            except (ValueError, LLMClientError, ValidationError) as exc:
                error = str(exc)
            elapsed_ms = (perf_counter() - started) * 1000
            case_results.append(
                evaluate_generation_case(
                    query=query,
                    split=split_manifest.assignments[query.id].value,
                    result=rag_result,
                    retrieved_chunks=dense_baseline_case["retrieved"],
                    judgments=judgments_by_query.get(query.id, []),
                    groups=groups_by_query.get(query.id, []),
                    elapsed_ms=elapsed_ms,
                    error=error,
                )
            )

        write_outputs(
            output_dir=args.output_dir,
            case_results=case_results,
            benchmark_manifest_path=args.benchmark_manifest,
            split_manifest_path=args.split_manifest,
            retrieval_manifest_path=retrieval_manifest_path,
            retrieval_config_path=args.retrieval_config,
            llm_config_path=args.llm_config,
            benchmark_version=benchmark_manifest.benchmark_version,
            generation_config=generation_config,
            model=openrouter.model,
            provider=args.provider,
            command=["python", *sys.argv],
            sample_mode=args.sample_development is not None or args.sample_held_out is not None,
        )
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValueError,
        ValidationError,
        BenchmarkLoadError,
    ) as exc:
        print(f"Frozen generation baseline failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    if not args.quiet:
        metrics = aggregate_generation_metrics(case_results)
        split_metrics = build_generation_breakdowns(case_results)["split"]
        print("Frozen Naive RAG Generation Baseline")
        print(f"Benchmark version: {benchmark_manifest.benchmark_version}")
        print(f"Provider/model: {args.provider}/{openrouter.model}")
        print(f"Queries: {metrics['query_count']} | Errors: {metrics['generation_error_count']}")
        for split_name, split_data in split_metrics.items():
            print(
                f"{split_name}: decision_accuracy={split_data['decision_accuracy']:.3f} "
                f"answer_rate={split_data['answer_allowed_answer_rate']:.3f} "
                f"fallback_rate={split_data['fallback_required_fallback_rate']:.3f} "
                f"citation_validity={split_data['citation_id_validity_rate']:.3f}"
            )
        print(f"Artifacts: {args.output_dir}")
    return EXIT_SUCCESS


def validate_cli_arguments(args: argparse.Namespace) -> None:
    """Validate bounded generation settings and approved artifact paths."""
    if not args.retrieval_dir.is_dir():
        raise ValueError(f"Dense retrieval artifact directory not found: {args.retrieval_dir}")
    if not (args.retrieval_dir / "baseline_manifest.json").is_file():
        raise ValueError("Dense retrieval baseline_manifest.json is missing")
    if not (args.retrieval_dir / "case_results.jsonl").is_file():
        raise ValueError("Dense retrieval case_results.jsonl is missing")
    if not args.processed_chunks.is_file():
        raise ValueError(f"processed chunks file not found: {args.processed_chunks}")
    if args.max_tokens <= 0:
        raise ValueError("max-tokens must be positive")
    if args.timeout_s <= 0:
        raise ValueError("timeout-s must be positive")
    if not 0 <= args.temperature <= 2:
        raise ValueError("temperature must be between 0 and 2")
    for value, label in (
        (args.sample_development, "sample-development"),
        (args.sample_held_out, "sample-held-out"),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{label} must be non-negative")
    validate_benchmark_output_dir(
        args.output_dir,
        repo_root=REPO_ROOT,
        evaluation_reports_root=EVALUATION_REPORTS_ROOT,
        output_policy=args.output_policy,
        label="output-dir",
    )


def verify_retrieval_compatibility(
    *,
    retrieval_manifest: dict[str, Any],
    retrieval_cases: list[dict[str, Any]],
    benchmark_version: str,
    benchmark_manifest_path: Path,
    split_manifest_path: Path,
    retrieval_config_path: Path,
    expected_query_count: int,
) -> None:
    """Require dense retrieval artifacts to match current frozen inputs."""
    if retrieval_manifest.get("benchmark_version") != benchmark_version:
        raise ValueError("Dense retrieval benchmark_version does not match current benchmark")
    checks = {
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "retrieval_config_sha256": sha256_file(retrieval_config_path),
    }
    for key, current_hash in checks.items():
        if retrieval_manifest.get(key) != current_hash:
            raise ValueError(f"Dense retrieval {key} does not match current file")
    if len(retrieval_cases) != expected_query_count:
        raise ValueError(
            "Dense retrieval query count "
            f"{len(retrieval_cases)} does not match benchmark {expected_query_count}"
        )
    error_count = sum(1 for case in retrieval_cases if case.get("retrieval_error"))
    if error_count:
        raise ValueError(f"Dense retrieval artifacts contain {error_count} retrieval errors")


def select_queries(
    queries: list[BenchmarkQuery],
    assignments: dict[str, Any],
    *,
    sample_development: int | None,
    sample_held_out: int | None,
) -> list[BenchmarkQuery]:
    """Select either all queries or a deterministic dry-run split sample."""
    if sample_development is None and sample_held_out is None:
        return queries
    dev_limit = sample_development or 0
    held_limit = sample_held_out or 0
    selected: list[BenchmarkQuery] = []
    dev_count = 0
    held_count = 0
    for query in queries:
        split = assignments[query.id].value
        if split == "development" and dev_count < dev_limit:
            selected.append(query)
            dev_count += 1
        elif split == "held_out_test" and held_count < held_limit:
            selected.append(query)
            held_count += 1
    if not selected:
        raise ValueError("dry-run sample selected no queries")
    return selected


def build_retrieval_result(
    *,
    query: BenchmarkQuery,
    dense_baseline_case: dict[str, Any],
    chunk_lookup: dict[str, dict[str, Any]],
    collection_name: str,
    vector_name: str,
    top_k: int,
    query_vector_dimension: int,
) -> RetrievalResult:
    """Reconstruct a typed retrieval result from frozen dense IDs and processed chunks."""
    chunks: list[RetrievedChunk] = []
    for item in dense_baseline_case["retrieved"]:
        chunk_id = item["chunk_id"]
        payload = chunk_lookup.get(chunk_id)
        if payload is None:
            raise ValueError(f"retrieved chunk_id not found in processed chunks: {chunk_id}")
        chunk_payload = {
            key: payload.get(key)
            for key in RetrievedChunk.model_fields
            if key in payload and key not in {"rank", "score", "issues"}
        }
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        chunk_payload.update(
            {
                "rank": item["rank"],
                "score": item["score"],
                "is_empty_or_repealed": metadata.get("is_empty_or_repealed"),
                "is_source_unit_repealed": metadata.get("is_source_unit_repealed"),
            }
        )
        chunks.append(RetrievedChunk.model_validate(chunk_payload))
    return RetrievalResult(
        query=query.query,
        collection_name=collection_name,
        vector_name=vector_name,
        top_k=top_k,
        elapsed_ms=float(dense_baseline_case.get("elapsed_ms") or 0.0),
        query_vector_dimension=query_vector_dimension,
        results=chunks,
        issues=[],
    )


def load_processed_chunk_lookup(path: Path) -> dict[str, dict[str, Any]]:
    """Load processed chunks by ID without mutating the corpus file."""
    lookup: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            chunk_id = payload.get("chunk_id")
            if not isinstance(chunk_id, str):
                raise ValueError(f"processed chunk missing chunk_id at {path}:{line_number}")
            lookup[chunk_id] = payload
    return lookup


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    """Load JSONL objects."""
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


def write_outputs(
    *,
    output_dir: Path,
    case_results: list[dict[str, Any]],
    benchmark_manifest_path: Path,
    split_manifest_path: Path,
    retrieval_manifest_path: Path,
    retrieval_config_path: Path,
    llm_config_path: Path,
    benchmark_version: str,
    generation_config: RagGenerationConfig,
    model: str,
    provider: str,
    command: list[str],
    sample_mode: bool,
) -> None:
    """Write generation baseline artifacts with secret screening."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = aggregate_generation_metrics(case_results)
    breakdowns = build_generation_breakdowns(case_results)
    split_metrics = breakdowns["split"]
    write_jsonl_atomic(output_dir / "case_results.jsonl", case_results)
    write_json_atomic(output_dir / "metrics_all.json", metrics)
    write_json_atomic(output_dir / "metrics_development.json", split_metrics.get("development", {}))
    write_json_atomic(
        output_dir / "metrics_held_out_test.json", split_metrics.get("held_out_test", {})
    )
    write_json_atomic(output_dir / "breakdowns.json", breakdowns)
    manifest = build_manifest(
        output_dir=output_dir,
        benchmark_version=benchmark_version,
        benchmark_manifest_path=benchmark_manifest_path,
        split_manifest_path=split_manifest_path,
        retrieval_manifest_path=retrieval_manifest_path,
        retrieval_config_path=retrieval_config_path,
        llm_config_path=llm_config_path,
        generation_config=generation_config,
        model=model,
        provider=provider,
        command=command,
        query_count=len(case_results),
        sample_mode=sample_mode,
    )
    write_json_atomic(output_dir / "baseline_manifest.json", manifest)
    (output_dir / "summary.md").write_text(
        render_summary(
            metrics=metrics,
            split_metrics=split_metrics,
            status=status_counts(case_results),
            model=model,
            provider=provider,
            sample_mode=sample_mode,
        ),
        encoding="utf-8",
    )
    assert_no_secret_artifacts(output_dir)


def build_manifest(
    *,
    output_dir: Path,
    benchmark_version: str,
    benchmark_manifest_path: Path,
    split_manifest_path: Path,
    retrieval_manifest_path: Path,
    retrieval_config_path: Path,
    llm_config_path: Path,
    generation_config: RagGenerationConfig,
    model: str,
    provider: str,
    command: list[str],
    query_count: int,
    sample_mode: bool,
) -> dict[str, Any]:
    """Build a secret-free generation baseline manifest."""
    return {
        "report_type": "frozen_naive_rag_generation_baseline_manifest",
        "benchmark_version": benchmark_version,
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "dense_retrieval_baseline_manifest_sha256": sha256_file(retrieval_manifest_path),
        "generation_config": {
            "provider": provider,
            "model": model,
            "temperature": generation_config.temperature,
            "max_tokens": generation_config.max_tokens,
            "timeout_s": generation_config.timeout_s,
            "include_auxiliary_context": generation_config.include_auxiliary_context,
            "fail_on_invalid_citation": generation_config.fail_on_invalid_citation,
        },
        "llm_provider_config_path": str(llm_config_path),
        "llm_provider_config_sha256": sha256_file(llm_config_path),
        "retrieval_config_path": str(retrieval_config_path),
        "retrieval_config_sha256": sha256_file(retrieval_config_path),
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "command": command,
        "sample_mode": sample_mode,
        "query_count": query_count,
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
            "Naive RAG baseline only",
            "uses frozen dense retrieval results",
            "no hybrid retrieval",
            "no reranking",
            "no query rewriting",
            "held_out_test excludes high-risk sanction/criminal QA",
            "qualified human legal review has not occurred",
            "LLM outputs may be nondeterministic unless temperature/seed are fixed",
        ],
    }


def render_summary(
    *,
    metrics: dict[str, Any],
    split_metrics: dict[str, dict[str, Any]],
    status: dict[str, int],
    model: str,
    provider: str,
    sample_mode: bool,
) -> str:
    """Render a concise Markdown summary."""
    lines = [
        "# Frozen Naive RAG Generation Baseline",
        "",
        "## Scope",
        "",
        "- Benchmark version is recorded in `baseline_manifest.json`.",
        "- Uses frozen dense retrieval results.",
        f"- LLM provider/model: `{provider}` / `{model}`.",
        f"- Sample mode: `{str(sample_mode).lower()}`.",
        "- No sparse retrieval, fusion, reranking, query rewriting, or Advanced RAG.",
        "- `held_out_test` is scoped to low/medium-risk cases only.",
        "",
        "## Headline Metrics",
        "",
        _metric_line("all", metrics),
    ]
    for split_name in ("development", "held_out_test"):
        if split_name in split_metrics:
            lines.append(_metric_line(split_name, split_metrics[split_name]))
    lines.extend(
        [
            "",
            "## Case Status",
            "",
            f"- pass: {status.get('pass', 0)}",
            f"- partial: {status.get('partial', 0)}",
            f"- fail: {status.get('fail', 0)}",
            "",
            "## Known Limitations",
            "",
            "- Naive RAG baseline only.",
            "- LLM outputs may be nondeterministic unless the provider enforces determinism.",
            "- No semantic claim-level human faithfulness review is performed in this run.",
            "- `held_out_test` excludes high-risk sanction/criminal QA.",
            "- Qualified human legal review has not occurred.",
            "",
        ]
    )
    return "\n".join(lines)


def _metric_line(label: str, metrics: dict[str, Any]) -> str:
    return (
        f"- `{label}`: queries={metrics.get('query_count', 0)}, "
        f"decision_accuracy={metrics.get('decision_accuracy', 0.0):.3f}, "
        f"answer_rate={metrics.get('answer_allowed_answer_rate', 0.0):.3f}, "
        f"fallback_rate={metrics.get('fallback_required_fallback_rate', 0.0):.3f}, "
        f"citation_validity={metrics.get('citation_id_validity_rate', 0.0):.3f}, "
        f"group_coverage={metrics.get('selected_evidence_group_coverage', 0.0):.3f}"
    )


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL atomically."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def assert_no_secret_artifacts(output_dir: Path) -> None:
    """Reject artifacts containing obvious secret-like strings."""
    for path in output_dir.glob("*"):
        if path.is_file() and find_secret_leak_labels(path.read_text(encoding="utf-8")):
            raise ValueError(f"refusing artifact with secret-like content: {path}")


def _judgments_by_query(records: list[EvidenceJudgment]) -> dict[str, list[EvidenceJudgment]]:
    grouped: dict[str, list[EvidenceJudgment]] = defaultdict(list)
    for record in records:
        grouped[record.query_id].append(record)
    return grouped


def _groups_by_query(records: list[EvidenceGroup]) -> dict[str, list[EvidenceGroup]]:
    grouped: dict[str, list[EvidenceGroup]] = defaultdict(list)
    for record in records:
        grouped[record.query_id].append(record)
    return grouped


def _targets_by_query(dataset: LoadedBenchmarkDataset) -> dict[str, list[ExpectedTarget]]:
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


def git_commit() -> str | None:
    """Return current Git commit hash when available."""
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


if __name__ == "__main__":
    raise SystemExit(main())
