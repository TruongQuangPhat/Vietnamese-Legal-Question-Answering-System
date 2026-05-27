"""Orchestration service for cleaning quality audits.

This service coordinates diagnostic computations and writes JSON reports.
Argument parsing and terminal formatting belong to the CLI layer.
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Any

from src.ingestion.cleaning_diagnostics import (
    audit_all_raw_html,
    compute_cleaning_quality_audit,
    compute_corpus_inventory,
    compute_pattern_groups,
    compute_raw_vs_cleaning_comparison,
    compute_selector_candidate_audit,
    ping_diagnostics,
)


def ping_service() -> str:
    """Check that the service and diagnostics module are linked."""
    return ping_diagnostics()


def run_corpus_inventory(
    registry_path: Path,
    raw_dir: Path,
    interim_dir: Path,
    report_dir: Path,
) -> dict[str, Any]:
    """Run corpus inventory audit and write its JSON report.

    Args:
        registry_path: Path to corpus registry YAML.
        raw_dir: Directory containing raw HTML artifacts.
        interim_dir: Directory containing normalized artifacts.
        report_dir: Directory to write audit reports.

    Returns:
        Report dictionary with metadata, total_records, items, and errors.
    """
    report = compute_corpus_inventory(
        registry_path=registry_path,
        raw_dir=raw_dir,
        interim_dir=interim_dir,
        report_dir=report_dir,
    )
    return _write_report(report_dir / "cleaning_quality_inventory.json", report)


def run_html_pattern_audit(raw_dir: Path, report_dir: Path) -> dict[str, Any]:
    """Run raw HTML pattern audit and write its JSON report.

    Args:
        raw_dir: Directory containing raw HTML artifacts.
        report_dir: Directory to write audit reports.

    Returns:
        Report dictionary with metadata, total_records, items, and errors.
    """
    profiles, errors = audit_all_raw_html(raw_dir)
    report = {
        "metadata": {
            "audit_type": "html_pattern_audit",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "audit_version": "1.0",
        },
        "total_records": len(profiles),
        "items": [profile.to_dict() for profile in profiles],
        "errors": errors,
    }
    return _write_report(report_dir / "html_pattern_audit.json", report)


def run_selector_candidate_audit(raw_dir: Path, report_dir: Path) -> dict[str, Any]:
    """Run raw HTML selector candidate audit and write its JSON report.

    Args:
        raw_dir: Directory containing raw HTML artifacts.
        report_dir: Directory to write audit reports.

    Returns:
        Report dictionary with metadata, total_records, items, and errors.
    """
    report = compute_selector_candidate_audit(raw_dir)
    return _write_report(report_dir / "selector_candidate_audit.json", report)


def run_cleaning_quality_audit(interim_dir: Path, report_dir: Path) -> dict[str, Any]:
    """Run normalized output quality audit and write its JSON report.

    Args:
        interim_dir: Directory containing normalized artifacts.
        report_dir: Directory to write audit reports.

    Returns:
        Report dictionary with metadata, total_records, items, and errors.
    """
    report = compute_cleaning_quality_audit(interim_dir)
    return _write_report(report_dir / "cleaning_quality_audit.json", report)


def run_raw_vs_cleaning_comparison(
    raw_dir: Path,
    interim_dir: Path,
    report_dir: Path,
) -> dict[str, Any]:
    """Run raw-vs-cleaning comparison audit and write its JSON report.

    Args:
        raw_dir: Directory containing raw HTML artifacts.
        interim_dir: Directory containing normalized artifacts.
        report_dir: Directory to write audit reports.

    Returns:
        Report dictionary with metadata, total_records, items, and errors.
    """
    report = compute_raw_vs_cleaning_comparison(raw_dir=raw_dir, interim_dir=interim_dir)
    return _write_report(report_dir / "raw_vs_cleaning_comparison.json", report)


def run_pattern_groups(
    registry_path: Path,
    raw_dir: Path,
    interim_dir: Path,
    report_dir: Path,
) -> dict[str, Any]:
    """Run law pattern grouping audit and write its JSON report.

    Args:
        registry_path: Path to corpus registry YAML.
        raw_dir: Directory containing raw HTML artifacts.
        interim_dir: Directory containing normalized artifacts.
        report_dir: Directory to write audit reports.

    Returns:
        Report dictionary with metadata, total_records, items, and errors.
    """
    report = compute_pattern_groups(
        registry_path=registry_path,
        raw_dir=raw_dir,
        interim_dir=interim_dir,
    )
    return _write_report(report_dir / "pattern_groups.json", report)


def _write_report(report_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    return report
