"""CLI entry point for the legal document crawler.

This module provides the command-line interface for:
- Batch crawling from registry
- Single URL debug crawling
- Target selection with filters
- Dry-run mode
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import structlog
from rich.console import Console
from rich.table import Table

from src.core.config import get_settings
from src.core.exceptions import RegistryError, TrustedDomainError
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

logger = structlog.get_logger(__name__)
console = Console()


def print_selection_table(selection: CrawlSelection) -> None:
    """Print selection details in a table format.

    Args:
        selection: The crawl selection to print.
    """
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


def print_skip_table(skips: list[CrawlSkipRecord]) -> None:
    """Print skip details in a table format.

    Args:
        skips: List of skip records to print.
    """
    if not skips:
        console.print("[green]No targets skipped.[/]")
        return

    table = Table(
        title=f"Skipped {len(skips)} targets",
        show_header=True,
        header_style="bold yellow",
    )

    table.add_column("Law ID", style="cyan")
    table.add_column("Reason", max_width=60)
    table.add_column("Previous Hash", max_width=20)

    for record in skips:
        prev_hash = (
            record.existing_content_hash[:16] + "..." if record.existing_content_hash else "N/A"
        )
        table.add_row(
            record.target.law_id,
            record.reason[:60] + "..." if len(record.reason) > 60 else record.reason,
            prev_hash,
        )

    console.print(table)


def print_crawl_summary(
    results: list[CrawlResult],
    skips: list[CrawlSkipRecord],
    start_time: datetime,
) -> None:
    """Print crawl execution summary.

    Args:
        results: List of crawl results.
        skips: List of skip records.
        start_time: Start time of crawl.
    """
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


async def run_batch_crawl(
    targets: list[Any],
    storage: RawArtifactStore,
    concurrency: int,
    dry_run: bool = False,
) -> tuple[list[CrawlResult], list[CrawlSkipRecord]]:
    """Run batch crawl with concurrency control.

    Args:
        targets: List of targets to crawl.
        storage: Raw artifact storage instance.
        concurrency: Maximum concurrent crawls.
        dry_run: If True, do not perform actual crawling.

    Returns:
        Tuple of (results, skip_records).
    """

    settings = get_settings()
    rate_limiter = RateLimiter(
        delay_seconds=settings.crawler_rate_limit_seconds,
        max_concurrency=min(concurrency, 3),
    )
    crawler = ThuvienPhapLuatCrawler(
        rate_limiter=rate_limiter,
        storage=storage,
    )

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)

    async def crawl_with_semaphore(target: Any) -> CrawlResult:
        """Crawl a single target with semaphore control."""
        async with semaphore:
            return await crawler.crawl(target)

    if dry_run:
        console.print("[yellow]Dry run mode - no actual crawling will occur[/]")
        return [], []

    # Create tasks
    tasks = [crawl_with_semaphore(t) for t in targets]

    # Run with concurrency limit using gather
    results: list[CrawlResult | BaseException] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    # Process results
    crawl_results: list[CrawlResult] = []
    skip_records: list[CrawlSkipRecord] = []

    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            # Convert exception to failed result
            crawl_results.append(
                CrawlResult(
                    target=targets[i],
                    success=False,
                    error_message=f"Exception: {result}",
                )
            )
        else:
            crawl_results.append(result)

    return crawl_results, skip_records


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point.

    Args:
        argv: Command line arguments. If None, uses sys.argv.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    import argparse

    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="python -m src.ingestion.cli",
        description="Registry-Driven Legal Document Crawler for VnLaw-QA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Batch crawl all pending
  python -m src.ingestion.cli --registry config/laws/corpus_registry.yml --output data/raw --only-status pending

  # Crawl specific laws
  python -m src.ingestion.cli --registry config/laws/corpus_registry.yml --law-ids BLDS_2015 HP_2013 --output data/raw

  # Crawl by tier
  python -m src.ingestion.cli --registry config/laws/corpus_registry.yml --tier 1 --output data/raw

  # Debug single URL
  python -m src.ingestion.cli --url "https://thuvienphapluat.vn/..." --law-id "BLDS_2015" --output data/raw

  # Dry run
  python -m src.ingestion.cli --registry config/laws/corpus_registry.yml --only-status pending --dry-run

  # Force refresh
  python -m src.ingestion.cli --registry config/laws/corpus_registry.yml --law-ids LDD_VBHN --force --output data/raw
        """,
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--registry",
        type=str,
        help="Path to corpus_registry.yml for batch crawling",
    )
    mode_group.add_argument(
        "--url",
        type=str,
        help="Single URL for debug crawling (requires --law-id)",
    )

    # Registry-based selection options (composable)
    parser.add_argument(
        "--law-ids",
        nargs="+",
        type=str,
        help="Filter by specific law IDs (registry mode only)",
    )
    parser.add_argument(
        "--tier",
        type=int,
        action="append",
        dest="tiers",
        help="Filter by tier (can repeat)",
    )
    parser.add_argument(
        "--group",
        type=str,
        action="append",
        dest="groups",
        help="Filter by group name (can repeat)",
    )
    parser.add_argument(
        "--priority",
        type=str,
        action="append",
        dest="priorities",
        choices=["critical", "high", "medium", "low"],
        help="Filter by priority (can repeat)",
    )
    parser.add_argument(
        "--only-status",
        type=str,
        action="append",
        dest="only_statuses",
        choices=[s.value for s in CrawlStatus],
        help="Filter by crawl status (can repeat)",
    )
    parser.add_argument(
        "--include-manual-review",
        action="store_true",
        help="Include manual_review entries (default: skip)",
    )
    parser.add_argument(
        "--no-skip-crawled",
        action="store_false",
        dest="skip_already_crawled",
        help="Don't skip already crawled entries",
    )

    # Debug mode
    parser.add_argument(
        "--law-id",
        type=str,
        help="Law ID for single URL debug mode",
    )

    # Behavior options
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-crawl, backup existing artifacts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selection without crawling",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Maximum concurrent crawls (default: 2, max: 3)",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=None,
        help="Delay between requests per host (default: 2.0)",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=None,
        help="Maximum retry attempts (default: 3)",
    )

    # Output
    parser.add_argument(
        "--output",
        type=str,
        default="data/raw",
        help="Output directory for raw artifacts (default: data/raw)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    # Validate debug mode
    if args.url and not args.law_id:
        console.print("[red]Error: --law-id is required when using --url[/]")
        return 1

    # Set up logging
    settings = get_settings()
    log_level = "DEBUG" if args.verbose else settings.log_level

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    try:
        if args.url:
            # Single URL debug mode
            return asyncio.run(crawl_single_url(args))
        else:
            # Registry-based batch mode
            return asyncio.run(crawl_from_registry(args))

    except RegistryError as e:
        console.print(f"[red]Registry Error:[/] {e}")
        return 1

    except TrustedDomainError as e:
        console.print(f"[red]Domain Validation Error:[/] {e}")
        return 1

    except KeyboardInterrupt:
        console.print("\n[yellow]Crawl interrupted by user[/]")
        return 130

    except Exception as e:
        console.print(f"[red]Unexpected error:[/] {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="python -m src.ingestion.cli",
        description="Registry-Driven Legal Document Crawler for VnLaw-QA",
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--registry",
        type=str,
        help="Path to corpus_registry.yml for batch crawling",
    )
    mode_group.add_argument(
        "--url",
        type=str,
        help="Single URL for debug crawling (requires --law-id)",
    )

    # Registry-based selection options (composable)
    parser.add_argument(
        "--law-ids",
        nargs="+",
        type=str,
        help="Filter by specific law IDs (registry mode only)",
    )
    parser.add_argument(
        "--tier",
        type=int,
        action="append",
        dest="tiers",
        help="Filter by tier (can repeat)",
    )
    parser.add_argument(
        "--group",
        type=str,
        action="append",
        dest="groups",
        help="Filter by group name (can repeat)",
    )
    parser.add_argument(
        "--priority",
        type=str,
        action="append",
        dest="priorities",
        choices=["critical", "high", "medium", "low"],
        help="Filter by priority (can repeat)",
    )
    parser.add_argument(
        "--only-status",
        type=str,
        action="append",
        dest="only_statuses",
        choices=[s.value for s in CrawlStatus],
        help="Filter by crawl status (can repeat)",
    )
    parser.add_argument(
        "--include-manual-review",
        action="store_true",
        help="Include manual_review entries (default: skip)",
    )
    parser.add_argument(
        "--no-skip-crawled",
        action="store_false",
        dest="skip_already_crawled",
        help="Don't skip already crawled entries",
    )

    # Debug mode
    parser.add_argument(
        "--law-id",
        type=str,
        help="Law ID for single URL debug mode",
    )

    # Behavior options
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-crawl, backup existing artifacts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selection without crawling",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Maximum concurrent crawls (default: 2, max: 3)",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=None,
        help="Delay between requests per host (default: 2.0)",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=None,
        help="Maximum retry attempts (default: 3)",
    )

    # Output
    parser.add_argument(
        "--output",
        type=str,
        default="data/raw",
        help="Output directory for raw artifacts (default: data/raw)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args(argv)


async def crawl_single_url(args: argparse.Namespace) -> int:
    """Crawl a single URL for debugging.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    console.print("[cyan]Debug crawl mode[/]")
    console.print(f"  URL: {args.url}")
    console.print(f"  Law ID: {args.law_id}")

    # Validate URL domain
    settings = get_settings()

    parsed = urlparse(args.url)
    hostname = parsed.hostname

    if not hostname or settings.trusted_domain not in hostname:
        console.print(f"[red]Error: URL must be from {settings.trusted_domain}[/]")
        return 1

    # Set up components
    storage = RawArtifactStore(args.output)
    rate_limiter = RateLimiter(
        delay_seconds=args.delay_seconds or settings.crawler_rate_limit_seconds,
        max_concurrency=1,
    )
    crawler = ThuvienPhapLuatCrawler(
        rate_limiter=rate_limiter,
        storage=storage,
        max_retries=args.retry or settings.crawler_max_retries,
    )

    target = CrawlTarget(
        law_id=args.law_id,
        name=args.law_id,
        tier=0,
        group="debug",
        source_domain=settings.trusted_domain,
        source_type=SourceType.HTML,
        url=args.url,
        crawl_status=CrawlStatus.PENDING,
        priority=Priority.HIGH,
        effective_date=None,
        expiry_date=None,
        notes=None,
    )

    # Crawl
    console.print("\n[cyan]Starting crawl...[/]")
    result = await crawler.crawl(target)

    if result.success:
        console.print("[green]Success![/]")
        content_hash_display = result.content_hash[:32] + "..." if result.content_hash else "N/A"
        console.print(f"  Content hash: {content_hash_display}")
        console.print(f"  Duration: {result.duration_seconds:.2f}s")
        if result.http_status:
            console.print(f"  HTTP Status: {result.http_status}")
        return 0
    else:
        console.print(f"[red]Failed:[/] {result.error_message}")
        return 1


async def crawl_from_registry(args: argparse.Namespace) -> int:
    """Crawl from registry in batch mode.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    start_time = datetime.now(UTC)

    console.print("[cyan]Registry crawl mode[/]")
    console.print(f"  Registry: {args.registry}")
    console.print(f"  Output: {args.output}")

    # Load registry
    console.print("\n[cyan]Loading registry...[/]")
    loader = CorpusRegistryLoader(args.registry)
    targets = loader.load_registry()
    console.print(f"[green]Loaded {len(targets)} entries[/]")

    # Convert priority strings to enums
    priorities = None
    if args.priorities:
        priorities = [Priority(p) for p in args.priorities]

    # Convert status strings to enums
    only_statuses = None
    if args.only_statuses:
        only_statuses = [CrawlStatus(s) for s in args.only_statuses]

    # Select targets
    console.print("\n[cyan]Selecting targets...[/]")
    selector = CrawlTargetSelector(args.output)

    selection = selector.select(
        targets=targets,
        law_ids=args.law_ids,
        tiers=args.tiers,
        groups=args.groups,
        priorities=priorities,
        only_statuses=only_statuses,
        include_manual_review=args.include_manual_review,
        skip_already_crawled=args.skip_already_crawled,
        dry_run=args.dry_run,
    )

    # Print selection
    print_selection_table(selection)

    if args.dry_run:
        console.print("\n[yellow]Dry run complete - no crawling performed[/]")
        return 0

    if selection.selected_count == 0:
        console.print("\n[yellow]No targets to crawl[/]")
        return 0

    # Set up storage
    storage = RawArtifactStore(args.output)

    # Run batch crawl
    console.print("\n[cyan]Starting batch crawl...[/]")

    settings = get_settings()
    rate_limiter = RateLimiter(
        delay_seconds=args.delay_seconds or settings.crawler_rate_limit_seconds,
        max_concurrency=min(args.concurrency, 3),
    )
    crawler = ThuvienPhapLuatCrawler(
        rate_limiter=rate_limiter,
        storage=storage,
        max_retries=args.retry or settings.crawler_max_retries,
    )

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(min(args.concurrency, 3))

    async def crawl_with_semaphore(target: Any) -> CrawlResult:
        async with semaphore:
            return await crawler.crawl(target)

    tasks = [crawl_with_semaphore(t) for t in selection.targets]
    results_raw: list[CrawlResult | BaseException] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    # Process results
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

    # Print summary
    print_crawl_summary(crawl_results, selector.get_skip_records(), start_time)

    # Return non-zero if any failures
    failures = sum(1 for r in crawl_results if not r.success)
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
