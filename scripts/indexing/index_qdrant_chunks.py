#!/usr/bin/env python3
"""Run a safely bounded and resumable indexing job."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.indexing.chunk_loader import ChunkLoaderError, iter_legal_chunks
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.indexing_models import (
    EmbeddingTextTemplate,
    IndexingConfig,
    IndexingReport,
    ProcessedValidationSummary,
)
from src.indexing.indexing_service import (
    IndexingService,
    IndexingServiceError,
    load_indexing_checkpoint,
)
from src.indexing.official_artifacts import (
    OfficialArtifactError,
    build_processed_corpus_validation_summary_from_path,
    write_json_atomic,
)
from src.indexing.qdrant_collection import (
    QdrantCollectionError,
    build_qdrant_client,
    resolve_qdrant_api_key,
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT = Path("/tmp/vnlaw_indexing_report.json")
DEFAULT_DRY_RUN_LIMIT = 100
MEASURED_BGE_M3_DIMENSION = 1024
PROTECTED_CORPUS_PATHS = (
    REPO_ROOT / "data/raw",
    REPO_ROOT / "data/interim",
    REPO_ROOT / "data/reports",
    REPO_ROOT / "data/processed",
)
REPORTS_ROOT = REPO_ROOT / "artifacts/reports"
OFFICIAL_INDEXING_REPORTS_ROOT = REPORTS_ROOT / "indexing"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the operational indexing command parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/indexing/index_qdrant_chunks.py",
        description="Run bounded or resumable dense indexing into an existing Qdrant collection.",
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
        help="indexing configuration.",
    )
    parser.add_argument("--collection-name", default=None, help="Target existing collection.")
    parser.add_argument("--url", default=None, help="Override the configured Qdrant URL.")
    parser.add_argument(
        "--qdrant-api-key",
        default=None,
        help=(
            "Override QDRANT_API_KEY. Prefer the environment variable to avoid "
            "placing credentials in shell history."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum matching chunks.")
    parser.add_argument("--law-id", default=None, help="Optional exact law_id filter.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Embedding and upsert batch size.",
    )
    parser.add_argument(
        "--text-template",
        choices=[template.value for template in EmbeddingTextTemplate],
        default=None,
        help="Deterministic embedding text template.",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default=None,
        help="Embedding device for a real run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare inputs, payloads, and point IDs without embedding or Qdrant access.",
    )
    parser.add_argument(
        "--allow-full-corpus",
        action="store_true",
        help="Allow a real run without --limit.",
    )
    parser.add_argument(
        "--processed-validation-report",
        type=Path,
        default=None,
        help="Processed JSONL validation report to enforce before indexing.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Optional compatible progress checkpoint path.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the explicitly supplied compatible checkpoint.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Maximum Qdrant upsert retries per failed batch.",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=2.0,
        help="Linear backoff base between Qdrant upsert retries.",
    )
    parser.add_argument(
        "--reconcile-counts",
        action="store_true",
        help="Read Qdrant collection counts before and after a real run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Experimental JSON report path.",
    )
    parser.add_argument(
        "--report-type",
        choices=["indexing_report"],
        default="indexing_report",
        help="Operational report contract identifier.",
    )
    parser.add_argument(
        "--run-type",
        default="development_indexing",
        help="Operational run classification.",
    )
    parser.add_argument(
        "--workflow-name",
        choices=["embedding_indexing"],
        default="embedding_indexing",
        help="Operational workflow name.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress completion summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous operational indexing command."""
    return asyncio.run(run_indexing(argv))


async def run_indexing(argv: list[str] | None = None) -> int:
    """Load validation/configuration, execute indexing, and write the report."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None

    try:
        validate_cli_arguments(
            output_path=args.output,
            checkpoint_path=args.checkpoint,
            limit=args.limit,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            allow_full_corpus=args.allow_full_corpus,
            resume=args.resume,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )
        config = load_indexing_config(args.config)
        limit = args.limit
        if args.dry_run and limit is None:
            limit = DEFAULT_DRY_RUN_LIMIT
        batch_size = args.batch_size or config.embedding.batch_size
        template = EmbeddingTextTemplate(args.text_template or config.embedding.text_template)
        device = args.device or config.embedding.device
        collection_name = args.collection_name or config.qdrant.collection_name
        dense_dimension = config.embedding.dense_dimension or MEASURED_BGE_M3_DIMENSION
        validate_cli_arguments(
            output_path=args.output,
            checkpoint_path=args.checkpoint,
            limit=limit,
            batch_size=batch_size,
            dry_run=args.dry_run,
            allow_full_corpus=args.allow_full_corpus,
            resume=args.resume,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )

        processed_validation = ProcessedValidationSummary()
        if args.processed_validation_report is not None:
            processed_validation = load_processed_validation_report(
                args.processed_validation_report,
                expected_input_path=args.input,
            )
            if args.run_type == "official_full_indexing":
                summary_path = args.output.parent / "processed_corpus_validation_summary.json"
                summary = build_processed_corpus_validation_summary_from_path(
                    args.processed_validation_report
                )
                write_json_atomic(summary_path, summary.model_dump(mode="json"))
                processed_validation = processed_validation.model_copy(
                    update={"report_path": str(summary_path)}
                )

        resume_checkpoint = None
        if args.resume:
            if args.checkpoint is None:
                raise ValueError("--resume requires --checkpoint")
            resume_checkpoint = load_indexing_checkpoint(args.checkpoint)

        embedding_model = None
        if not args.dry_run:
            embedding_model = BgeM3EmbeddingModel(
                model_name=config.embedding.model_name,
                model_revision=config.embedding.model_revision,
                device=device,
                normalize_embeddings=config.embedding.normalize_embeddings,
                max_length=config.embedding.max_length,
                dense_vector_name=config.embedding.dense_vector_name,
            )
            client = build_qdrant_client(
                url=args.url or config.qdrant.url,
                timeout_seconds=config.qdrant.timeout_seconds,
                api_key=resolve_qdrant_api_key(args.qdrant_api_key),
            )

        service = IndexingService(
            qdrant_client=client,
            embedding_model=embedding_model,
            collection_name=collection_name,
            point_id_namespace=config.qdrant.point_id_namespace,
            dense_vector_name=config.embedding.dense_vector_name,
            dense_dimension=dense_dimension,
            batch_size=batch_size,
            payload_schema_version=config.payload.schema_version,
            model_name=config.embedding.model_name,
            model_revision=config.embedding.model_revision,
        )
        report = await service.index_chunks(
            iter_legal_chunks(args.input),
            input_path=str(args.input),
            report_type=args.report_type,
            run_type=args.run_type,
            workflow_name=args.workflow_name,
            text_template=template,
            law_id=args.law_id,
            limit=limit,
            dry_run=args.dry_run,
            checkpoint_path=args.checkpoint,
            resume_checkpoint=resume_checkpoint,
            processed_validation=processed_validation,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
            reconcile_counts=args.reconcile_counts,
            device=device,
            allow_full_corpus=args.allow_full_corpus,
        )
        write_report(args.output, report)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        ChunkLoaderError,
        EmbeddingModelError,
        IndexingServiceError,
        OfficialArtifactError,
        QdrantCollectionError,
    ) as exc:
        print(f"Qdrant chunk indexing failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        print(f"Indexing status: {report.status}")
        print(f"Processed validation: {report.processed_validation_status}")
        print(f"Planned chunks: {report.planned_count}")
        print(f"Checkpoint-skipped chunks: {report.skipped_due_to_checkpoint_count}")
        print(f"Embedded chunks: {report.embedded_count}")
        print(f"Upserted chunks: {report.upserted_count}")
        print(f"Failed chunks: {report.failed_count}")
        print(f"Retry attempts: {report.retry_attempts_total}")
        print(f"Count reconciliation: {report.count_reconciliation_status}")
        print(f"Report: {args.output}")
        if args.checkpoint is not None and not args.dry_run:
            print(f"Checkpoint: {args.checkpoint}")
    return EXIT_SUCCESS if report.status in {"success", "dry_run"} else EXIT_FAILURE


def load_indexing_config(path: Path) -> IndexingConfig:
    """Load and validate the embedding/indexing YAML configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("indexing config root must be a YAML object")
    return IndexingConfig.model_validate(payload)


def load_processed_validation_report(
    path: Path,
    *,
    expected_input_path: Path,
) -> ProcessedValidationSummary:
    """Load and enforce processed JSONL readiness from its validation report."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"unable to read processed validation report {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"processed validation report {path} is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("processed validation report root must be a JSON object")

    embedding = payload.get("embedding_readiness")
    if not isinstance(embedding, dict):
        raise ValueError("processed validation report is missing embedding_readiness")

    report_input = payload.get("input_path")
    if not isinstance(report_input, str) or not report_input.strip():
        raise ValueError("processed validation report is missing input_path")
    if Path(report_input).resolve() != expected_input_path.resolve():
        raise ValueError(
            "processed validation report input_path does not match indexing input: "
            f"{report_input!r} != {str(expected_input_path)!r}"
        )

    status = payload.get("status")
    errors_total = payload.get("errors_total")
    invalid_chunks = payload.get("invalid_chunks")
    warnings_total = payload.get("warnings_total", embedding.get("warning_count", 0))
    embedding_ready = embedding.get("embedding_ready")
    payload_ready_rate = embedding.get("payload_ready_rate")
    if status not in {"pass", "pass_with_warnings"}:
        raise ValueError(
            f"processed validation status must be pass or pass_with_warnings, got {status!r}"
        )
    if not isinstance(errors_total, int) or errors_total > 0:
        raise ValueError(f"processed validation errors_total must be 0, got {errors_total!r}")
    if not isinstance(invalid_chunks, int) or invalid_chunks > 0:
        raise ValueError(f"processed validation invalid_chunks must be 0, got {invalid_chunks!r}")
    if embedding_ready is not True:
        raise ValueError("processed validation embedding_ready must be true")
    if payload_ready_rate != 1.0:
        raise ValueError(
            f"processed validation payload_ready_rate must be 1.0, got {payload_ready_rate!r}"
        )
    if not isinstance(warnings_total, int) or warnings_total < 0:
        raise ValueError("processed validation warnings_total must be non-negative")

    return ProcessedValidationSummary(
        status=status,
        report_path=str(path),
        input_path=report_input,
        errors_total=errors_total,
        invalid_chunks=invalid_chunks,
        warnings_total=warnings_total,
        embedding_ready=True,
        payload_ready_rate=payload_ready_rate,
    )


def validate_cli_arguments(
    *,
    output_path: Path,
    checkpoint_path: Path | None,
    limit: int | None,
    batch_size: int | None,
    dry_run: bool,
    allow_full_corpus: bool,
    resume: bool,
    max_retries: int,
    retry_backoff_seconds: float,
) -> None:
    """Enforce bounded execution, explicit resume, and protected-output policy."""
    if is_protected_output(output_path):
        raise ValueError(f"refusing protected report path {output_path}; use /tmp")
    if checkpoint_path is not None and is_protected_output(checkpoint_path):
        raise ValueError(f"refusing protected checkpoint path {checkpoint_path}; use /tmp")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if batch_size is not None and batch_size <= 0:
        raise ValueError("batch size must be positive")
    if max_retries < 0:
        raise ValueError("max retries must be greater than or equal to zero")
    if retry_backoff_seconds < 0:
        raise ValueError("retry backoff seconds must be greater than or equal to zero")
    if resume and checkpoint_path is None:
        raise ValueError("--resume requires --checkpoint")
    if resume and checkpoint_path is not None and not checkpoint_path.is_file():
        raise ValueError(f"resume checkpoint does not exist: {checkpoint_path}")
    if not dry_run and limit is None and not allow_full_corpus:
        raise ValueError(
            "real indexing requires --limit; pass --allow-full-corpus only for an "
            "explicit operational full-corpus run"
        )


def is_protected_output(path: Path) -> bool:
    """Return whether a path violates corpus or report artifact boundaries."""
    resolved = path.expanduser().resolve()
    if any(
        resolved == protected or protected in resolved.parents
        for protected in PROTECTED_CORPUS_PATHS
    ):
        return True
    if resolved == REPORTS_ROOT or REPORTS_ROOT in resolved.parents:
        return not is_allowed_official_indexing_artifact(resolved)
    return False


def is_allowed_official_indexing_artifact(path: Path) -> bool:
    """Allow one file directly below a named official indexing run directory."""
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(OFFICIAL_INDEXING_REPORTS_ROOT)
    except ValueError:
        return False
    return (
        len(relative.parts) == 2
        and relative.parts[0] not in {"", ".", ".."}
        and relative.parts[1] not in {"", ".", ".."}
    )


def write_report(path: Path, report: IndexingReport) -> None:
    """Write an indexing report atomically as UTF-8 JSON."""
    payload = report.model_dump(mode="json")
    write_json_atomic(path, payload)


if __name__ == "__main__":
    raise SystemExit(main())
