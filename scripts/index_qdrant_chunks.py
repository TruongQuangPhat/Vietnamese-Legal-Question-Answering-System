#!/usr/bin/env python3
"""Run a bounded Phase 8 dense-vector indexing job."""

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

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.indexing.chunk_loader import ChunkLoaderError, iter_legal_chunks
from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.indexing_models import EmbeddingTextTemplate, IndexingConfig, IndexingReport
from src.indexing.indexing_service import IndexingService, IndexingServiceError
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT = Path("/tmp/vnlaw_phase8_8f_indexing_report.json")
DEFAULT_DRY_RUN_LIMIT = 100
MEASURED_BGE_M3_DIMENSION = 1024
PROTECTED_PATHS = (
    REPO_ROOT / "data/raw",
    REPO_ROOT / "data/interim",
    REPO_ROOT / "data/reports",
    REPO_ROOT / "data/processed",
    REPO_ROOT / "artifacts/reports",
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the bounded indexing command parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/index_qdrant_chunks.py",
        description="Embed and upsert a bounded LegalChunk sample into an existing collection.",
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
        help="Phase 8 indexing configuration.",
    )
    parser.add_argument("--collection-name", default=None, help="Target existing collection.")
    parser.add_argument("--url", default=None, help="Override the configured Qdrant URL.")
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
        help="Prepare inputs, payloads, and point IDs without embedding or upsert.",
    )
    parser.add_argument(
        "--allow-full-corpus",
        action="store_true",
        help="Allow a real run without --limit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Experimental JSON report path.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Optional checkpoint JSON path written after successful batches.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress completion summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous bounded indexing command."""
    return asyncio.run(run_indexing(argv))


async def run_indexing(argv: list[str] | None = None) -> int:
    """Load configuration, execute indexing, and write an experimental report."""
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
        )
        config = load_indexing_config(args.config)
        limit = args.limit
        if args.dry_run and limit is None:
            limit = DEFAULT_DRY_RUN_LIMIT
        batch_size = args.batch_size or config.embedding.batch_size
        validate_cli_arguments(
            output_path=args.output,
            checkpoint_path=args.checkpoint,
            limit=limit,
            batch_size=batch_size,
            dry_run=args.dry_run,
            allow_full_corpus=args.allow_full_corpus,
        )

        embedding_model = None
        if not args.dry_run:
            embedding_model = BgeM3EmbeddingModel(
                model_name=config.embedding.model_name,
                model_revision=config.embedding.model_revision,
                device=args.device or config.embedding.device,
                normalize_embeddings=config.embedding.normalize_embeddings,
                max_length=config.embedding.max_length,
                dense_vector_name=config.embedding.dense_vector_name,
            )
            client = build_qdrant_client(
                url=args.url or config.qdrant.url,
                timeout_seconds=config.qdrant.timeout_seconds,
            )

        service = IndexingService(
            qdrant_client=client,
            embedding_model=embedding_model,
            collection_name=args.collection_name or config.qdrant.collection_name,
            point_id_namespace=config.qdrant.point_id_namespace,
            dense_vector_name=config.embedding.dense_vector_name,
            dense_dimension=config.embedding.dense_dimension or MEASURED_BGE_M3_DIMENSION,
            batch_size=batch_size,
            payload_schema_version=config.payload.schema_version,
            model_name=config.embedding.model_name,
            model_revision=config.embedding.model_revision,
        )
        report = await service.index_chunks(
            iter_legal_chunks(args.input),
            input_path=str(args.input),
            text_template=args.text_template or config.embedding.text_template,
            law_id=args.law_id,
            limit=limit,
            dry_run=args.dry_run,
            checkpoint_path=args.checkpoint,
            phase7_gate_status="not_run",
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
        IndexingServiceError,
        QdrantCollectionError,
    ) as exc:
        print(f"Qdrant chunk indexing failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        print(f"Indexing status: {report.status}")
        print(f"Planned chunks: {report.planned_count}")
        print(f"Embedded chunks: {report.embedded_count}")
        print(f"Upserted chunks: {report.upserted_count}")
        print(f"Failed chunks: {report.failed_count}")
        print(f"Report: {args.output}")
        if args.checkpoint is not None and not args.dry_run:
            print(f"Checkpoint: {args.checkpoint}")
    return EXIT_SUCCESS if report.status in {"success", "dry_run"} else EXIT_FAILURE


def load_indexing_config(path: Path) -> IndexingConfig:
    """Load and validate the Phase 8 YAML configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("indexing config root must be a YAML object")
    return IndexingConfig.model_validate(payload)


def validate_cli_arguments(
    *,
    output_path: Path,
    checkpoint_path: Path | None,
    limit: int | None,
    batch_size: int | None,
    dry_run: bool,
    allow_full_corpus: bool,
) -> None:
    """Enforce bounded execution and protected-output policy."""
    if is_protected_output(output_path):
        raise ValueError(f"refusing protected report path {output_path}; use /tmp")
    if checkpoint_path is not None and is_protected_output(checkpoint_path):
        raise ValueError(f"refusing protected checkpoint path {checkpoint_path}; use /tmp")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if batch_size is not None and batch_size <= 0:
        raise ValueError("batch size must be positive")
    if not dry_run and limit is None and not allow_full_corpus:
        raise ValueError(
            "real indexing requires --limit; pass --allow-full-corpus only for an "
            "explicit operational full-corpus run"
        )


def is_protected_output(path: Path) -> bool:
    """Return whether a path is inside a protected repository tree."""
    resolved = path.expanduser().resolve()
    return any(
        resolved == protected or protected in resolved.parents for protected in PROTECTED_PATHS
    )


def write_report(path: Path, report: IndexingReport) -> None:
    """Write an indexing report atomically as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
