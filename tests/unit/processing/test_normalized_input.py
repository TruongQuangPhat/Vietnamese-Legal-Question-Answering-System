"""Tests for legal hierarchy parsing normalized input loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.processing.legal_hierarchy_models import ParsingIssueCode
from src.processing.normalized_input import (
    NormalizedLegalArtifact,
    compare_cleaned_text,
    load_normalized_artifact,
    load_normalized_input,
)


def _artifact_payload(normalized_text: str = "Điều 1. Phạm vi điều chỉnh\n") -> dict[str, Any]:
    """Build a minimal normalized artifact payload for parser input tests."""
    return {
        "law_id": "TEST_LAW",
        "law_name": "Luật Kiểm thử",
        "source_url": "https://thuvienphapluat.vn/test.aspx",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "raw_artifact_path": "data/raw/TEST_LAW/latest/main.html",
        "normalized_text": normalized_text,
        "text_stats": {"normalized_text_chars": len(normalized_text), "line_count": 1},
        "markers": {
            "article_reference_count": 1,
            "article_heading_count": 1,
            "max_heading_article_number": 1,
            "has_heading_article_1": True,
            "heading_sequence_score": 1.0,
        },
        "warnings": [],
        "metadata": {"cleaner_version": "v0.8.0"},
        "candidate_info": {"selection_strategy": "fixture"},
    }


def _write_normalized(path: Path, payload: dict[str, Any]) -> None:
    """Write a normalized artifact fixture using repository JSON conventions."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_valid_normalized_artifact_loads_correctly(tmp_path: Path) -> None:
    """Load and validate the required normalized artifact fields."""
    normalized_path = tmp_path / "normalized.json"
    _write_normalized(normalized_path, _artifact_payload())

    artifact = load_normalized_artifact(normalized_path)

    assert isinstance(artifact, NormalizedLegalArtifact)
    assert artifact.law_id == "TEST_LAW"
    assert artifact.law_name == "Luật Kiểm thử"
    assert artifact.source_type == "html"
    assert artifact.metadata.cleaner_version == "v0.8.0"
    assert artifact.markers.article_heading_count == 1


def test_required_fields_are_validated(tmp_path: Path) -> None:
    """Reject normalized artifacts missing required legal hierarchy parsing input fields."""
    normalized_path = tmp_path / "normalized.json"
    payload = _artifact_payload()
    del payload["raw_artifact_path"]
    _write_normalized(normalized_path, payload)

    with pytest.raises(ValidationError, match="raw_artifact_path"):
        load_normalized_artifact(normalized_path)


def test_normalized_text_is_preserved_exactly(tmp_path: Path) -> None:
    """Do not strip, normalize, or rewrite the authoritative source string."""
    source_text = "  Điều 1. Phạm vi điều chỉnh\r\nNội dung giữ nguyên.  \n"
    normalized_path = tmp_path / "normalized.json"
    _write_normalized(normalized_path, _artifact_payload(source_text))

    artifact = load_normalized_artifact(normalized_path)

    assert artifact.normalized_text == source_text


def test_matching_cleaned_text_returns_no_warning(tmp_path: Path) -> None:
    """Matching cleaned.txt remains a diagnostic with no parser warning."""
    source_text = "Điều 1. Phạm vi điều chỉnh\n"
    cleaned_path = tmp_path / "cleaned.txt"
    cleaned_path.write_text(source_text, encoding="utf-8")

    warning = compare_cleaned_text(cleaned_path, source_text, law_id="TEST_LAW")

    assert warning is None


def test_mismatching_cleaned_text_returns_structured_warning(tmp_path: Path) -> None:
    """A cleaned.txt mismatch is reported without changing normalized_text."""
    cleaned_path = tmp_path / "cleaned.txt"
    cleaned_path.write_text("Điều 1. Khác\n", encoding="utf-8")

    warning = compare_cleaned_text(
        cleaned_path,
        "Điều 1. Phạm vi điều chỉnh\n",
        law_id="TEST_LAW",
    )

    assert warning is not None
    assert warning.code == ParsingIssueCode.CLEANED_TEXT_MISMATCH
    assert warning.law_id == "TEST_LAW"
    assert warning.context["normalized_length"] == len("Điều 1. Phạm vi điều chỉnh\n")
    assert warning.context["cleaned_length"] == len("Điều 1. Khác\n")


def test_missing_optional_cleaned_text_is_explicit(tmp_path: Path) -> None:
    """Missing cleaned.txt is allowed and produces no consistency warning."""
    normalized_path = tmp_path / "normalized.json"
    _write_normalized(normalized_path, _artifact_payload())

    result = load_normalized_input(normalized_path, cleaned_path=tmp_path / "missing.txt")

    assert result.artifact.law_id == "TEST_LAW"
    assert result.warnings == []
