#!/usr/bin/env python3
"""Run read-only Phase 8 Qdrant index validation and retrieval sanity checks."""

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

from src.indexing.embedding_model import BgeM3EmbeddingModel, EmbeddingModelError
from src.indexing.index_validation import IndexValidationError, validate_index
from src.indexing.indexing_models import (
    IndexingConfig,
    IndexValidationReport,
    PayloadFilterCheck,
    RetrievalSanityQuery,
)
from src.indexing.qdrant_collection import QdrantCollectionError, build_qdrant_client

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
DEFAULT_OUTPUT = Path("/tmp/vnlaw_phase8_8h_index_validation_report.json")
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
    """Build the read-only index-validation command parser."""
    parser = argparse.ArgumentParser(
        prog="scripts/validate_qdrant_index.py",
        description="Validate Qdrant schema, sampled points, filters, and dense search.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/indexing/embedding_indexing.yml"),
        help="Phase 8 indexing configuration.",
    )
    parser.add_argument("--collection-name", default=None, help="Existing collection to inspect.")
    parser.add_argument("--url", default=None, help="Override the configured Qdrant URL.")
    parser.add_argument("--dense-vector-name", default=None, help="Named dense vector to validate.")
    parser.add_argument(
        "--dense-dimension",
        type=int,
        default=None,
        help="Expected dense dimension measured during the embedding pilot.",
    )
    parser.add_argument(
        "--expected-distance",
        default=None,
        help="Expected dense-vector distance metric.",
    )
    parser.add_argument(
        "--expected-min-points",
        type=int,
        default=1,
        help="Conservative minimum expected collection point count.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Maximum number of points sampled for payload/vector validation.",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Dense results per sanity query.")
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="cpu",
        help="Device used only for retrieval sanity query embedding.",
    )
    parser.add_argument(
        "--skip-retrieval-sanity",
        action="store_true",
        help="Skip BGE-M3 loading and dense query searches.",
    )
    parser.add_argument(
        "--skip-vector-check",
        action="store_true",
        help="Sample payloads without requesting stored vectors.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON validation report path.",
    )
    parser.add_argument(
        "--report-type",
        choices=["index_validation_report"],
        default="index_validation_report",
        help="Operational report contract identifier.",
    )
    parser.add_argument(
        "--run-type",
        default="development_index_validation",
        help="Operational run classification.",
    )
    parser.add_argument(
        "--pipeline-stage",
        choices=["index_validation"],
        default="index_validation",
        help="Operational pipeline stage.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress completion summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the asynchronous read-only validation command."""
    return asyncio.run(run_validation(argv))


async def run_validation(argv: list[str] | None = None) -> int:
    """Load configuration, validate an existing index, and write a JSON report."""
    args = build_arg_parser().parse_args(argv)
    client: Any | None = None
    try:
        validate_cli_arguments(
            output_path=args.output,
            dense_dimension=args.dense_dimension,
            expected_min_points=args.expected_min_points,
            sample_limit=args.sample_limit,
            top_k=args.top_k,
        )
        config = load_indexing_config(args.config)
        collection_name = args.collection_name or config.qdrant.collection_name
        dense_vector_name = args.dense_vector_name or config.embedding.dense_vector_name
        dense_dimension = (
            args.dense_dimension or config.embedding.dense_dimension or MEASURED_BGE_M3_DIMENSION
        )
        expected_distance = args.expected_distance or config.qdrant.distance
        validate_cli_arguments(
            output_path=args.output,
            dense_dimension=dense_dimension,
            expected_min_points=args.expected_min_points,
            sample_limit=args.sample_limit,
            top_k=args.top_k,
        )

        client = build_qdrant_client(
            url=args.url or config.qdrant.url,
            timeout_seconds=config.qdrant.timeout_seconds,
        )
        embedding_model = None
        if not args.skip_retrieval_sanity:
            embedding_model = BgeM3EmbeddingModel(
                model_name=config.embedding.model_name,
                model_revision=config.embedding.model_revision,
                device=args.device,
                normalize_embeddings=config.embedding.normalize_embeddings,
                max_length=config.embedding.max_length,
                dense_vector_name=dense_vector_name,
            )

        report = await validate_index(
            client,
            report_type=args.report_type,
            run_type=args.run_type,
            pipeline_stage=args.pipeline_stage,
            collection_name=collection_name,
            dense_vector_name=dense_vector_name,
            dense_dimension=dense_dimension,
            expected_distance=expected_distance,
            expected_min_points=args.expected_min_points,
            sample_limit=args.sample_limit,
            filters=default_filter_checks(),
            queries=default_retrieval_queries(),
            top_k=args.top_k,
            check_vectors=not args.skip_vector_check,
            embedding_model=embedding_model,
        )
        write_report(args.output, report)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        EmbeddingModelError,
        IndexValidationError,
        QdrantCollectionError,
    ) as exc:
        print(f"Qdrant index validation failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        if client is not None:
            await client.close()

    if not args.quiet:
        print(f"Validation status: {report.status}")
        print(f"Collection schema: {report.collection_schema_status}")
        print(f"Points count: {report.points_count}")
        print(f"Sampled points: {report.sampled_point_count}")
        print(f"Payload validation: {report.payload_validation_status}")
        print(f"Vector validation: {report.vector_validation_status}")
        print(f"Filter validation: {report.filter_validation_status}")
        print(f"Retrieval sanity: {report.retrieval_sanity_status}")
        print(f"Report: {args.output}")
    return EXIT_SUCCESS if report.status in {"success", "warning"} else EXIT_FAILURE


def default_filter_checks() -> list[PayloadFilterCheck]:
    """Return deterministic read-only filters for the current dev index."""
    return [
        PayloadFilterCheck(
            name="law_id_blds_2015",
            field_name="law_id",
            match_value="BLDS_2015",
        ),
        PayloadFilterCheck(
            name="chunk_kind_clause_level",
            field_name="chunk_kind",
            match_value="clause_level",
        ),
        PayloadFilterCheck(
            name="level_clause",
            field_name="level",
            match_value="clause",
        ),
        PayloadFilterCheck(
            name="not_empty_or_repealed",
            field_name="metadata.is_empty_or_repealed",
            match_value=False,
        ),
        PayloadFilterCheck(
            name="source_unit_not_repealed",
            field_name="metadata.is_source_unit_repealed",
            match_value=False,
        ),
    ]


def default_retrieval_queries() -> list[RetrievalSanityQuery]:
    """Return bounded Vietnamese legal queries for the current dev collection."""
    return [
        RetrievalSanityQuery(
            query_text="Phạm vi điều chỉnh của Bộ luật Dân sự là gì?",
            expected_hint_terms=["Điều 1", "Phạm vi điều chỉnh"],
        ),
        RetrievalSanityQuery(
            query_text="Quyền dân sự được công nhận và bảo vệ như thế nào?",
            expected_hint_terms=["Điều 2", "quyền dân sự"],
        ),
        RetrievalSanityQuery(
            query_text="Quyền dân sự có thể bị hạn chế trong trường hợp nào?",
            expected_hint_terms=["khoản 2 Điều 2", "hạn chế"],
        ),
    ]


def load_indexing_config(path: Path) -> IndexingConfig:
    """Load and validate the Phase 8 YAML configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("indexing config root must be a YAML object")
    return IndexingConfig.model_validate(payload)


def validate_cli_arguments(
    *,
    output_path: Path,
    dense_dimension: int | None,
    expected_min_points: int,
    sample_limit: int,
    top_k: int,
) -> None:
    """Enforce protected-output and bounded validation settings."""
    if is_protected_output(output_path):
        raise ValueError(f"refusing protected report path {output_path}; use /tmp")
    if dense_dimension is not None and dense_dimension <= 0:
        raise ValueError("dense dimension must be positive")
    if expected_min_points < 0:
        raise ValueError("expected minimum points must be non-negative")
    if sample_limit <= 0:
        raise ValueError("sample limit must be positive")
    if top_k <= 0:
        raise ValueError("top-k must be positive")


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


def write_report(path: Path, report: IndexValidationReport) -> None:
    """Write the validation report atomically as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
