#!/usr/bin/env python3
"""Raw legal corpus crawling CLI.

Usage:
    uv run python scripts/crawl_raw_corpus.py \
      --registry configs/laws/corpus_registry.yml \
      --output data/raw \
      --only-status pending
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog
from rich.console import Console
from src.services.crawl_service import run_crawl_pipeline, CrawlPipelineConfig

console = Console()

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/crawl_raw_corpus.py",
        description="Registry-Driven Legal Document Crawler for VnLaw-QA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Batch crawl all pending
  uv run python scripts/crawl_raw_corpus.py --registry configs/laws/corpus_registry.yml --output data/raw --only-status pending

  # Crawl specific laws
  uv run python scripts/crawl_raw_corpus.py --registry configs/laws/corpus_registry.yml --law-ids BLDS_2015 HP_2013 --output data/raw

  # Crawl by tier
  uv run python scripts/crawl_raw_corpus.py --registry configs/laws/corpus_registry.yml --tier 1 --output data/raw

  # Debug single URL
  uv run python scripts/crawl_raw_corpus.py --url "https://thuvienphapluat.vn/..." --law-id "BLDS_2015" --output data/raw

  # Dry run
  uv run python scripts/crawl_raw_corpus.py --registry configs/laws/corpus_registry.yml --only-status pending --dry-run

  # Force refresh
  uv run python scripts/crawl_raw_corpus.py --registry configs/laws/corpus_registry.yml --law-ids LDD_VBHN --force --output data/raw
        """
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

    # Registry-based selection options
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
        choices=["pending", "crawling", "crawled", "parsed", "ingested", "verified", "failed", "manual_review"],
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

    args = parser.parse_args()

    if args.url and not args.law_id:
        console.print("[red]Error: --law-id is required when using --url[/]")
        return 1

    # Set up logging
    from src.core.config import get_settings
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
        # Construct pipeline config from args
        config = CrawlPipelineConfig(
            output_dir=Path(args.output),
            registry_path=Path(args.registry) if args.registry else None,
            url=args.url,
            law_id=args.law_id,
            law_ids=args.law_ids,
            tiers=args.tiers,
            groups=args.groups,
            priorities=args.priorities,
            only_statuses=args.only_statuses,
            include_manual_review=args.include_manual_review,
            skip_already_crawled=args.skip_already_crawled,
            force=args.force,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
            delay_seconds=args.delay_seconds,
            retry=args.retry,
            verbose=args.verbose,
        )

        result = asyncio.run(run_crawl_pipeline(config))
        return 0 if result.success else 1

    except Exception as e:
        console.print(f"[red]Unexpected error:[/] {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
