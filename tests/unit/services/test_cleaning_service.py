"""Tests for cleaning service orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import src.services.cleaning_service as cleaning_service
from src.services.cleaning_service import CleaningPipelineConfig, clean_raw_artifact


def _write_raw_artifact(
    tmp_path: Path,
    law_id: str,
    html: str,
    metadata: dict[str, Any],
) -> Path:
    """Write a minimal raw artifact directory for service helper tests."""
    artifact_dir = tmp_path / law_id / "latest"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "main.html").write_text(html, encoding="utf-8")
    (artifact_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return artifact_dir


def _fake_artifact(law_id: str, warnings: list[str] | None = None) -> SimpleNamespace:
    """Build the minimal artifact shape used by execute_cleaning_pipeline."""
    return SimpleNamespace(
        law_id=law_id,
        warnings=warnings or [],
        text_stats=SimpleNamespace(normalized_text_chars=1234, line_count=12),
        markers=SimpleNamespace(
            article_reference_count=3,
            article_heading_count=2,
            max_heading_article_number=2,
            has_heading_article_1=True,
            heading_sequence_score=1.0,
            article_count_estimate=2,
        ),
        candidate_info={"selection_strategy": "fixture"},
    )


def test_execute_cleaning_pipeline_aggregates_success_warning_and_failure(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Cleaning service builds a corpus-level report from per-artifact outcomes."""
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "interim"
    report_path = tmp_path / "reports" / "cleaning_report.json"
    artifacts = {
        "A_LAW": tmp_path / "raw" / "A_LAW" / "latest",
        "B_LAW": tmp_path / "raw" / "B_LAW" / "latest",
        "C_LAW": tmp_path / "raw" / "C_LAW" / "latest",
    }

    def fake_scan_raw_artifacts(path: Path) -> dict[str, Path]:
        assert path == raw_dir
        return artifacts

    def fake_clean_raw_artifact(
        artifact_paths: tuple[Path, Path],
        configured_output_dir: Path,
        min_text_length: int,
        write_txt: bool,
    ) -> tuple[SimpleNamespace | None, list[str]]:
        latest_dir = artifact_paths[0].parent
        law_id = latest_dir.parent.name
        assert configured_output_dir == output_dir
        assert min_text_length == 100
        assert write_txt is True
        if law_id == "A_LAW":
            return _fake_artifact(law_id), []
        if law_id == "B_LAW":
            return _fake_artifact(law_id, ["text_suspiciously_short"]), []
        return None, ["bad artifact"]

    monkeypatch.setattr(cleaning_service, "scan_raw_artifacts", fake_scan_raw_artifacts)
    monkeypatch.setattr(cleaning_service, "clean_raw_artifact", fake_clean_raw_artifact)

    report = cleaning_service.execute_cleaning_pipeline(
        CleaningPipelineConfig(
            raw_dir=raw_dir,
            output_dir=output_dir,
            report_path=report_path,
            min_text_length=100,
            write_txt=True,
        )
    )

    assert report["summary"]["total_artifacts"] == 3
    assert report["summary"]["successfully_cleaned"] == 2
    assert report["summary"]["warning_artifacts"] == 1
    assert report["summary"]["failed"] == 1
    assert report["summary"]["suspiciously_short_texts"] == 1
    assert [item["law_id"] for item in report["items"]] == ["A_LAW", "B_LAW", "C_LAW"]
    assert report["items"][2]["errors"] == ["bad artifact"]
    assert json.loads(report_path.read_text(encoding="utf-8"))["summary"]["failed"] == 1


def test_clean_raw_artifact_generates_normalized_json(tmp_path: Path) -> None:
    """Single-artifact cleaning writes normalized JSON under the output directory."""
    artifact_dir = _write_raw_artifact(
        tmp_path,
        "BLDS_2015",
        """
        <!DOCTYPE html>
        <html><body>
        Điều 1. Nội dung luật.
        Điều 2. Nội dung khác.
        1. Khoản một.
        a) Điểm a.
        </body></html>
        """,
        {
            "law_id": "BLDS_2015",
            "name": "Bộ luật Dân sự 2015",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/van-ban/Bo-luat-dan-su-2015-296215.aspx",
        },
    )
    output_dir = tmp_path / "out"

    artifact, errors = clean_raw_artifact(
        (artifact_dir / "main.html", artifact_dir / "metadata.json"),
        output_dir,
        min_text_length=1,
        write_txt=False,
    )

    assert errors == []
    assert artifact is not None
    assert artifact.law_id == "BLDS_2015"
    assert artifact.normalized_text
    assert (output_dir / "BLDS_2015" / "normalized.json").exists()


def test_clean_raw_artifact_uses_metadata_fallback_fields(tmp_path: Path) -> None:
    """Cleaning service maps legacy metadata names and URL fields safely."""
    artifact_dir = _write_raw_artifact(
        tmp_path,
        "FALLBACK_TEST",
        "Điều 1. Nội dung",
        {
            "law_id": "FALLBACK_TEST",
            "name": "Fallback Law Name",
            "url": "https://example.com/law",
            "source_domain": "example.com",
            "source_type": "html",
        },
    )

    artifact, errors = clean_raw_artifact(
        (artifact_dir / "main.html", artifact_dir / "metadata.json"),
        tmp_path / "out",
        min_text_length=1,
        write_txt=False,
    )

    assert errors == []
    assert artifact is not None
    assert artifact.law_name == "Fallback Law Name"
    assert artifact.source_url == "https://example.com/law"


def test_clean_raw_artifact_warns_for_suspiciously_short_text(tmp_path: Path) -> None:
    """Short cleaned outputs are represented as warnings, not hard failures."""
    artifact_dir = _write_raw_artifact(
        tmp_path,
        "SHORT",
        "Điều 1. Chỉ.",
        {
            "law_id": "SHORT",
            "name": "Short Law",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/short",
        },
    )

    artifact, errors = clean_raw_artifact(
        (artifact_dir / "main.html", artifact_dir / "metadata.json"),
        tmp_path / "out",
        min_text_length=1000,
        write_txt=False,
    )

    assert errors == []
    assert artifact is not None
    assert "text_suspiciously_short" in artifact.warnings


def test_clean_raw_artifact_handles_missing_main_html_gracefully(tmp_path: Path) -> None:
    """Missing raw HTML produces an error list instead of writing outputs."""
    artifact_dir = tmp_path / "MISSING" / "latest"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "metadata.json").write_text("{}", encoding="utf-8")

    artifact, errors = clean_raw_artifact(
        (artifact_dir / "main.html", artifact_dir / "metadata.json"),
        tmp_path / "out",
        min_text_length=1,
        write_txt=False,
    )

    assert artifact is None
    assert errors
