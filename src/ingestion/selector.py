"""Crawl target selector with filtering capabilities.

This module provides functionality to:
- Select crawl targets based on various filters
- Skip already-crawled targets
- Handle dry-run mode
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.models import (
    CrawlSelection,
    CrawlSkipRecord,
    CrawlStatus,
    CrawlTarget,
    Priority,
)

if TYPE_CHECKING:
    from src.ingestion.models import CrawlTarget


class CrawlTargetSelector:
    """Selects crawl targets based on filters and skip rules.

    This class applies filters to a list of CrawlTarget objects and
    determines which targets should be crawled based on:
    - Explicit law_ids
    - Tier
    - Group
    - Priority
    - Crawl status
    - Manual review flag
    - Skip already-crawled

    Attributes:
        output_dir: Path to the output directory for raw artifacts.
    """

    def __init__(self, output_dir: str | Path):
        """Initialize the target selector.

        Args:
            output_dir: Path to the output directory for raw artifacts.
        """
        self.output_dir = Path(output_dir)
        self._skip_records: list[CrawlSkipRecord] = []

    def select(
        self,
        targets: list[CrawlTarget],
        law_ids: list[str] | None = None,
        tiers: list[int] | None = None,
        groups: list[str] | None = None,
        priorities: list[Priority] | None = None,
        only_statuses: list[CrawlStatus] | None = None,
        include_manual_review: bool = False,
        skip_already_crawled: bool = True,
        dry_run: bool = False,
    ) -> CrawlSelection:
        """Select crawl targets based on filters.

        Applies filters in the following order:
        1. Filter by law_ids (if specified)
        2. Filter by tiers (if specified)
        3. Filter by groups (if specified)
        4. Filter by priorities (if specified)
        5. Filter by crawl statuses (if specified)
        6. Skip manual_review (unless include_manual_review is True)
        7. Skip already-crawled (if skip_already_crawled is True)

        Args:
            targets: List of all CrawlTarget objects.
            law_ids: Filter by specific law IDs.
            tiers: Filter by tier numbers.
            groups: Filter by group names.
            priorities: Filter by priority levels.
            only_statuses: Filter by specific crawl statuses.
            include_manual_review: Include manual_review targets.
            skip_already_crawled: Skip targets that have been crawled.
            dry_run: If True, do not perform file system checks.

        Returns:
            CrawlSelection containing selected targets and skip records.
        """
        self._skip_records = []
        selected = targets.copy()

        # Apply filters
        if law_ids:
            selected = [t for t in selected if t.law_id in law_ids]

        if tiers:
            selected = [t for t in selected if t.tier in tiers]

        if groups:
            selected = [t for t in selected if t.group in groups]

        if priorities:
            selected = [t for t in selected if t.priority in priorities]

        if only_statuses:
            selected = [t for t in selected if t.crawl_status in only_statuses]

        # Skip manual_review unless explicitly included
        if not include_manual_review:
            manual_review_count = sum(
                1 for t in selected
                if t.crawl_status == CrawlStatus.MANUAL_REVIEW
            )
            if manual_review_count > 0:
                skipped = [
                    t for t in selected
                    if t.crawl_status == CrawlStatus.MANUAL_REVIEW
                ]
                selected = [
                    t for t in selected
                    if t.crawl_status != CrawlStatus.MANUAL_REVIEW
                ]
                for target in skipped:
                    self._skip_records.append(CrawlSkipRecord(
                        target=target,
                        reason="manual_review status and --include-manual-review not specified",
                    ))

        # Skip already-crawled
        if skip_already_crawled:
            selected = self._skip_crawled_targets(selected, dry_run)

        return CrawlSelection(
            targets=selected,
            total_available=len(targets),
            selected_count=len(selected),
            skipped_count=len(self._skip_records),
            skip_reasons=self._count_skip_reasons(),
            dry_run=dry_run,
        )

    def _skip_crawled_targets(
        self,
        targets: list[CrawlTarget],
        dry_run: bool,
    ) -> list[CrawlTarget]:
        """Skip targets that have already been crawled.

        A target is considered already crawled if disk metadata confirms success:
        - data/raw/{law_id}/latest/metadata.json exists
        - crawl_status in metadata is "success"
        - content_hash exists in metadata
        - Expected raw artifact (main.html or attachment) exists

        Registry crawl_status is used as an additional signal, but disk metadata
        is the primary source of truth.

        Args:
            targets: List of CrawlTarget objects.
            dry_run: If True, do not perform file system checks.

        Returns:
            Filtered list of targets that have not been crawled.
        """
        crawled_statuses = {
            CrawlStatus.CRAWLED,
            CrawlStatus.PARSED,
            CrawlStatus.INGESTED,
            CrawlStatus.VERIFIED,
        }

        selected = []
        for target in targets:
            metadata_path = self.output_dir / target.law_id / "latest" / "metadata.json"

            # Check disk metadata first (primary source)
            if not dry_run and metadata_path.exists():
                try:
                    with open(metadata_path, encoding="utf-8") as f:
                        metadata = json.load(f)

                    if (
                        metadata.get("crawl_status") == "success"
                        and metadata.get("content_hash")
                        and self._has_expected_artifact(target)
                    ):
                        self._skip_records.append(CrawlSkipRecord(
                            target=target,
                            reason="Already crawled successfully (verified by metadata.json)",
                            existing_metadata_path=str(metadata_path),
                            existing_crawled_at=metadata.get("crawled_at"),
                            existing_content_hash=metadata.get("content_hash"),
                        ))
                        continue
                except (json.JSONDecodeError, OSError):
                    # If we can't read metadata, check registry status as fallback
                    pass

            # Fallback: check registry crawl_status if no disk metadata
            if target.crawl_status in crawled_statuses:
                # Registry says crawled but no disk metadata - proceed with crawl
                # (registry may be out of sync)
                pass

            selected.append(target)

        return selected

    def _has_expected_artifact(self, target: CrawlTarget) -> bool:
        """Check if expected raw artifact exists.

        Args:
            target: CrawlTarget to check.

        Returns:
            True if the expected artifact exists.
        """
        law_dir = self.output_dir / target.law_id / "latest"

        if not law_dir.exists():
            return False

        if target.source_type in {"html", "mixed"}:
            return (law_dir / "main.html").exists()

        # For PDF/DOC/DOCX, check for attachments
        attachments_dir = law_dir / "attachments"
        if attachments_dir.exists():
            return any(attachments_dir.iterdir())

        return True

    def _count_skip_reasons(self) -> dict[str, int]:
        """Count skip records by reason.

        Returns:
            Dictionary mapping skip reasons to counts.
        """
        reasons: dict[str, int] = {}
        for record in self._skip_records:
            reason = record.reason
            reasons[reason] = reasons.get(reason, 0) + 1
        return reasons

    def get_skip_records(self) -> list[CrawlSkipRecord]:
        """Get all skip records from the last selection.

        Returns:
            List of CrawlSkipRecord objects.
        """
        return self._skip_records.copy()

    def print_selection_summary(self, selection: CrawlSelection) -> None:
        """Print a summary of the crawl selection.

        Args:
            selection: The CrawlSelection to summarize.
        """
        print("\n" + "=" * 60)
        print("CRAWL SELECTION SUMMARY")
        print("=" * 60)
        print(f"Total targets in registry: {selection.total_available}")
        print(f"Selected for crawl:        {selection.selected_count}")
        print(f"Skipped:                   {selection.skipped_count}")

        if selection.skip_reasons:
            print("\nSkip reasons:")
            for reason, count in selection.skip_reasons.items():
                print(f"  - {reason}: {count}")

        if selection.targets:
            print("\nSelected targets:")
            print("-" * 60)
            for target in selection.targets:
                print(f"  {target.law_id:20} | {target.name[:30]:30} | {str(target.priority):8} | {target.url}")
            print("-" * 60)

        if selection.skipped_count > 0:
            print("\nSkipped targets:")
            print("-" * 60)
            for record in self._skip_records:
                print(f"  {record.target.law_id:20} | {record.reason[:50]:50}")
            print("-" * 60)

        print("=" * 60)
