"""Deterministic fingerprinting and freeze-manifest support."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.evaluation.benchmark.exceptions import BenchmarkFreezeError, BenchmarkLoadError
from src.evaluation.benchmark.loader import (
    BenchmarkFileSet,
    load_benchmark_dataset,
    load_benchmark_manifest,
    load_split_manifest,
)
from src.evaluation.benchmark.schemas import BenchmarkConfig, BenchmarkManifest, ReviewStatus
from src.evaluation.benchmark.validator import BenchmarkValidator
from src.indexing.official_artifacts import write_json_atomic

INVALID_FREEZE_VERSIONS = {"draft", "dev", "development", "placeholder", "tbd", "todo"}
_MANIFEST_HASH_PLACEHOLDER = "0" * 64


def sha256_file(path: Path | str) -> str:
    """Return the SHA-256 digest of a file's raw bytes.

    Args:
        path: File path to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible data with deterministic ordering."""
    normalized = _to_json_compatible(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_canonical_data(value: Any) -> str:
    """Return the SHA-256 digest for canonical JSON-compatible data.

    Record order affects this hash when the provided value is a list.
    """
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_ordered_records(records: list[BaseModel]) -> str:
    """Hash an ordered JSONL-style model collection.

    The order of records is intentionally part of the fingerprint.
    """
    return sha256_canonical_data([record.model_dump(mode="json") for record in records])


def sha256_records_by_stable_id(
    records: list[BaseModel],
    id_getter: Callable[[BaseModel], str],
) -> str:
    """Hash records after sorting by stable record ID.

    JSON object key order and JSONL line order do not affect this semantic
    fingerprint. Record content, including Vietnamese Unicode text, is
    preserved exactly by canonical UTF-8 serialization.
    """
    sorted_records = sorted(records, key=id_getter)
    return sha256_canonical_data([record.model_dump(mode="json") for record in sorted_records])


def sha256_split_manifest(manifest: BaseModel) -> str:
    """Hash a split manifest using canonical model data."""
    return sha256_canonical_data(manifest.model_dump(mode="json"))


def sha256_benchmark_manifest(manifest: BenchmarkManifest) -> str:
    """Hash a manifest while excluding its own stored manifest fingerprint."""
    return sha256_canonical_data(
        manifest.model_copy(
            update={"manifest_canonical_content_sha256": _MANIFEST_HASH_PLACEHOLDER}
        )
    )


def create_benchmark_manifest(
    *,
    file_set: BenchmarkFileSet,
    config: BenchmarkConfig,
    split_manifest_path: Path,
    corpus_registry_path: Path,
    processed_chunks_path: Path,
    output_path: Path,
    change_log: list[str],
) -> BenchmarkManifest:
    """Validate benchmark files and write a frozen manifest.

    Args:
        file_set: Canonical benchmark JSONL file paths.
        config: Benchmark configuration.
        split_manifest_path: Existing split manifest path.
        corpus_registry_path: Read-only corpus registry path.
        processed_chunks_path: Read-only processed chunks JSONL path.
        output_path: Destination manifest path.
        change_log: Durable freeze change log entries.

    Returns:
        Written benchmark manifest.

    Raises:
        BenchmarkFreezeError: If validation errors or incomplete freeze
            requirements are found.

    Legal assumptions:
        This function verifies corpus and chunk checksums but never mutates
        corpus files, Qdrant collections, or regression assets.
    """
    if output_path.exists():
        raise BenchmarkFreezeError(f"refusing to overwrite existing manifest: {output_path}")
    if config.benchmark_version.strip().casefold() in INVALID_FREEZE_VERSIONS:
        raise BenchmarkFreezeError(
            "refusing freeze because benchmark_version must be a release version, "
            f"not {config.benchmark_version!r}"
        )

    try:
        dataset = load_benchmark_dataset(file_set)
        split_manifest = load_split_manifest(split_manifest_path)
    except BenchmarkLoadError as exc:
        raise BenchmarkFreezeError(f"refusing freeze because input loading failed: {exc}") from exc
    validator = BenchmarkValidator(config=config)
    report = validator.validate(
        dataset,
        split_manifest=split_manifest,
        corpus_registry_path=corpus_registry_path,
        processed_chunks_path=processed_chunks_path,
    )
    if report.errors:
        raise BenchmarkFreezeError(
            f"refusing freeze because validation has {len(report.errors)} errors",
        )
    if any(query.review_status != ReviewStatus.FROZEN for query in dataset.queries):
        raise BenchmarkFreezeError("refusing freeze because not all queries are frozen")
    split_raw_checksum = sha256_file(split_manifest_path)
    split_canonical_checksum = sha256_split_manifest(split_manifest)

    raw_file_sha256 = {
        "queries": sha256_file(file_set.queries),
        "legal_targets": sha256_file(file_set.legal_targets),
        "evidence_judgments": sha256_file(file_set.evidence_judgments),
        "evidence_groups": sha256_file(file_set.evidence_groups),
        "review_records": sha256_file(file_set.review_records),
        "split_manifest": split_raw_checksum,
    }
    canonical_content_sha256 = {
        "queries": sha256_records_by_stable_id(dataset.queries, lambda record: record.id),
        "legal_targets": sha256_records_by_stable_id(
            dataset.legal_targets, lambda record: record.id
        ),
        "evidence_judgments": sha256_records_by_stable_id(
            dataset.evidence_judgments, lambda record: f"{record.query_id}:{record.chunk_id}"
        ),
        "evidence_groups": sha256_records_by_stable_id(
            dataset.evidence_groups, lambda record: f"{record.query_id}:{record.evidence_group_id}"
        ),
        "review_records": sha256_records_by_stable_id(
            dataset.review_records, lambda record: record.id
        ),
        "split_manifest": split_canonical_checksum,
    }

    manifest = BenchmarkManifest(
        schema_version=config.schema_version,
        benchmark_version=config.benchmark_version,
        freeze_date=datetime.now(UTC),
        record_counts={
            "queries": len(dataset.queries),
            "legal_targets": len(dataset.legal_targets),
            "evidence_judgments": len(dataset.evidence_judgments),
            "evidence_groups": len(dataset.evidence_groups),
            "review_records": len(dataset.review_records),
        },
        raw_file_sha256=raw_file_sha256,
        canonical_content_sha256=canonical_content_sha256,
        corpus_registry_raw_file_sha256=sha256_file(corpus_registry_path),
        processed_chunks_raw_file_sha256=sha256_file(processed_chunks_path),
        split_manifest_raw_file_sha256=split_raw_checksum,
        split_manifest_canonical_content_sha256=split_canonical_checksum,
        manifest_canonical_content_sha256=_MANIFEST_HASH_PLACEHOLDER,
        review_status=ReviewStatus.FROZEN,
        change_log=change_log,
    )
    manifest = manifest.model_copy(
        update={"manifest_canonical_content_sha256": sha256_benchmark_manifest(manifest)}
    )
    write_json_atomic(output_path, manifest.model_dump(mode="json"))
    reloaded = load_benchmark_manifest(output_path)
    if sha256_benchmark_manifest(reloaded) != manifest.manifest_canonical_content_sha256:
        raise BenchmarkFreezeError("post-write manifest verification failed")
    return manifest


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_json_compatible(child) for key, child in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json_compatible(child) for child in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
