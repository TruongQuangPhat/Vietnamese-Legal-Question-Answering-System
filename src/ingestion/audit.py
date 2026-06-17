"""Raw corpus audit and validation system.

This module validates crawled legal artifacts before they enter the processing pipeline.
It performs deterministic checks on file presence, metadata correctness, HTML validity,
and detects common error pages or blocks.

Typical usage:
    >>> from pathlib import Path
    >>> report = audit_raw_corpus(
    ...     registry_path=Path("configs/laws/corpus_registry.yml"),
    ...     raw_dir=Path("data/raw"),
    ...     min_html_size=10000
    ... )
    >>> print(report["summary"]["valid_artifacts"])
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .exceptions import AuditError
from .models import CrawlTarget

# Legal text markers to verify the file contains Vietnamese legal content
LEGAL_MARKERS = {
    "điều",
    "khoản",
    "điểm",
    "luật",
    "bộ luật",
    "văn bản hợp nhất",
    "quốc hội",
    "căn cứ",
}

# Error/blocked page indicators (case-insensitive)
ERROR_MARKERS = {
    "captcha",
    "access denied",
    "forbidden",
    "403",
    "404",
    "not found",
    "bad gateway",
    "service unavailable",
    "cloudflare",
    "vui lòng đăng nhập",
    "đăng nhập",
    "không tìm thấy",
    "truy cập bị từ chối",
}


@dataclass
class ArtifactStatus:
    """Validation result for a single raw artifact."""

    law_id: str
    status: str  # "valid", "warning", "invalid", "missing"
    artifact_dir: Path | None = None
    main_html_exists: bool = False
    metadata_json_exists: bool = False
    html_size_bytes: int = 0
    metadata_valid: bool | None = None
    source_url: str | None = None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_registry_law_ids(registry_path: Path) -> set[str]:
    """Load all law_id values from the corpus registry YAML.

    Args:
        registry_path: Path to configs/laws/corpus_registry.yml

    Returns:
        Set of law_id strings.

    Raises:
        AuditError: If registry file not found, YAML parse error, or duplicate law_id.
    """
    if not registry_path.exists():
        raise AuditError(f"Registry file not found: {registry_path}")

    try:
        with registry_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise AuditError(f"YAML parse error in registry: {e}") from e
    except Exception as e:
        raise AuditError(f"Error reading registry: {e}") from e

    if not isinstance(data, dict) or "corpus" not in data:
        raise AuditError("Invalid registry format: missing 'corpus' key")

    entries = data["corpus"]
    if not isinstance(entries, list):
        raise AuditError("Invalid registry format: 'corpus' must be a list")

    law_ids = set()
    duplicates = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        law_id = entry.get("law_id")
        if law_id:
            if law_id in law_ids:
                duplicates.add(law_id)
            law_ids.add(law_id)

    if duplicates:
        raise AuditError(f"Duplicate law_id in registry: {duplicates}")

    return law_ids


def scan_raw_artifacts(raw_dir: Path) -> dict[str, Path]:
    """Scan raw directory for artifact directories.

    Recognizes both layouts:
    - Preferred: {law_id}/latest/main.html and {law_id}/latest/metadata.json
    - Fallback: {law_id}/main.html and {law_id}/metadata.json

    Args:
        raw_dir: Path to data/raw

    Returns:
        Dictionary mapping law_id to artifact directory path (the directory containing the files).
        Only includes law_id directories that have either layout.
    """
    if not raw_dir.exists():
        return {}

    artifacts = {}
    for item in raw_dir.iterdir():
        if not item.is_dir():
            continue
        law_id = item.name

        # Check preferred layout: {law_id}/latest/
        latest_dir = item / "latest"
        if latest_dir.is_dir():
            main_html = latest_dir / "main.html"
            metadata_json = latest_dir / "metadata.json"
            if main_html.is_file() and metadata_json.is_file():
                artifacts[law_id] = latest_dir
                continue

        # Check fallback flat layout: {law_id}/
        main_html = item / "main.html"
        metadata_json = item / "metadata.json"
        if main_html.is_file() and metadata_json.is_file():
            artifacts[law_id] = item

    return artifacts


def validate_metadata(
    metadata_path: Path,
    expected_law_id: str | None = None,
) -> tuple[bool, dict[str, Any], list[str]]:
    """Validate metadata.json structure and fields.

    Args:
        metadata_path: Path to metadata.json
        expected_law_id: If provided, check that metadata law_id matches this value.

    Returns:
        Tuple of (is_valid, metadata_dict, issues)
    """
    issues = []

    if not metadata_path.is_file():
        return False, {}, ["metadata_json_missing"]

    try:
        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
    except json.JSONDecodeError as e:
        return False, {}, [f"invalid_metadata_json: {e}"]

    if not isinstance(metadata, dict):
        return False, metadata, ["metadata_not_dict"]

    # Check required fields
    required_fields = ["law_id", "name", "source_domain", "source_type", "url", "crawl_status"]
    for required_field in required_fields:
        if required_field not in metadata:
            issues.append(f"metadata_missing_field: {required_field}")

    # Validate law_id match if expected provided
    if expected_law_id is not None and "law_id" in metadata:
        if metadata["law_id"] != expected_law_id:
            issues.append(
                f"metadata_law_id_mismatch: expected {expected_law_id}, got {metadata['law_id']}"
            )

    # Validate source_domain contains thuvienphapluat.vn
    if "source_domain" in metadata:
        if "thuvienphapluat.vn" not in metadata["source_domain"].lower():
            issues.append("metadata_source_domain_untrusted")

    # Validate crawl_status
    if "crawl_status" in metadata:
        if metadata["crawl_status"] != "success":
            issues.append(f"metadata_crawl_status_not_success: {metadata['crawl_status']}")

    # Check content_hash exists
    if "content_hash" not in metadata or not metadata["content_hash"]:
        issues.append("metadata_missing_content_hash")

    is_valid = len(issues) == 0
    return is_valid, metadata, issues


def validate_html(
    html_path: Path, min_html_size: int = 10000, sample_size: int = 2048
) -> tuple[int, bool, list[str]]:
    """Validate HTML file: size, UTF-8 encoding, error markers.

    Args:
        html_path: Path to main.html
        min_html_size: Minimum acceptable file size in bytes
        sample_size: Number of bytes to sample for marker detection

    Returns:
        Tuple of (size_bytes, is_valid, issues)
    """
    issues = []

    if not html_path.is_file():
        return 0, False, ["html_missing"]

    try:
        size = html_path.stat().st_size
    except OSError as e:
        return 0, False, [f"html_stat_error: {e}"]

    if size == 0:
        issues.append("html_empty")
        return size, False, issues

    if size < min_html_size:
        issues.append(f"html_size_suspiciously_small: {size} < {min_html_size}")

    # Check for null bytes in first sample (indicates binary/corruption)
    try:
        sample = html_path.read_bytes()[:sample_size]
        if b"\x00" in sample:
            issues.append("html_contains_null_bytes")
    except OSError as e:
        issues.append(f"html_read_error: {e}")
        return size, False, issues

    # Check UTF-8 decode
    try:
        with html_path.open("r", encoding="utf-8") as f:
            content_sample = f.read(sample_size)
    except UnicodeDecodeError as e:
        issues.append(f"html_not_utf8: {e}")
        return size, False, issues
    except OSError as e:
        issues.append(f"html_read_error: {e}")
        return size, False, issues

    # Detect error markers
    content_lower = content_sample.lower()
    found_markers = [m for m in ERROR_MARKERS if m in content_lower]
    if found_markers:
        issues.append(f"likely_error_page: {found_markers[:3]}")

    # Check for legal text markers
    legal_markers_found = [m for m in LEGAL_MARKERS if m in content_lower]
    if not legal_markers_found:
        issues.append("no_legal_markers")

    is_valid = (
        len(
            [
                i
                for i in issues
                if not i.startswith("html_size_suspiciously_small") and i != "no_legal_markers"
            ]
        )
        == 0
    )
    return size, is_valid, issues


def check_legal_text_markers(html_path: Path, sample_size: int = 2048) -> bool:
    """Quick check if HTML contains at least one Vietnamese legal marker."""
    try:
        with html_path.open("r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(sample_size).lower()
        return any(marker in sample for marker in LEGAL_MARKERS)
    except OSError:
        return False


def audit_single_artifact(
    law_id: str,
    artifact_dir: Path,
    registry_entries: dict[str, CrawlTarget | dict[str, Any]],
    min_html_size: int,
) -> ArtifactStatus:
    """Audit a single raw artifact.

    Args:
        law_id: Expected law_id
        artifact_dir: Path to artifact directory (containing main.html and metadata.json)
        registry_entries: Dictionary of all registry entries for lookup
        min_html_size: Minimum HTML file size threshold

    Returns:
        ArtifactStatus object.
    """
    status = ArtifactStatus(law_id=law_id, status="valid")
    status.artifact_dir = artifact_dir

    expected_entry = registry_entries.get(law_id)

    # Check main.html
    main_html = artifact_dir / "main.html"
    if main_html.is_file():
        status.main_html_exists = True
        html_size, html_valid, html_issues = validate_html(main_html, min_html_size)
        status.html_size_bytes = html_size

        # Classify issues as warnings or errors
        for issue in html_issues:
            if issue.startswith("html_size_suspiciously_small") or issue == "no_legal_markers":
                status.warnings.append(issue)
            else:
                status.issues.append(issue)

        if not html_valid:
            status.status = "invalid"
    else:
        status.main_html_exists = False
        status.issues.append("missing_main_html")
        status.status = "invalid"

    # Check metadata.json
    metadata_json = artifact_dir / "metadata.json"
    if metadata_json.is_file():
        status.metadata_json_exists = True
        metadata_valid, metadata_dict, metadata_issues = validate_metadata(
            metadata_json, expected_law_id=law_id if expected_entry else None
        )
        status.metadata_valid = metadata_valid

        # Extract source_url if available
        if metadata_valid and "url" in metadata_dict:
            status.source_url = metadata_dict["url"]

        for issue in metadata_issues:
            status.issues.append(issue)

        if not metadata_valid:
            status.status = "invalid"
    else:
        status.metadata_json_exists = False
        status.issues.append("missing_metadata_json")
        status.status = "invalid"

    # If any critical issues, mark as invalid
    if status.issues:
        status.status = "invalid"

    # If no issues but warnings exist, mark as warning
    if status.warnings and status.status == "valid":
        status.status = "warning"

    # If artifact directory itself is missing (handled externally), mark as missing
    if not artifact_dir.exists():
        status.status = "missing"

    return status


def audit_raw_corpus(
    registry_path: Path, raw_dir: Path, min_html_size: int = 10000, output_path: Path | None = None
) -> dict:
    """Perform full raw corpus audit.

    Args:
        registry_path: Path to corpus registry YAML
        raw_dir: Path to data/raw directory
        min_html_size: Minimum acceptable HTML file size in bytes
        output_path: Optional path to write JSON report

    Returns:
        Audit report dictionary.
    """
    # Load registry law_ids
    registry_law_ids = load_registry_law_ids(registry_path)

    # Load registry entries for validation (full entries, not just IDs)
    try:
        with registry_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        registry_entries: dict[str, CrawlTarget | dict[str, Any]] = {}
        for entry in data.get("corpus", []):
            law_id = entry.get("law_id")
            if law_id:
                try:
                    registry_entries[law_id] = CrawlTarget(**entry)
                except Exception:
                    # Still include the law_id in the set, but the entry may be incomplete
                    # We'll handle validation issues in the metadata check
                    registry_entries[law_id] = entry
    except Exception as e:
        raise AuditError(f"Failed to load full registry entries: {e}") from e

    # Scan raw artifacts
    raw_artifacts = scan_raw_artifacts(raw_dir)
    raw_law_ids = set(raw_artifacts.keys())

    # Compute differences
    missing_in_raw = registry_law_ids - raw_law_ids
    extra_in_raw = raw_law_ids - registry_law_ids

    # Audit each registry entry
    items = []
    for law_id in sorted(registry_law_ids):
        if law_id in missing_in_raw:
            # Artifact missing entirely
            item = ArtifactStatus(
                law_id=law_id, status="missing", artifact_dir=None, issues=["artifact_missing"]
            )
        else:
            # Artifact exists, validate it
            artifact_dir = raw_artifacts[law_id]
            item = audit_single_artifact(
                law_id=law_id,
                artifact_dir=artifact_dir,
                registry_entries=registry_entries,
                min_html_size=min_html_size,
            )
        items.append(item)

    # Build summary
    summary = {
        "registry_entries": len(registry_law_ids),
        "raw_artifacts_found": len(raw_law_ids),
        "valid_artifacts": sum(1 for i in items if i.status == "valid"),
        "warning_artifacts": sum(1 for i in items if i.status == "warning"),
        "invalid_artifacts": sum(1 for i in items if i.status == "invalid"),
        "missing_artifacts": sum(1 for i in items if i.status == "missing"),
        "extra_artifacts": len(extra_in_raw),
        "missing_main_html": sum(1 for i in items if not i.main_html_exists),
        "missing_metadata_json": sum(1 for i in items if not i.metadata_json_exists),
        "invalid_metadata_json": sum(1 for i in items if i.metadata_valid is False),
        "suspicious_small_html": sum(
            1 for i in items if any("html_size_suspiciously_small" in w for w in i.warnings)
        ),
        "possible_error_pages": sum(
            1 for i in items if any("likely_error_page" in iss for iss in i.issues)
        ),
    }

    # Build report dict
    report = {
        "summary": summary,
        "missing_in_raw": sorted(missing_in_raw),
        "extra_in_raw": sorted(extra_in_raw),
        "items": [
            {
                "law_id": item.law_id,
                "status": item.status,
                "artifact_dir": str(item.artifact_dir) if item.artifact_dir else None,
                "main_html_exists": item.main_html_exists,
                "metadata_json_exists": item.metadata_json_exists,
                "html_size_bytes": item.html_size_bytes,
                "metadata_valid": item.metadata_valid,
                "source_url": item.source_url,
                "issues": item.issues,
                "warnings": item.warnings,
            }
            for item in items
        ],
    }

    # Write to output if specified
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    return report
