"""Deterministic UTF-8 loaders for legal QA benchmark files."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from src.evaluation.benchmark.exceptions import BenchmarkLoadError
from src.evaluation.benchmark.schemas import (
    BenchmarkConfig,
    BenchmarkManifest,
    BenchmarkQuery,
    EvidenceGroup,
    EvidenceJudgment,
    LegalTarget,
    ReviewRecord,
    SplitManifest,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class BenchmarkFileSet(BaseModel):
    """Canonical file paths for a benchmark dataset."""

    queries: Path
    legal_targets: Path
    evidence_judgments: Path
    evidence_groups: Path
    review_records: Path


class LoadedBenchmarkDataset(BaseModel):
    """Typed benchmark records loaded from canonical JSONL files."""

    queries: list[BenchmarkQuery]
    legal_targets: list[LegalTarget]
    evidence_judgments: list[EvidenceJudgment]
    evidence_groups: list[EvidenceGroup]
    review_records: list[ReviewRecord]
    checked_files: list[str]


def load_benchmark_config(path: Path | str) -> BenchmarkConfig:
    """Load benchmark YAML configuration.

    Args:
        path: UTF-8 YAML config path.

    Returns:
        Typed benchmark configuration.

    Raises:
        BenchmarkLoadError: If YAML parsing or schema validation fails.
    """
    config_path = Path(path)
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BenchmarkLoadError(f"failed to read config {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise BenchmarkLoadError(f"invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkLoadError(f"config root must be a YAML object: {config_path}")
    return _validate_single_record(config_path, BenchmarkConfig, payload)


def load_benchmark_dataset(file_set: BenchmarkFileSet) -> LoadedBenchmarkDataset:
    """Load every canonical benchmark JSONL file into typed records."""
    return LoadedBenchmarkDataset(
        queries=load_benchmark_queries(file_set.queries),
        legal_targets=load_legal_targets(file_set.legal_targets),
        evidence_judgments=load_evidence_judgments(file_set.evidence_judgments),
        evidence_groups=load_evidence_groups(file_set.evidence_groups),
        review_records=load_review_records(file_set.review_records),
        checked_files=[
            str(file_set.queries),
            str(file_set.legal_targets),
            str(file_set.evidence_judgments),
            str(file_set.evidence_groups),
            str(file_set.review_records),
        ],
    )


def load_benchmark_queries(path: Path | str) -> list[BenchmarkQuery]:
    """Load benchmark query records from JSONL."""
    return load_jsonl_records(Path(path), BenchmarkQuery, lambda record: record.id)


def load_legal_targets(path: Path | str) -> list[LegalTarget]:
    """Load legal target records from JSONL."""
    return load_jsonl_records(Path(path), LegalTarget, lambda record: record.id)


def load_evidence_judgments(path: Path | str) -> list[EvidenceJudgment]:
    """Load chunk-level evidence judgment records from JSONL."""
    return load_jsonl_records(
        Path(path),
        EvidenceJudgment,
        lambda record: f"{record.query_id}:{record.chunk_id}",
    )


def load_evidence_groups(path: Path | str) -> list[EvidenceGroup]:
    """Load semantic evidence group records from JSONL."""
    return load_jsonl_records(
        Path(path),
        EvidenceGroup,
        lambda record: f"{record.query_id}:{record.evidence_group_id}",
    )


def load_review_records(path: Path | str) -> list[ReviewRecord]:
    """Load review provenance records from JSONL."""
    return load_jsonl_records(Path(path), ReviewRecord, lambda record: record.id)


def load_split_manifest(path: Path | str) -> SplitManifest:
    """Load a split manifest from JSON."""
    return load_json_record(Path(path), SplitManifest)


def load_benchmark_manifest(path: Path | str) -> BenchmarkManifest:
    """Load a frozen benchmark manifest from JSON."""
    return load_json_record(Path(path), BenchmarkManifest)


def load_jsonl_records(
    path: Path,
    model_type: type[ModelT],
    id_getter: Callable[[ModelT], str],
) -> list[ModelT]:
    """Load a UTF-8 JSONL file into Pydantic models.

    Args:
        path: JSONL path.
        model_type: Pydantic model class for each record.
        id_getter: Function returning the stable record identifier.

    Returns:
        Records in source order.

    Raises:
        BenchmarkLoadError: If JSON is malformed, validation fails, or a
            duplicate stable record ID is found.
    """
    records: list[ModelT] = []
    seen: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped, object_pairs_hook=_reject_duplicate_keys)
                except json.JSONDecodeError as exc:
                    raise BenchmarkLoadError(
                        f"invalid JSON at {path}:{line_number}: {exc.msg}",
                    ) from exc
                except ValueError as exc:
                    raise BenchmarkLoadError(
                        f"invalid JSON at {path}:{line_number}: {exc}",
                    ) from exc
                if not isinstance(payload, dict):
                    raise BenchmarkLoadError(
                        f"record must be a JSON object at {path}:{line_number}",
                    )
                record = _validate_line_record(path, line_number, model_type, payload)
                record_id = id_getter(record)
                if record_id in seen:
                    raise BenchmarkLoadError(
                        f"duplicate record ID {record_id!r} at {path}:{line_number}",
                    )
                seen.add(record_id)
                records.append(record)
    except OSError as exc:
        raise BenchmarkLoadError(f"failed to read JSONL file {path}: {exc}") from exc
    return records


def load_json_record(path: Path, model_type: type[ModelT]) -> ModelT:
    """Load a single UTF-8 JSON object into a Pydantic model."""
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except OSError as exc:
        raise BenchmarkLoadError(f"failed to read JSON file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkLoadError(f"invalid JSON at {path}: {exc.msg}") from exc
    except ValueError as exc:
        raise BenchmarkLoadError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkLoadError(f"JSON root must be an object: {path}")
    return _validate_single_record(path, model_type, payload)


def load_json_array(path: Path, model_type: type[ModelT]) -> Sequence[ModelT]:
    """Load a UTF-8 JSON array into typed records."""
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except OSError as exc:
        raise BenchmarkLoadError(f"failed to read JSON file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkLoadError(f"invalid JSON at {path}: {exc.msg}") from exc
    except ValueError as exc:
        raise BenchmarkLoadError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise BenchmarkLoadError(f"JSON root must be an array: {path}")
    records: list[ModelT] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise BenchmarkLoadError(f"array item must be an object at {path}:{index}")
        records.append(_validate_line_record(path, index, model_type, item))
    return records


def _validate_line_record(
    path: Path,
    line_number: int,
    model_type: type[ModelT],
    payload: dict[str, Any],
) -> ModelT:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise BenchmarkLoadError(f"invalid record at {path}:{line_number}: {exc}") from exc


def _validate_single_record(
    path: Path,
    model_type: type[ModelT],
    payload: dict[str, Any],
) -> ModelT:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise BenchmarkLoadError(f"invalid record at {path}: {exc}") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON object keys instead of keeping the last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result
