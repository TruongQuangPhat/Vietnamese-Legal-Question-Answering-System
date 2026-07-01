#!/usr/bin/env python3
"""Set up only the embedding/indexing Qdrant collection schema."""

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

from src.indexing.indexing_models import IndexingConfig
from src.indexing.qdrant_collection import (
    QdrantCollectionError,
    build_collection_plan,
    build_qdrant_client,
    ensure_collection,
    resolve_qdrant_api_key,
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the collection-only setup argument parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/indexing/setup_qdrant_collection.py",
        description="Validate or create a Qdrant collection schema without indexing points.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/indexing/embedding_indexing.yml"),
        help="embedding/indexing configuration.",
    )
    parser.add_argument("--url", default=None, help="Override the configured Qdrant URL.")
    parser.add_argument(
        "--qdrant-api-key",
        default=None,
        help=(
            "Override QDRANT_API_KEY. Prefer the environment variable to avoid "
            "placing credentials in shell history."
        ),
    )
    parser.add_argument(
        "--collection-name",
        default=None,
        help="Override the configured collection name.",
    )
    parser.add_argument(
        "--dense-vector-name",
        default=None,
        help="Override the configured dense vector name.",
    )
    parser.add_argument(
        "--dense-dimension",
        type=int,
        default=None,
        help="Measured dense vector dimension; required when config remains null.",
    )
    parser.add_argument(
        "--distance",
        choices=["Cosine", "Dot", "Euclid", "Manhattan"],
        default=None,
        help="Override the configured dense distance.",
    )
    parser.add_argument(
        "--sparse-enabled",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the optional named sparse vector.",
    )
    parser.add_argument(
        "--sparse-vector-name",
        default=None,
        help="Override the configured sparse vector name.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Explicitly replace an existing collection only when its schema mismatches.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the validated schema plan without connecting to Qdrant.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the async collection setup command."""
    return asyncio.run(run_setup(argv))


async def run_setup(argv: list[str] | None = None) -> int:
    """Load configuration and validate or create the collection schema."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None

    try:
        config = load_indexing_config(args.config)
        dense_dimension = args.dense_dimension or config.embedding.dense_dimension
        if dense_dimension is None:
            raise QdrantCollectionError(
                "dense dimension is not configured; pass --dense-dimension using "
                "the measured model output (1024 for the validated BGE-M3 pilot)"
            )

        sparse_enabled = (
            config.sparse.enabled if args.sparse_enabled is None else args.sparse_enabled
        )
        plan = build_collection_plan(
            collection_name=args.collection_name or config.qdrant.collection_name,
            dense_vector_name=args.dense_vector_name or config.embedding.dense_vector_name,
            dense_dimension=dense_dimension,
            distance=args.distance or config.qdrant.distance,
            sparse_enabled=sparse_enabled,
            sparse_vector_name=args.sparse_vector_name or config.sparse.vector_name,
            recreate=args.recreate,
        )

        if args.dry_run:
            if not args.quiet:
                print(json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False))
            return EXIT_SUCCESS

        client = build_qdrant_client(
            url=args.url or config.qdrant.url,
            timeout_seconds=config.qdrant.timeout_seconds,
            api_key=resolve_qdrant_api_key(args.qdrant_api_key),
        )
        result = await ensure_collection(client, **plan.model_dump())
        if not args.quiet:
            print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return EXIT_SUCCESS
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        QdrantCollectionError,
    ) as exc:
        print(f"Qdrant collection setup failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()


def load_indexing_config(path: Path) -> IndexingConfig:
    """Load and validate the embedding/indexing YAML configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("indexing config root must be a YAML object")
    return IndexingConfig.model_validate(payload)


if __name__ == "__main__":
    raise SystemExit(main())
