"""Tests for raw corpus audit service orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import src.services.raw_audit_service as raw_audit_service


def test_run_raw_audit_pipeline_delegates_to_ingestion_audit(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """The service passes configured paths to the ingestion audit function."""
    captured: dict[str, Any] = {}
    expected_report = {"summary": {"status": "ok"}}

    def fake_audit_raw_corpus(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return expected_report

    monkeypatch.setattr(raw_audit_service, "audit_raw_corpus", fake_audit_raw_corpus)

    result = raw_audit_service.run_raw_audit_pipeline(
        registry_path=tmp_path / "registry.yml",
        raw_dir=tmp_path / "raw",
        output_path=tmp_path / "reports" / "raw_corpus_audit.json",
        min_html_size=2048,
    )

    assert result == expected_report
    assert captured == {
        "registry_path": tmp_path / "registry.yml",
        "raw_dir": tmp_path / "raw",
        "min_html_size": 2048,
        "output_path": tmp_path / "reports" / "raw_corpus_audit.json",
    }
