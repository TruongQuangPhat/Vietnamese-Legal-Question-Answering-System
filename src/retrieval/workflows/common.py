"""Shared helpers for retrieval workflow entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.indexing.official_artifacts import write_json_atomic
from src.retrieval.models import RetrievalConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = Path("configs/retrieval/retrieval.yml")
DEFAULT_QUERIES = Path("data/eval/manual_retrieval_queries.jsonl")
PROTECTED_CORPUS_PATHS = (
    REPO_ROOT / "data/raw",
    REPO_ROOT / "data/interim",
    REPO_ROOT / "data/reports",
    REPO_ROOT / "data/processed",
)
REPORTS_ROOT = REPO_ROOT / "artifacts/reports"
RETRIEVAL_REPORTS_ROOT = REPORTS_ROOT / "retrieval"


def load_retrieval_config(path: Path) -> RetrievalConfig:
    """Load and validate the Phase 9A retrieval YAML configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("retrieval config root must be a YAML object")
    return RetrievalConfig.model_validate(payload)


def is_protected_output(path: Path) -> bool:
    """Return whether a report output path violates repository boundaries."""
    resolved = path.expanduser().resolve()
    if any(
        resolved == protected or protected in resolved.parents
        for protected in PROTECTED_CORPUS_PATHS
    ):
        return True
    if resolved == REPORTS_ROOT or REPORTS_ROOT in resolved.parents:
        return not (
            resolved == RETRIEVAL_REPORTS_ROOT or RETRIEVAL_REPORTS_ROOT in resolved.parents
        )
    return False


def is_protected_query_path(path: Path) -> bool:
    """Return whether the query dataset is under a protected corpus path."""
    resolved = path.expanduser().resolve()
    return any(
        resolved == protected or protected in resolved.parents
        for protected in PROTECTED_CORPUS_PATHS
    )


def write_json_report(path: Path, payload: Any) -> None:
    """Write one workflow JSON report atomically as UTF-8."""
    write_json_atomic(path, payload)
