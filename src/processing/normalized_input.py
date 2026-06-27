"""Typed legal hierarchy parsing loading for normalized legal artifacts.

This module only validates parser input and compares the optional
`cleaned.txt` diagnostic artifact. It never mutates source text, writes corpus
artifacts, or generates hierarchy output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.processing.legal_hierarchy_models import ParsingIssueCode, StructuredParsingIssue


class NormalizedArtifactMarkers(BaseModel):
    """cleaning/normalization legal marker metrics required by legal hierarchy parsing."""

    model_config = ConfigDict(extra="allow")

    article_reference_count: int = Field(..., ge=0)
    article_heading_count: int = Field(..., ge=0)
    max_heading_article_number: int = Field(..., ge=0)
    has_heading_article_1: bool = Field(...)
    heading_sequence_score: float = Field(..., ge=0.0)


class NormalizedArtifactMetadata(BaseModel):
    """cleaning/normalization metadata required by legal hierarchy parsing."""

    model_config = ConfigDict(extra="allow")

    cleaner_version: str = Field(..., min_length=1)


class NormalizedLegalArtifact(BaseModel):
    """Validated `normalized.json` input for legal hierarchy parsing.

    Attributes:
        law_id: Stable law identifier.
        law_name: Legal document name.
        source_url: Trusted source URL.
        source_domain: Trusted source domain.
        source_type: Source content type as produced by cleaning/normalization.
        raw_artifact_path: Raw artifact path used for traceability.
        normalized_text: Authoritative source text for parser offsets.
        text_stats: cleaning/normalization text statistics.
        markers: cleaning/normalization legal marker metrics.
        warnings: cleaning/normalization warnings carried for diagnostics.
        metadata: cleaning/normalization metadata, including cleaner version.
        candidate_info: cleaning/normalization extraction diagnostics.

    Legal assumptions:
        `normalized_text` is authoritative. The loader does not strip,
        normalize, or rewrite it before downstream parser offset calculation.
    """

    model_config = ConfigDict(extra="allow")

    law_id: str = Field(..., min_length=1)
    law_name: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=1)
    source_domain: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    raw_artifact_path: str = Field(..., min_length=1)
    normalized_text: str = Field(..., min_length=1)
    text_stats: dict[str, Any] = Field(default_factory=dict)
    markers: NormalizedArtifactMarkers = Field(...)
    warnings: list[str] = Field(default_factory=list)
    metadata: NormalizedArtifactMetadata = Field(...)
    candidate_info: dict[str, Any] = Field(default_factory=dict)


class NormalizedInputLoadResult(BaseModel):
    """Result of loading parser input plus optional diagnostics."""

    model_config = ConfigDict(extra="forbid")

    artifact: NormalizedLegalArtifact = Field(...)
    warnings: list[StructuredParsingIssue] = Field(default_factory=list)


def load_normalized_artifact(path: Path) -> NormalizedLegalArtifact:
    """Load and validate a cleaning/normalization `normalized.json` artifact.

    Args:
        path: Path to `data/interim/{LAW_ID}/normalized.json` or a test fixture.

    Returns:
        Typed normalized legal artifact with the authoritative `normalized_text`
        value preserved exactly as loaded from JSON.

    Raises:
        FileNotFoundError: If the artifact path does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        pydantic.ValidationError: If the required legal hierarchy parsing input contract is
            missing or invalid.

    Legal assumptions:
        The parser must calculate all offsets from this exact loaded text, not
        from `cleaned.txt` or any rewritten variant.
    """
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return NormalizedLegalArtifact.model_validate(payload)


def compare_cleaned_text(
    cleaned_path: Path,
    normalized_text: str,
    *,
    law_id: str,
) -> StructuredParsingIssue | None:
    """Compare optional `cleaned.txt` against authoritative normalized text.

    Args:
        cleaned_path: Optional diagnostic text artifact path.
        normalized_text: Exact source string loaded from `normalized.json`.
        law_id: Law identifier used in structured warning output.

    Returns:
        `None` when `cleaned.txt` is absent or exactly matches
        `normalized_text`; otherwise a `CLEANED_TEXT_MISMATCH` warning.

    Legal assumptions:
        A mismatch is a corpus consistency warning only. Parsing must continue
        from `normalized_text` and must never switch to `cleaned.txt`.
    """
    if not cleaned_path.exists():
        return None

    cleaned_text = cleaned_path.read_text(encoding="utf-8")
    if cleaned_text == normalized_text:
        return None

    return StructuredParsingIssue(
        code=ParsingIssueCode.CLEANED_TEXT_MISMATCH,
        message="cleaned.txt differs from normalized_text; normalized_text remains authoritative.",
        law_id=law_id,
        node_id=None,
        start_offset=None,
        end_offset=None,
        context={
            "cleaned_path": str(cleaned_path),
            "normalized_length": len(normalized_text),
            "cleaned_length": len(cleaned_text),
        },
    )


def load_normalized_input(
    normalized_path: Path,
    cleaned_path: Path | None = None,
) -> NormalizedInputLoadResult:
    """Load normalized parser input and compare optional `cleaned.txt`.

    Args:
        normalized_path: Path to the authoritative normalized JSON artifact.
        cleaned_path: Optional explicit cleaned text path. If omitted, the
            loader checks `cleaned.txt` next to `normalized.json`.

    Returns:
        Loaded artifact plus zero or more structured warnings.

    Legal assumptions:
        The returned artifact always uses `normalized.json["normalized_text"]`
        as the only parser source string, regardless of cleaned text status.
    """
    artifact = load_normalized_artifact(normalized_path)
    diagnostic_path = cleaned_path or normalized_path.with_name("cleaned.txt")
    warning = compare_cleaned_text(
        diagnostic_path,
        artifact.normalized_text,
        law_id=artifact.law_id,
    )
    warnings = [] if warning is None else [warning]
    return NormalizedInputLoadResult(artifact=artifact, warnings=warnings)
