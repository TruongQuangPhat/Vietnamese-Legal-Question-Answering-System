"""Tests for cleaning quality audit service wrappers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import src.services.cleaning_quality_audit_service as quality_service


def test_run_cleaning_quality_audit_writes_report_with_vietnamese_text(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """The service writes the diagnostics report under the requested directory."""
    report = {
        "metadata": {"audit_type": "cleaning_quality"},
        "items": [{"law_id": "TEST", "title": "Điều 1. Quy định chung"}],
    }

    def fake_compute_cleaning_quality_audit(interim_dir: Path) -> dict[str, Any]:
        assert interim_dir == tmp_path / "interim"
        return report

    monkeypatch.setattr(
        quality_service,
        "compute_cleaning_quality_audit",
        fake_compute_cleaning_quality_audit,
    )

    result = quality_service.run_cleaning_quality_audit(
        interim_dir=tmp_path / "interim",
        report_dir=tmp_path / "reports",
    )

    report_path = tmp_path / "reports" / "cleaning_quality_audit.json"
    assert result == report
    assert report_path.exists()
    persisted = report_path.read_text(encoding="utf-8")
    assert "Điều 1. Quy định chung" in persisted
    assert "\\u" not in persisted
    assert json.loads(persisted) == report


def test_run_raw_vs_cleaning_comparison_delegates_and_writes_report(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Raw-vs-cleaning comparison service delegates to diagnostics code."""
    captured: dict[str, Path] = {}
    report = {"metadata": {"audit_type": "raw_vs_cleaning"}, "items": []}

    def fake_compute_raw_vs_cleaning_comparison(
        *,
        raw_dir: Path,
        interim_dir: Path,
    ) -> dict[str, Any]:
        captured["raw_dir"] = raw_dir
        captured["interim_dir"] = interim_dir
        return report

    monkeypatch.setattr(
        quality_service,
        "compute_raw_vs_cleaning_comparison",
        fake_compute_raw_vs_cleaning_comparison,
    )

    result = quality_service.run_raw_vs_cleaning_comparison(
        raw_dir=tmp_path / "raw",
        interim_dir=tmp_path / "interim",
        report_dir=tmp_path / "reports",
    )

    assert result == report
    assert captured == {"raw_dir": tmp_path / "raw", "interim_dir": tmp_path / "interim"}
    assert (tmp_path / "reports" / "raw_vs_cleaning_comparison.json").exists()
