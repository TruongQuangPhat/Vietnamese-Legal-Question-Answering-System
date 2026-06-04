"""Crawl pipeline service.

This module orchestrates the legal document crawling phase, coordinating the
registry, selector, crawler, and storage components.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from rich.console import Console
from rich.table import Table

from src.core.config import get_settings
from src.ingestion.crawler import ThuvienPhapLuatCrawler
from src.ingestion.models import (
    CrawlResult,
    CrawlSelection,
    CrawlSkipRecord,
    CrawlStatus,
    CrawlTarget,
    Priority,
    SourceType,
)
from src.ingestion.rate_limiter import RateLimiter
from src.ingestion.registry import CorpusRegistryLoader
from src.ingestion.selector import CrawlTargetSelector
from src.ingestion.storage import RawArtifactStore

console = Console()

@dataclass
class CrawlPipelineConfig:
    """Configuration for a crawl pipeline execution."""
    output_dir: Path
    report_path: Path | None = Path("artifacts/reports/crawling/crawl_report.json")
    registry_path: Path | None = None
    url: str | None = None
    law_id: str | None = None
    law_ids: list[str] | None = None
    tiers: list[int] | None = None
    groups: list[str] | None = None
    priorities: list[str] | None = None
    only_statuses: list[str] | None = None
    include_manual_review: bool = False
    skip_already_crawled: bool = True
    force: bool = False
    dry_run: bool = False
    concurrency: int = 2
    delay_seconds: float | None = None
    retry: int | None = None
    verbose: bool = False

@dataclass
class CrawlPipelineResult:
    """Result of a crawl pipeline execution."""
    success: bool
    failure_count: int
    results: list[CrawlResult]
    skips: list[CrawlSkipRecord]
    report_path: Path | None = None
    report: dict[str, Any] | None = None

def print_selection_table(selection: CrawlSelection) -> None:
    """Print selection details in a table format."""
    if not selection.targets:
        console.print("[yellow]No targets selected.[/]")
        return

    table = Table(
        title=f"Selected {selection.selected_count} targets",
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("Law ID", style="cyan")
    table.add_column("Name", max_width=40)
    table.add_column("Tier", justify="center")
    table.add_column("Priority", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("URL", max_width=50)

    for target in selection.targets:
        url_display = (
            target.url[:50] + "..."
            if target.url and len(target.url) > 50
            else (target.url or "N/A")
        )
        table.add_row(
            target.law_id,
            target.name[:40] + "..." if len(target.name) > 40 else target.name,
            str(target.tier),
            target.priority.value,
            target.crawl_status.value,
            url_display,
        )

    console.print(table)

def print_crawl_summary(
    results: list[CrawlResult],
    skips: list[CrawlSkipRecord],
    start_time: datetime,
) -> None:
    """Print crawl execution summary."""
    success_count = sum(1 for r in results if r.success)
    failure_count = len(results) - success_count
    duration = (datetime.now(UTC) - start_time).total_seconds()

    console.print("\n" + "=" * 60)
    console.print("CRAWL EXECUTION SUMMARY", style="bold")
    console.print("=" * 60)
    console.print(f"Total attempted:     {len(results)}")
    console.print(f"Successful:          [green]{success_count}[/]")
    console.print(f"Failed:              [red]{failure_count}[/]")
    console.print(f"Skipped:             [yellow]{len(skips)}[/]")
    console.print(f"Duration:            {duration:.2f}s")
    console.print("=" * 60)

    if failure_count > 0:
        console.print("\n[red]Failed crawls:[/]")
        for result in results:
            if not result.success:
                console.print(f"  - {result.target.law_id}: {result.error_message}")

    if skips:
        console.print("\n[yellow]Skipped targets:[/]")
        for record in skips:
            console.print(f"  - {record.target.law_id}: {record.reason}")

async def run_crawl_pipeline(config: CrawlPipelineConfig) -> CrawlPipelineResult:
    """High-level orchestration of the crawl pipeline."""
    if config.url:
        return await _crawl_single_url(config)
    elif config.registry_path:
        return await _crawl_from_registry(config)
    else:
        raise ValueError("Either registry_path or url must be provided.")

async def _crawl_single_url(config: CrawlPipelineConfig) -> CrawlPipelineResult:
    """Internal orchestration for single URL crawl."""
    started_at = datetime.now(UTC)
    if not config.law_id:
        raise ValueError("--law-id is required when using --url")

    console.print("[cyan]Debug crawl mode[/]")
    console.print(f"  URL: {config.url}")
    console.print(f"  Law ID: {config.law_id}")

    settings = get_settings()
    from urllib.parse import urlparse
    parsed = urlparse(config.url)
    hostname = parsed.hostname

    if not hostname or settings.trusted_domain not in hostname:
        console.print(f"[red]Error: URL must be from {settings.trusted_domain}[/]")
        return _finalize_crawl_pipeline_result(
            config=config,
            mode="url",
            started_at=started_at,
            total_targets=1,
            selected_targets=0,
            results=[],
            skips=[],
            success=False,
        )

    storage = RawArtifactStore(str(config.output_dir))
    rate_limiter = RateLimiter(
        delay_seconds=config.delay_seconds or settings.crawler_rate_limit_seconds,
        max_concurrency=1,
    )
    crawler = ThuvienPhapLuatCrawler(
        rate_limiter=rate_limiter,
        storage=storage,
        max_retries=config.retry or settings.crawler_max_retries,
    )

    target = CrawlTarget(
        law_id=config.law_id,
        name=config.law_id,
        tier=0,
        group="debug",
        source_domain=settings.trusted_domain,
        source_type=SourceType.HTML,
        url=config.url,
        crawl_status=CrawlStatus.PENDING,
        priority=Priority.HIGH,
        effective_date=None,
        expiry_date=None,
        notes=None,
    )

    console.print("\n[cyan]Starting crawl...[/]")
    result = await crawler.crawl(target)

    if result.success:
        console.print("[green]Success![/]")
        content_hash_display = result.content_hash[:32] + "..." if result.content_hash else "N/A"
        console.print(f"  Content hash: {content_hash_display}")
        console.print(f"  Duration: {result.duration_seconds:.2f}s")
        if result.http_status:
            console.print(f"  HTTP Status: {result.http_status}")
        return _finalize_crawl_pipeline_result(
            config=config,
            mode="url",
            started_at=started_at,
            total_targets=1,
            selected_targets=1,
            results=[result],
            skips=[],
            success=True,
        )
    else:
        console.print(f"[red]Failed:[/] {result.error_message}")
        return _finalize_crawl_pipeline_result(
            config=config,
            mode="url",
            started_at=started_at,
            total_targets=1,
            selected_targets=1,
            results=[result],
            skips=[],
            success=False,
        )

async def _crawl_from_registry(config: CrawlPipelineConfig) -> CrawlPipelineResult:
    """Internal orchestration for registry-based batch crawl."""
    start_time = datetime.now(UTC)
    console.print("[cyan]Registry crawl mode[/]")
    console.print(f"  Registry: {config.registry_path}")
    console.print(f"  Output: {config.output_dir}")

    loader = CorpusRegistryLoader(str(config.registry_path))
    targets = loader.load_registry()
    console.print(f"[green]Loaded {len(targets)} entries[/]")

    conv_priorities = [Priority(p) for p in config.priorities] if config.priorities else None
    conv_statuses = [CrawlStatus(s) for s in config.only_statuses] if config.only_statuses else None

    selector = CrawlTargetSelector(str(config.output_dir))
    selection = selector.select(
        targets=targets,
        law_ids=config.law_ids,
        tiers=config.tiers,
        groups=config.groups,
        priorities=conv_priorities,
        only_statuses=conv_statuses,
        include_manual_review=config.include_manual_review,
        skip_already_crawled=config.skip_already_crawled,
        dry_run=config.dry_run,
    )

    print_selection_table(selection)

    if config.dry_run:
        console.print("\n[yellow]Dry run complete - no crawling performed[/]")
        return _finalize_crawl_pipeline_result(
            config=config,
            mode="registry",
            started_at=start_time,
            total_targets=len(targets),
            selected_targets=selection.selected_count,
            results=[],
            skips=selector.get_skip_records(),
            success=True,
        )

    if selection.selected_count == 0:
        console.print("\n[yellow]No targets to crawl[/]")
        return _finalize_crawl_pipeline_result(
            config=config,
            mode="registry",
            started_at=start_time,
            total_targets=len(targets),
            selected_targets=0,
            results=[],
            skips=selector.get_skip_records(),
            success=True,
        )

    storage = RawArtifactStore(str(config.output_dir))
    settings = get_settings()
    rate_limiter = RateLimiter(
        delay_seconds=config.delay_seconds or settings.crawler_rate_limit_seconds,
        max_concurrency=min(config.concurrency, 3),
    )
    crawler = ThuvienPhapLuatCrawler(
        rate_limiter=rate_limiter,
        storage=storage,
        max_retries=config.retry or settings.crawler_max_retries,
    )

    semaphore = asyncio.Semaphore(min(config.concurrency, 3))

    async def crawl_with_semaphore(target: Any) -> CrawlResult:
        async with semaphore:
            return await crawler.crawl(target)

    tasks = [crawl_with_semaphore(t) for t in selection.targets]
    results_raw: list[CrawlResult | BaseException] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    crawl_results: list[CrawlResult] = []
    for i, result in enumerate(results_raw):
        if isinstance(result, BaseException):
            crawl_results.append(
                CrawlResult(
                    target=selection.targets[i],
                    success=False,
                    error_message=f"Exception: {result}",
                )
            )
        else:
            crawl_results.append(result)

    print_crawl_summary(crawl_results, selector.get_skip_records(), start_time)
    failures = sum(1 for r in crawl_results if not r.success)
    return _finalize_crawl_pipeline_result(
        config=config,
        mode="registry",
        started_at=start_time,
        total_targets=len(targets),
        selected_targets=selection.selected_count,
        results=crawl_results,
        skips=selector.get_skip_records(),
        success=failures == 0,
    )


def _finalize_crawl_pipeline_result(
    config: CrawlPipelineConfig,
    mode: str,
    started_at: datetime,
    total_targets: int,
    selected_targets: int,
    results: list[CrawlResult],
    skips: list[CrawlSkipRecord],
    success: bool,
) -> CrawlPipelineResult:
    """Build and write the crawl report, then return the pipeline result.

    Args:
        config: Crawl pipeline configuration.
        mode: Crawl mode, either ``registry`` or ``url``.
        started_at: UTC timestamp when the crawl run started.
        total_targets: Number of available crawl targets.
        selected_targets: Number of targets selected for crawling.
        results: Completed crawl results.
        skips: Targets skipped by selection logic.
        success: Whether the pipeline should be considered successful.

    Returns:
        Pipeline result containing crawl outcomes and the generated report.

    Raises:
        OSError: If the configured report path cannot be written.
    """
    finished_at = datetime.now(UTC)
    failure_count = sum(1 for result in results if not result.success)
    if not success and failure_count == 0:
        failure_count = 1
    report = build_crawl_report(
        config=config,
        mode=mode,
        started_at=started_at,
        finished_at=finished_at,
        total_targets=total_targets,
        selected_targets=selected_targets,
        results=results,
        skips=skips,
    )
    report_path = write_crawl_report(config.report_path, report)

    return CrawlPipelineResult(
        success=success,
        failure_count=failure_count,
        results=results,
        skips=skips,
        report_path=report_path,
        report=report,
    )


def build_crawl_report(
    config: CrawlPipelineConfig,
    mode: str,
    started_at: datetime,
    finished_at: datetime,
    total_targets: int,
    selected_targets: int,
    results: list[CrawlResult],
    skips: list[CrawlSkipRecord],
) -> dict[str, Any]:
    """Build a JSON-serializable batch crawl report.

    Args:
        config: Crawl pipeline configuration.
        mode: Crawl mode, either ``registry`` or ``url``.
        started_at: UTC timestamp when the crawl run started.
        finished_at: UTC timestamp when the crawl run finished.
        total_targets: Number of available crawl targets.
        selected_targets: Number of targets selected for crawling.
        results: Completed crawl results.
        skips: Targets skipped by selection logic.

    Returns:
        Report dictionary suitable for JSON serialization.
    """
    successful = sum(1 for result in results if result.success)
    failed = sum(1 for result in results if not result.success)
    report_results = [_crawl_result_to_report_item(config.output_dir, result) for result in results]
    report_results.extend(_skip_record_to_report_item(record) for record in skips)
    warnings = [_skip_record_to_warning(record) for record in skips]
    errors = [_crawl_result_to_error(result) for result in results if not result.success]

    return {
        "run_id": f"crawl-{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "crawler_version": "v1.0.0",
        "registry_path": str(config.registry_path) if config.registry_path else None,
        "raw_dir": str(config.output_dir),
        "mode": mode,
        "total_targets": total_targets,
        "selected_targets": selected_targets,
        "skipped_existing": len(skips),
        "successful": successful,
        "failed": failed,
        "warnings_count": len(warnings),
        "errors_count": len(errors),
        "results": report_results,
        "warnings": warnings,
        "errors": errors,
    }


def write_crawl_report(report_path: Path | None, report: dict[str, Any]) -> Path | None:
    """Write a crawl report to disk.

    Args:
        report_path: Destination path. If ``None``, report writing is skipped.
        report: JSON-serializable report dictionary.

    Returns:
        The written report path, or ``None`` when writing is disabled.

    Raises:
        OSError: If the parent directory or report file cannot be written.
    """
    if report_path is None:
        return None

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    return report_path


def _crawl_result_to_report_item(raw_dir: Path, result: CrawlResult) -> dict[str, Any]:
    latest_dir = raw_dir / result.target.law_id / "latest"
    main_html_path = latest_dir / "main.html"
    metadata_path = latest_dir / "metadata.json"
    metadata = _load_metadata(metadata_path)

    return {
        "law_id": result.target.law_id,
        "name": result.target.name,
        "url": result.target.url,
        "source_domain": result.target.source_domain,
        "status": "success" if result.success else "failed",
        "http_status": result.http_status,
        "output_dir": str(latest_dir) if result.success else None,
        "main_html_path": str(main_html_path) if result.success else None,
        "metadata_path": str(metadata_path) if result.success else None,
        "content_hash": result.content_hash or metadata.get("content_hash"),
        "content_length": len(result.content) if result.content is not None else None,
        "crawled_at": metadata.get("crawled_at"),
        "error": result.error_message,
    }


def _skip_record_to_report_item(record: CrawlSkipRecord) -> dict[str, Any]:
    return {
        "law_id": record.target.law_id,
        "name": record.target.name,
        "url": record.target.url,
        "source_domain": record.target.source_domain,
        "status": "skipped",
        "http_status": None,
        "output_dir": None,
        "main_html_path": None,
        "metadata_path": record.existing_metadata_path,
        "content_hash": record.existing_content_hash,
        "content_length": None,
        "crawled_at": record.existing_crawled_at,
        "error": record.reason,
    }


def _skip_record_to_warning(record: CrawlSkipRecord) -> dict[str, Any]:
    return {
        "law_id": record.target.law_id,
        "reason": record.reason,
        "existing_metadata_path": record.existing_metadata_path,
    }


def _crawl_result_to_error(result: CrawlResult) -> dict[str, Any]:
    return {
        "law_id": result.target.law_id,
        "url": result.target.url,
        "http_status": result.http_status,
        "error": result.error_message,
    }


def _load_metadata(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.exists():
        return {}
    try:
        with metadata_path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}
