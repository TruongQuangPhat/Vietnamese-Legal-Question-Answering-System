"""Operational metadata helpers for official indexing artifact packages."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.indexing.indexing_models import ProcessedCorpusValidationSummary

FORBIDDEN_OFFICIAL_TERMINOLOGY = re.compile(r"(?i:phase|slice)|8F|8G|8H")
_WARNING_DISTRIBUTION_EXCLUDED_FIELDS = {"deferred_resolution", "examples"}


class OfficialArtifactError(ValueError):
    """Raised when an official artifact cannot be safely built or sanitized."""


def build_processed_corpus_validation_summary(
    raw_report: dict[str, Any],
) -> ProcessedCorpusValidationSummary:
    """Build a clean operational summary from a processed JSONL validation report.

    Args:
        raw_report: Parsed report produced by ``validate_processed_jsonl.py``.

    Returns:
        A typed summary containing only operational corpus-readiness facts.

    Raises:
        OfficialArtifactError: If required validation sections are missing.
    """
    embedding = _require_mapping(raw_report, "embedding_readiness")
    warning_categories = _require_mapping(embedding, "warning_categories")
    warning_distribution = _require_mapping(raw_report, "warning_distribution_summary")
    clean_warning_distribution = {
        key: deepcopy(value)
        for key, value in warning_distribution.items()
        if key not in _WARNING_DISTRIBUTION_EXCLUDED_FIELDS
    }
    summary = ProcessedCorpusValidationSummary(
        input_path=_require_string(raw_report, "input_path"),
        total_lines=_require_int(raw_report, "total_lines"),
        valid_chunks=_require_int(raw_report, "valid_chunks"),
        invalid_chunks=_require_int(raw_report, "invalid_chunks"),
        errors_total=_require_int(raw_report, "errors_total"),
        warnings_total=_require_int(raw_report, "warnings_total"),
        embedding_ready=_require_bool(embedding, "embedding_ready"),
        readiness_status=_require_string(embedding, "readiness_status"),
        payload_ready_rate=_require_number(embedding, "payload_ready_rate"),
        contamination_warnings=_require_int(warning_categories, "contamination_warnings"),
        short_text_warnings=_require_int(warning_categories, "short_text_warnings"),
        chunks_by_level=_require_int_mapping(raw_report, "chunks_by_level"),
        chunks_by_law=_require_int_mapping(raw_report, "chunks_by_law"),
        text_length_summary=deepcopy(_require_mapping(raw_report, "text_length_summary")),
        parent_text_length_summary=deepcopy(
            _require_mapping(raw_report, "parent_text_length_summary")
        ),
        repealed_metadata_summary=deepcopy(
            _require_mapping(raw_report, "repealed_metadata_summary")
        ),
        warning_distribution_summary=clean_warning_distribution,
        blocking_reasons=_require_string_list(embedding, "blocking_reasons"),
    )
    assert_clean_official_payload(summary.model_dump(mode="json"))
    return summary


def build_processed_corpus_validation_summary_from_path(
    path: Path,
) -> ProcessedCorpusValidationSummary:
    """Load a raw validation report and return its clean operational summary."""
    return build_processed_corpus_validation_summary(_read_json_object(path))


def sanitize_official_indexing_run(
    run_dir: Path,
    *,
    reports_root: Path,
) -> list[Path]:
    """Sanitize one official indexing run directory without touching Qdrant.

    The raw processed-JSONL report is replaced by a clean summary. Indexing
    reports are updated to reference that summary and lose deprecated
    readiness fields. Validation reports receive deterministic retrieval
    baseline readiness.

    Args:
        run_dir: Named official indexing run directory.
        reports_root: Root directory that directly contains named run folders.

    Returns:
        Paths written or removed while sanitizing the package.

    Raises:
        OfficialArtifactError: If paths are unsafe or forbidden terminology
            remains in any JSON artifact.
    """
    resolved_run_dir = run_dir.expanduser().resolve()
    resolved_reports_root = reports_root.expanduser().resolve()
    if resolved_run_dir.parent != resolved_reports_root:
        raise OfficialArtifactError(
            f"run directory must be directly below {resolved_reports_root}: {resolved_run_dir}"
        )
    if not resolved_run_dir.is_dir():
        raise OfficialArtifactError(f"official indexing run directory does not exist: {run_dir}")

    changed: list[Path] = []
    raw_path = resolved_run_dir / "processed_jsonl_validation_report.json"
    summary_path = resolved_run_dir / "processed_corpus_validation_summary.json"
    if raw_path.is_file():
        summary = build_processed_corpus_validation_summary_from_path(raw_path)
        write_json_atomic(summary_path, summary.model_dump(mode="json"))
        changed.append(summary_path)

    for path in sorted(resolved_run_dir.glob("*.json")):
        if path in {raw_path, summary_path}:
            continue
        payload = _read_json_object(path)
        report_type = payload.get("report_type")
        if report_type == "indexing_report":
            payload.pop("readiness_for_phase9", None)
            if summary_path.is_file():
                payload["processed_validation_report_path"] = _display_path(summary_path)
            write_json_atomic(path, payload)
            changed.append(path)
        elif report_type == "index_validation_report":
            payload["retrieval_baseline_ready"] = _retrieval_baseline_ready(payload)
            write_json_atomic(path, payload)
            changed.append(path)

    if raw_path.is_file():
        raw_path.unlink()
        changed.append(raw_path)

    for path in sorted(resolved_run_dir.glob("*.json")):
        assert_clean_official_payload(_read_json_object(path))
    return changed


def assert_clean_official_payload(payload: dict[str, Any]) -> None:
    """Reject any key or string value containing development terminology."""
    violation = _find_forbidden_term(payload)
    if violation is not None:
        raise OfficialArtifactError(f"forbidden official artifact terminology at {violation}")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON object atomically using UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _retrieval_baseline_ready(payload: dict[str, Any]) -> bool:
    return all(
        payload.get(field) == "pass"
        for field in (
            "collection_schema_status",
            "payload_validation_status",
            "vector_validation_status",
            "filter_validation_status",
            "retrieval_sanity_status",
        )
    )


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _find_forbidden_term(value: Any, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{path}.{key}"
            if FORBIDDEN_OFFICIAL_TERMINOLOGY.search(str(key)):
                return key_path
            violation = _find_forbidden_term(item, key_path)
            if violation is not None:
                return violation
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violation = _find_forbidden_term(item, f"{path}[{index}]")
            if violation is not None:
                return violation
    elif isinstance(value, str) and FORBIDDEN_OFFICIAL_TERMINOLOGY.search(value):
        return path
    return None


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OfficialArtifactError(f"unable to read JSON artifact {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OfficialArtifactError(f"invalid JSON artifact {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise OfficialArtifactError(f"JSON artifact root must be an object: {path}")
    return payload


def _require_mapping(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise OfficialArtifactError(f"{field} must be an object")
    return value


def _require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise OfficialArtifactError(f"{field} must be a non-blank string")
    return value


def _require_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OfficialArtifactError(f"{field} must be a non-negative integer")
    return value


def _require_number(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise OfficialArtifactError(f"{field} must be numeric")
    return float(value)


def _require_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise OfficialArtifactError(f"{field} must be boolean")
    return value


def _require_int_mapping(payload: dict[str, Any], field: str) -> dict[str, int]:
    value = _require_mapping(payload, field)
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in value.values()
    ):
        raise OfficialArtifactError(f"{field} values must be non-negative integers")
    return dict(value)


def _require_string_list(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise OfficialArtifactError(f"{field} must be a list of strings")
    return list(value)
