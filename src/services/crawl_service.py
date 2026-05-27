"""Crawl pipeline service.

This module orchestrates the legal document crawling phase, coordinating the
registry, selector, crawler, and storage components.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

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
    registry_path: Optional[Path] = None
    url: Optional[str] = None
    law_id: Optional[str] = None
    law_ids: Optional[list[str]] = None
    tiers: Optional[list[int]] = None
    groups: Optional[list[str]] = None
    priorities: Optional[list[str]] = None
    only_statuses: Optional[list[str]] = None
    include_manual_review: bool = False
    skip_already_crawled: bool = True
    force: bool = False
    dry_run: bool = False
    concurrency: int = 2
    delay_seconds: Optional[float] = None
    retry: Optional[int] = None
    verbose: bool = False

@dataclass
class CrawlPipelineResult:
    """Result of a crawl pipeline execution."""
    success: bool
    failure_count: int
    results: list[CrawlResult]
    skips: list[CrawlSkipRecord]

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
        return CrawlPipelineResult(False, 1, [], [])

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
        return CrawlPipelineResult(True, 0, [result], [])
    else:
        console.print(f"[red]Failed:[/] {result.error_message}")
        return CrawlPipelineResult(False, 1, [result], [])

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
        return CrawlPipelineResult(True, 0, [], selector.get_skip_records())

    if selection.selected_count == 0:
        console.print("\n[yellow]No targets to crawl[/]")
        return CrawlPipelineResult(True, 0, [], [])

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
    return CrawlPipelineResult(failures == 0, failures, crawl_results, selector.get_skip_records())
