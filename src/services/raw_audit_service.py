"""Raw corpus audit service.

This module orchestrates the raw corpus audit pipeline, coordinating
registry loading, artifact scanning, and validation checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from src.ingestion.audit import audit_raw_corpus

def run_raw_audit_pipeline(
    registry_path: Path,
    raw_dir: Path,
    output_path: Path,
    min_html_size: int = 10000,
) -> Dict:
    """High-level orchestration of the raw corpus audit pipeline.

    Args:
        registry_path: Path to the corpus registry YAML.
        raw_dir: Path to the raw artifacts directory.
        output_path: Path where the JSON audit report should be written.
        min_html_size: Minimum acceptable HTML file size in bytes.

    Returns:
        The audit report dictionary containing summary and per-item details.
    """
    # The domain logic in src/ingestion/audit.py already performs the full audit
    # and handles report writing if output_path is provided.
    return audit_raw_corpus(
        registry_path=registry_path,
        raw_dir=raw_dir,
        min_html_size=min_html_size,
        output_path=output_path,
    )
