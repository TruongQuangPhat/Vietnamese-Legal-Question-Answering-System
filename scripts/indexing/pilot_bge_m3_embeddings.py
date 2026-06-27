#!/usr/bin/env python3
"""Run a constrained, non-indexing BGE-M3 dense embedding pilot."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.indexing.chunk_loader import ChunkLoaderError, iter_embedding_inputs
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.indexing_models import (
    DenseEmbedding,
    EmbeddingInput,
    EmbeddingTextTemplate,
    IndexingConfig,
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT = Path("/tmp/bge_m3_embedding_pilot_report.json")
DEFAULT_LIMIT = 100
MAX_SAFE_LIMIT = 1000
PROTECTED_PATHS = (
    REPO_ROOT / "data/raw",
    REPO_ROOT / "data/interim",
    REPO_ROOT / "data/reports",
    REPO_ROOT / "data/processed",
    REPO_ROOT / "artifacts/reports",
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the constrained BGE-M3 pilot argument parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/indexing/pilot_bge_m3_embeddings.py",
        description="Measure BGE-M3 dense embeddings without indexing or Qdrant.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/legal_chunks.jsonl"),
        help="Validated LegalChunk JSONL input.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/indexing/embedding_indexing.yml"),
        help="embedding/indexing configuration.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Pilot JSON report destination.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum pilot samples.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Embedding batch size; defaults to embedding.batch_size from config.",
    )
    parser.add_argument(
        "--template",
        choices=[template.value for template in EmbeddingTextTemplate],
        default=None,
        help="Embedding text template; defaults to config.",
    )
    parser.add_argument("--law-id", default=None, help="Optional exact law_id filter.")
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default=None,
        help="Requested model device; defaults to config.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress completion summary.")
    parser.add_argument(
        "--allow-protected-output",
        action="store_true",
        help="Allow writing under protected corpus/report paths.",
    )
    parser.add_argument(
        "--allow-large-pilot",
        action="store_true",
        help=f"Allow a pilot limit above {MAX_SAFE_LIMIT}.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the constrained embedding pilot and write a JSON report."""
    args = build_arg_parser().parse_args(argv)
    started = time.perf_counter()
    config: IndexingConfig | None = None
    inputs: list[EmbeddingInput] = []
    report: dict[str, Any] | None = None

    try:
        validate_pilot_arguments(
            output_path=args.output,
            limit=args.limit,
            batch_size=args.batch_size,
            allow_protected_output=args.allow_protected_output,
            allow_large_pilot=args.allow_large_pilot,
        )
        config = load_indexing_config(args.config)
        batch_size = args.batch_size or config.embedding.batch_size
        validate_pilot_arguments(
            output_path=args.output,
            limit=args.limit,
            batch_size=batch_size,
            allow_protected_output=args.allow_protected_output,
            allow_large_pilot=args.allow_large_pilot,
        )
        template = args.template or config.embedding.text_template.value
        device = args.device or config.embedding.device
        inputs = list(
            iter_embedding_inputs(
                args.input,
                text_template=template,
                law_id=args.law_id,
                limit=args.limit,
            )
        )
        if not inputs:
            raise ValueError("pilot sample is empty after applying filters")

        model = BgeM3EmbeddingModel(
            model_name=config.embedding.model_name,
            model_revision=config.embedding.model_revision,
            device=device,
            normalize_embeddings=config.embedding.normalize_embeddings,
            max_length=config.embedding.max_length,
            dense_vector_name=config.embedding.dense_vector_name,
        )
        embeddings = model.embed_dense(inputs, batch_size=batch_size)
        stability = check_batch_size_stability(
            model,
            inputs,
            embeddings,
            primary_batch_size=batch_size,
        )
        runtime_seconds = time.perf_counter() - started
        report = build_success_report(
            args=args,
            config=config,
            inputs=inputs,
            embeddings=embeddings,
            device_effective=model.device_effective,
            batch_size=batch_size,
            template=template,
            runtime_seconds=runtime_seconds,
            stability=stability,
        )
        write_report(args.output, report)
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        ChunkLoaderError,
        EmbeddingModelError,
    ) as exc:
        runtime_seconds = time.perf_counter() - started
        report = build_failure_report(
            args=args,
            config=config,
            inputs=inputs,
            reason=str(exc),
            runtime_seconds=runtime_seconds,
        )
        try:
            if args.allow_protected_output or not is_protected_output(args.output):
                write_report(args.output, report)
        except OSError as write_exc:
            print(f"Pilot report write failed: {write_exc}", file=sys.stderr)
        print(f"BGE-M3 embedding pilot failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    if not args.quiet:
        print("BGE-M3 embedding pilot complete")
        print(f"Samples: {report['actual_sample_count']}")
        print(f"Dense dimension: {report['dense_dimension']}")
        print(f"Device: {report['device_effective']}")
        print(f"Runtime seconds: {report['runtime_seconds']:.6f}")
        print(f"Throughput: {report['throughput_chunks_per_second']:.3f} chunks/s")
        print(f"Report: {args.output}")
    return EXIT_SUCCESS


def load_indexing_config(path: Path) -> IndexingConfig:
    """Load and validate embedding/indexing YAML configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("indexing config root must be a YAML object")
    return IndexingConfig.model_validate(payload)


def validate_pilot_arguments(
    *,
    output_path: Path,
    limit: int,
    batch_size: int | None,
    allow_protected_output: bool,
    allow_large_pilot: bool,
) -> None:
    """Validate pilot bounds and protected-output policy."""
    if limit <= 0:
        raise ValueError("pilot limit must be positive")
    if limit > MAX_SAFE_LIMIT and not allow_large_pilot:
        raise ValueError(
            f"pilot limit {limit} exceeds safe maximum {MAX_SAFE_LIMIT}; "
            "pass --allow-large-pilot to override"
        )
    if batch_size is not None and batch_size <= 0:
        raise ValueError("batch size must be positive")
    if is_protected_output(output_path) and not allow_protected_output:
        raise ValueError(
            f"refusing protected pilot output path {output_path}; "
            "use /tmp or pass --allow-protected-output"
        )


def is_protected_output(path: Path) -> bool:
    """Return whether a report path is inside a protected repository path."""
    resolved = path.expanduser().resolve()
    return any(
        resolved == protected or protected in resolved.parents for protected in PROTECTED_PATHS
    )


def check_batch_size_stability(
    model: BgeM3EmbeddingModel,
    inputs: list[EmbeddingInput],
    primary_embeddings: list[DenseEmbedding],
    *,
    primary_batch_size: int,
) -> dict[str, Any]:
    """Compare a small prefix using batch size one against primary outputs."""
    comparison_count = min(4, len(inputs))
    comparison_batch_size = 1 if primary_batch_size != 1 else 2
    comparison = model.embed_dense(inputs[:comparison_count], batch_size=comparison_batch_size)
    primary = primary_embeddings[:comparison_count]
    max_absolute_difference = max(
        (
            abs(left - right)
            for baseline, candidate in zip(primary, comparison, strict=True)
            for left, right in zip(baseline.values, candidate.values, strict=True)
        ),
        default=0.0,
    )
    dimensions_stable = all(
        baseline.dimension == candidate.dimension
        for baseline, candidate in zip(primary, comparison, strict=True)
    )
    return {
        "batch_size_stability_checked": True,
        "batch_size_stable": dimensions_stable and max_absolute_difference <= 1e-5,
        "primary_batch_size": primary_batch_size,
        "comparison_batch_size": comparison_batch_size,
        "comparison_sample_count": comparison_count,
        "max_absolute_difference": max_absolute_difference,
    }


def compute_vector_diagnostics(embeddings: list[DenseEmbedding]) -> dict[str, Any]:
    """Compute finite-value, dimension, and L2 norm diagnostics."""
    dimensions = [embedding.dimension for embedding in embeddings]
    expected_dimension = dimensions[0] if dimensions else None
    norms = [
        math.sqrt(sum(value * value for value in embedding.values)) for embedding in embeddings
    ]
    nan_count = sum(
        1 for embedding in embeddings if any(math.isnan(value) for value in embedding.values)
    )
    inf_count = sum(
        1 for embedding in embeddings if any(math.isinf(value) for value in embedding.values)
    )
    empty_count = sum(1 for embedding in embeddings if not embedding.values)
    mismatch_count = sum(
        1
        for dimension in dimensions
        if expected_dimension is not None and dimension != expected_dimension
    )
    zero_or_near_zero = sum(1 for norm in norms if norm <= 1e-12)
    return {
        "dense_dimension": expected_dimension,
        "dimensions_observed": sorted(set(dimensions)),
        "vector_count": len(embeddings),
        "empty_vector_count": empty_count,
        "nan_vector_count": nan_count,
        "inf_vector_count": inf_count,
        "dimension_mismatch_count": mismatch_count,
        "zero_or_near_zero_norm_count": zero_or_near_zero,
        "norm_min": min(norms) if norms else None,
        "norm_max": max(norms) if norms else None,
        "norm_mean": statistics.fmean(norms) if norms else None,
        "norm_p50": _percentile(norms, 0.50),
        "norm_p95": _percentile(norms, 0.95),
    }


def build_success_report(
    *,
    args: argparse.Namespace,
    config: IndexingConfig,
    inputs: list[EmbeddingInput],
    embeddings: list[DenseEmbedding],
    device_effective: str | None,
    batch_size: int,
    template: str,
    runtime_seconds: float,
    stability: dict[str, Any],
) -> dict[str, Any]:
    """Build a successful pilot report without storing vector values."""
    diagnostics = compute_vector_diagnostics(embeddings)
    return {
        "schema_version": "0.1.0",
        "report_type": "embedding_pilot_report",
        "workflow_name": "embedding_pilot",
        "status": "success",
        "input_path": str(args.input),
        "limit": args.limit,
        "actual_sample_count": len(inputs),
        "text_template": template,
        "law_id_filter": args.law_id,
        "model_name": config.embedding.model_name,
        "model_revision": config.embedding.model_revision,
        "device_requested": args.device or config.embedding.device,
        "device_effective": device_effective,
        "batch_size": batch_size,
        "dense_vector_name": config.embedding.dense_vector_name,
        **diagnostics,
        "runtime_seconds": runtime_seconds,
        "throughput_chunks_per_second": (
            len(inputs) / runtime_seconds if runtime_seconds > 0 else None
        ),
        "failed_chunk_ids": [],
        "issues": [],
        "sample_chunk_ids": [item.chunk_id for item in inputs[:10]],
        **stability,
    }


def build_failure_report(
    *,
    args: argparse.Namespace,
    config: IndexingConfig | None,
    inputs: list[EmbeddingInput],
    reason: str,
    runtime_seconds: float,
) -> dict[str, Any]:
    """Build a failure report with no claim that vectors were produced."""
    embedding = config.embedding if config is not None else None
    return {
        "schema_version": "0.1.0",
        "report_type": "embedding_pilot_report",
        "workflow_name": "embedding_pilot",
        "status": "failed",
        "input_path": str(args.input),
        "limit": args.limit,
        "actual_sample_count": len(inputs),
        "text_template": args.template or (embedding.text_template.value if embedding else None),
        "law_id_filter": args.law_id,
        "model_name": embedding.model_name if embedding else None,
        "model_revision": embedding.model_revision if embedding else None,
        "device_requested": args.device or (embedding.device if embedding else None),
        "device_effective": None,
        "batch_size": args.batch_size or (embedding.batch_size if embedding else None),
        "dense_vector_name": embedding.dense_vector_name if embedding else None,
        "dense_dimension": None,
        "dimensions_observed": [],
        "vector_count": 0,
        "empty_vector_count": 0,
        "nan_vector_count": 0,
        "inf_vector_count": 0,
        "dimension_mismatch_count": 0,
        "zero_or_near_zero_norm_count": 0,
        "norm_min": None,
        "norm_max": None,
        "norm_mean": None,
        "norm_p50": None,
        "norm_p95": None,
        "runtime_seconds": runtime_seconds,
        "throughput_chunks_per_second": None,
        "failed_chunk_ids": [item.chunk_id for item in inputs],
        "issues": [{"code": "PILOT_FAILED", "severity": "error", "message": reason}],
        "sample_chunk_ids": [item.chunk_id for item in inputs[:10]],
        "batch_size_stability_checked": False,
        "batch_size_stable": None,
        "primary_batch_size": args.batch_size or (embedding.batch_size if embedding else None),
        "comparison_batch_size": 1,
        "comparison_sample_count": 0,
        "max_absolute_difference": None,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Write a UTF-8 JSON pilot report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(report, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )


def _percentile(values: list[float], quantile: float) -> float | None:
    """Return a linearly interpolated percentile for a non-empty list."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


if __name__ == "__main__":
    raise SystemExit(main())
