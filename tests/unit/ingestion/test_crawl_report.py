"""Unit tests for crawl batch report generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.ingestion.models import (
    CrawlResult,
    CrawlSkipRecord,
    CrawlStatus,
    CrawlTarget,
    Priority,
    SourceType,
)
from src.services.crawl_service import (
    CrawlPipelineConfig,
    build_crawl_report,
    write_crawl_report,
)


def _target(law_id: str = "TEST_LAW", url: str = "https://thuvienphapluat.vn/test.aspx") -> CrawlTarget:
    return CrawlTarget(
        law_id=law_id,
        name=f"{law_id} Name",
        tier=1,
        group="Test",
        source_domain="thuvienphapluat.vn",
        source_type=SourceType.HTML,
        url=url,
        crawl_status=CrawlStatus.PENDING,
        priority=Priority.HIGH,
    )


def _build_report(
    tmp_path: Path,
    results: list[CrawlResult],
    skips: list[CrawlSkipRecord] | None = None,
) -> dict:
    started_at = datetime(2026, 6, 5, 1, 2, 3, tzinfo=UTC)
    finished_at = started_at + timedelta(seconds=3.5)
    return build_crawl_report(
        config=CrawlPipelineConfig(
            output_dir=tmp_path / "raw",
            report_path=tmp_path / "reports" / "crawl_report.json",
            registry_path=tmp_path / "registry.yml",
        ),
        mode="registry",
        started_at=started_at,
        finished_at=finished_at,
        total_targets=3,
        selected_targets=len(results),
        results=results,
        skips=skips or [],
    )


def test_crawl_report_schema_from_successful_results(tmp_path: Path) -> None:
    """Crawl report includes successful result metadata and artifact paths."""
    target = _target("SUCCESS")
    latest_dir = tmp_path / "raw" / target.law_id / "latest"
    latest_dir.mkdir(parents=True)
    (latest_dir / "main.html").write_bytes(b"<html>OK</html>")
    (latest_dir / "metadata.json").write_text(
        json.dumps({"crawled_at": "2026-06-05T01:02:03+00:00", "content_hash": "abc123"}),
        encoding="utf-8",
    )

    report = _build_report(
        tmp_path,
        [
            CrawlResult(
                target=target,
                success=True,
                http_status=200,
                content=b"<html>OK</html>",
                content_hash="abc123",
                duration_seconds=1.25,
            )
        ],
    )

    assert report["mode"] == "registry"
    assert report["total_targets"] == 3
    assert report["selected_targets"] == 1
    assert report["successful"] == 1
    assert report["failed"] == 0
    assert report["errors_count"] == 0
    assert report["warnings_count"] == 0
    assert report["raw_dir"] == str(tmp_path / "raw")

    item = report["results"][0]
    assert item["law_id"] == "SUCCESS"
    assert item["status"] == "success"
    assert item["http_status"] == 200
    assert item["output_dir"] == str(latest_dir)
    assert item["main_html_path"] == str(latest_dir / "main.html")
    assert item["metadata_path"] == str(latest_dir / "metadata.json")
    assert item["content_hash"] == "abc123"
    assert item["content_length"] == len(b"<html>OK</html>")
    assert item["crawled_at"] == "2026-06-05T01:02:03+00:00"
    assert item["error"] is None


def test_crawl_report_includes_failed_results_and_errors(tmp_path: Path) -> None:
    """Crawl report represents failed crawl results in results and errors."""
    target = _target("FAIL", "https://thuvienphapluat.vn/fail.aspx")
    report = _build_report(
        tmp_path,
        [
            CrawlResult(
                target=target,
                success=False,
                http_status=500,
                error_message="HTTP 500",
                duration_seconds=0.5,
            )
        ],
    )

    assert report["successful"] == 0
    assert report["failed"] == 1
    assert report["errors_count"] == 1
    assert report["errors"] == [
        {
            "law_id": "FAIL",
            "url": "https://thuvienphapluat.vn/fail.aspx",
            "http_status": 500,
            "error": "HTTP 500",
        }
    ]
    assert report["results"][0]["status"] == "failed"
    assert report["results"][0]["error"] == "HTTP 500"
    assert report["results"][0]["main_html_path"] is None


def test_crawl_report_includes_skipped_results_and_warnings(tmp_path: Path) -> None:
    """Skipped targets appear as skipped results and warnings."""
    target = _target("SKIPPED")
    skip = CrawlSkipRecord(
        target=target,
        reason="Already crawled successfully (verified by metadata.json)",
        existing_metadata_path=str(tmp_path / "raw" / "SKIPPED" / "latest" / "metadata.json"),
        existing_crawled_at="2026-06-04T00:00:00+00:00",
        existing_content_hash="oldhash",
    )

    report = _build_report(tmp_path, [], [skip])

    assert report["skipped_existing"] == 1
    assert report["warnings_count"] == 1
    assert report["results"][0]["law_id"] == "SKIPPED"
    assert report["results"][0]["status"] == "skipped"
    assert report["results"][0]["metadata_path"] == skip.existing_metadata_path
    assert report["results"][0]["content_hash"] == "oldhash"
    assert report["warnings"][0]["reason"] == skip.reason


def test_explicit_report_path_is_respected_and_parent_dirs_are_created(tmp_path: Path) -> None:
    """Report writer uses the supplied path and creates missing parents."""
    report = _build_report(
        tmp_path,
        [CrawlResult(target=_target("SUCCESS"), success=True, http_status=200, content=b"OK")],
    )
    report_path = tmp_path / "custom" / "nested" / "crawl_report.json"

    written_path = write_crawl_report(report_path, report)

    assert written_path == report_path
    assert report_path.exists()
    with report_path.open(encoding="utf-8") as file:
        persisted = json.load(file)
    assert persisted["results"][0]["law_id"] == "SUCCESS"


def test_build_crawl_report_does_not_create_raw_artifacts(tmp_path: Path) -> None:
    """Report building does not write raw evidence artifacts."""
    raw_dir = tmp_path / "raw"
    assert not raw_dir.exists()

    _build_report(
        tmp_path,
        [CrawlResult(target=_target("SUCCESS"), success=True, http_status=200, content=b"OK")],
    )

    assert not raw_dir.exists()
