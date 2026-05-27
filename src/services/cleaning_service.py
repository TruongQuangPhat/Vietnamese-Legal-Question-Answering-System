"""Cleaning & Normalization service.

This module orchestrates the cleaning pipeline, coordinating raw artifact
discovery, text extraction, and normalization processes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.ingestion.audit import scan_raw_artifacts
from src.ingestion.cleaning import (
    CLEANER_VERSION,
    CleaningStats,
    LegalMarkersSummary,
    NormalizedArtifact,
    detect_legal_markers,
    extract_legal_text_from_html,
    normalize_unicode,
    normalize_whitespace,
    remove_encoded_footer_artifacts,
    remove_safe_boilerplate,
    trim_to_legal_body,
)

@dataclass
class CleaningPipelineConfig:
    """Configuration for the cleaning pipeline execution."""
    raw_dir: Path
    output_dir: Path
    report_path: Path
    min_text_length: int = 10000
    write_txt: bool = False
    verbose: bool = False

def execute_cleaning_pipeline(config: CleaningPipelineConfig) -> Dict:
    """Orchestrates the full cleaning and normalization pipeline.

    Args:
        config: Configuration for the pipeline execution.

    Returns:
        A dictionary containing the summary and per-item results.
    """
    artifacts = scan_raw_artifacts(config.raw_dir)

    results = []
    summary = {
        "total_artifacts": len(artifacts),
        "successfully_cleaned": 0,
        "warning_artifacts": 0,
        "failed": 0,
        "suspiciously_short_texts": 0,
        "missing_article_marker": 0,
        "output_dir": str(config.output_dir)
    }

    for law_id, artifact_dir in sorted(artifacts.items()):
        main_html = artifact_dir / "main.html"
        meta_json = artifact_dir / "metadata.json"

        artifact, errors = clean_raw_artifact(
            (main_html, meta_json),
            config.output_dir,
            config.min_text_length,
            config.write_txt
        )

        if artifact:
            summary["successfully_cleaned"] += 1
            status = "success"
            if artifact.warnings:
                status = "warning"
                summary["warning_artifacts"] += 1

            if "text_suspiciously_short" in artifact.warnings:
                summary["suspiciously_short_texts"] += 1
            if "missing_article_marker" in artifact.warnings:
                summary["missing_article_marker"] += 1

            results.append({
                "law_id": artifact.law_id,
                "status": status,
                "output_path": str(config.output_dir / artifact.law_id / "normalized.json"),
                "normalized_text_chars": artifact.text_stats.normalized_text_chars,
                "line_count": artifact.text_stats.line_count,
                "article_reference_count": artifact.markers.article_reference_count,
                "article_heading_count": artifact.markers.article_heading_count,
                "max_heading_article_number": artifact.markers.max_heading_article_number,
                "has_heading_article_1": artifact.markers.has_heading_article_1,
                "heading_sequence_score": artifact.markers.heading_sequence_score,
                "article_count_estimate": artifact.markers.article_count_estimate,
                "warnings": artifact.warnings,
                "errors": [],
                "candidate_info": artifact.candidate_info
            })
        else:
            summary["failed"] += 1
            results.append({
                "law_id": law_id,
                "status": "failed",
                "output_path": None,
                "normalized_text_chars": 0,
                "line_count": 0,
                "article_reference_count": 0,
                "article_heading_count": 0,
                "max_heading_article_number": 0,
                "has_heading_article_1": False,
                "heading_sequence_score": 0.0,
                "article_count_estimate": 0,
                "warnings": [],
                "errors": errors
            })

    report = {
        "metadata": {
            "cleaner_version": CLEANER_VERSION,
        },
        "summary": summary,
        "items": results
    }

    # Write the corpus-level report
    report_path = config.report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report

def clean_raw_artifact(
    artifact_paths: Tuple[Path, Path],
    output_dir: Path,
    min_text_length: int,
    write_txt: bool,
) -> Tuple[Optional[NormalizedArtifact], List[str]]:
    """Cleans a single raw legal artifact.

    Args:
        artifact_paths: Tuple of (main_html_path, metadata_json_path).
        output_dir: Directory to save normalized artifacts.
        min_text_length: Minimum acceptable length for a warning.
        write_txt: Whether to write an optional cleaned.txt file.

    Returns:
        Tuple of (NormalizedArtifact or None, list of errors).
    """
    main_html_path, metadata_json_path = artifact_paths
    law_id = main_html_path.parent.name
    if "latest" in main_html_path.parts:
        law_id = main_html_path.parent.parent.name

    try:
        # Load metadata
        with metadata_json_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        raw_html_size = main_html_path.stat().st_size

        with main_html_path.open("r", encoding="utf-8") as f:
            html_content = f.read()

        # Core cleaning pipeline
        extracted_text, candidate_info = extract_legal_text_from_html(html_content)
        extracted_chars = len(extracted_text)

        text = trim_to_legal_body(extracted_text, candidate_info)
        text = remove_safe_boilerplate(text)
        text, uni_warnings = normalize_unicode(text)
        text = normalize_whitespace(text)
        text = remove_encoded_footer_artifacts(text)

        markers = detect_legal_markers(text)

        stats = CleaningStats(
            raw_html_size_bytes=raw_html_size,
            extracted_text_chars=extracted_chars,
            normalized_text_chars=len(text),
            line_count=len(text.splitlines())
        )

        warnings = list(uni_warnings)
        if len(text) < min_text_length:
            warnings.append("text_suspiciously_short")
        if not markers.contains_article:
            warnings.append("missing_article_marker")

        # Quality check for known long laws
        LONG_LAWS_MIN_ARTICLES = {
            "BLDS_2015": 650,
            "BLHS_VBHN": 400,
            "BLTTDS_VBHN": 400,
            "BLTTHS_VBHN": 400,
        }
        actual_max_art = markers.max_heading_article_number
        if law_id in LONG_LAWS_MIN_ARTICLES:
            if actual_max_art < LONG_LAWS_MIN_ARTICLES[law_id]:
                warnings.append("suspicious_low_max_article_number")

        # Metadata fallback logic
        artifact = NormalizedArtifact(
            law_id=meta.get("law_id", law_id),
            law_name=meta.get("law_name") or meta.get("name") or "Unknown",
            source_url=meta.get("source_url") or meta.get("url") or "Unknown",
            source_domain=meta.get("source_domain") or "Unknown",
            source_type="html",
            raw_artifact_path=str(main_html_path),
            normalized_text=text,
            text_stats=stats,
            markers=markers,
            warnings=warnings,
            candidate_info=candidate_info
        )

        law_out_dir = output_dir / artifact.law_id
        law_out_dir.mkdir(parents=True, exist_ok=True)

        with (law_out_dir / "normalized.json").open("w", encoding="utf-8") as f:
            json.dump(artifact.to_dict(), f, indent=2, ensure_ascii=False)

        if write_txt:
            with (law_out_dir / "cleaned.txt").open("w", encoding="utf-8") as f:
                f.write(artifact.normalized_text)

        return artifact, []

    except Exception as e:
        return None, [str(e)]
