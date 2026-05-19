"""Unit tests for the crawl target selector.

Tests cover:
- Selecting pending entries
- Selecting by law_ids, tier, group, priority
- Skipping already crawled entries
- Dry-run mode
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ingestion.models import (
    CrawlStatus,
    CrawlTarget,
    LegalStatus,
    Priority,
    SourceType,
)
from src.ingestion.selector import CrawlTargetSelector


class TestCrawlTargetSelector:
    """Tests for CrawlTargetSelector class."""

    @pytest.fixture
    def sample_targets(self) -> list[CrawlTarget]:
        """Create sample crawl targets for testing."""
        return [
            CrawlTarget(
                law_id="LAW1",
                name="Law 1",
                tier=1,
                group="Group A",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.HTML,
                url="https://thuvienphapluat.vn/law1.aspx",
                crawl_status=CrawlStatus.PENDING,
                priority=Priority.CRITICAL,
                status=LegalStatus.ACTIVE,
            ),
            CrawlTarget(
                law_id="LAW2",
                name="Law 2",
                tier=1,
                group="Group B",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.HTML,
                url="https://thuvienphapluat.vn/law2.aspx",
                crawl_status=CrawlStatus.PENDING,
                priority=Priority.HIGH,
                status=LegalStatus.ACTIVE,
            ),
            CrawlTarget(
                law_id="LAW3",
                name="Law 3",
                tier=2,
                group="Group A",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.PDF,
                url="https://thuvienphapluat.vn/law3.pdf",
                crawl_status=CrawlStatus.CRAWLED,
                priority=Priority.MEDIUM,
                status=LegalStatus.ACTIVE,
            ),
            CrawlTarget(
                law_id="LAW4",
                name="Law 4",
                tier=2,
                group="Group C",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.HTML,
                url="https://thuvienphapluat.vn/law4.aspx",
                crawl_status=CrawlStatus.MANUAL_REVIEW,
                priority=Priority.LOW,
                status=LegalStatus.PLANNED,
            ),
        ]

    @pytest.fixture
    def selector(self, tmp_path: Path) -> CrawlTargetSelector:
        """Create a selector with temporary output directory."""
        return CrawlTargetSelector(tmp_path)

    def test_select_all_when_no_filters(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test selecting all targets when no filters applied."""
        selection = selector.select(
            targets=sample_targets,
            skip_already_crawled=False,
            include_manual_review=True,
        )

        assert selection.selected_count == 4
        assert selection.total_available == 4

    def test_select_pending_only(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test selecting only pending entries."""
        selection = selector.select(
            targets=sample_targets,
            only_statuses=[CrawlStatus.PENDING],
            include_manual_review=True,
        )

        assert selection.selected_count == 2
        assert all(t.crawl_status == CrawlStatus.PENDING for t in selection.targets)

    def test_select_by_law_ids(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test selecting by specific law IDs."""
        selection = selector.select(
            targets=sample_targets,
            law_ids=["LAW1", "LAW3"],
            skip_already_crawled=False,
            include_manual_review=True,
        )

        assert selection.selected_count == 2
        assert {t.law_id for t in selection.targets} == {"LAW1", "LAW3"}

    def test_select_by_tier(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test selecting by tier."""
        selection = selector.select(
            targets=sample_targets,
            tiers=[2],
            skip_already_crawled=False,
            include_manual_review=True,
        )

        assert selection.selected_count == 2
        assert all(t.tier == 2 for t in selection.targets)

    def test_select_by_group(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test selecting by group."""
        selection = selector.select(
            targets=sample_targets,
            groups=["Group A"],
            skip_already_crawled=False,
            include_manual_review=True,
        )

        assert selection.selected_count == 2
        assert all(t.group == "Group A" for t in selection.targets)

    def test_select_by_priority(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test selecting by priority."""
        selection = selector.select(
            targets=sample_targets,
            priorities=[Priority.CRITICAL, Priority.HIGH],
            skip_already_crawled=False,
            include_manual_review=True,
        )

        assert selection.selected_count == 2
        assert {t.priority for t in selection.targets} == {
            Priority.CRITICAL,
            Priority.HIGH,
        }

    def test_skip_manual_review_by_default(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test that manual_review entries are skipped by default."""
        selection = selector.select(
            targets=sample_targets,
            skip_already_crawled=False,
            include_manual_review=False,  # Default
        )

        assert selection.selected_count == 3
        assert not any(t.crawl_status == CrawlStatus.MANUAL_REVIEW for t in selection.targets)

        # Check skip record
        manual_skips = [s for s in selector.get_skip_records() if s.target.law_id == "LAW4"]
        assert len(manual_skips) == 1

    def test_include_manual_review_when_flagged(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test including manual_review with explicit flag."""
        selection = selector.select(
            targets=sample_targets,
            skip_already_crawled=False,
            include_manual_review=True,
        )

        assert selection.selected_count == 4
        assert any(t.law_id == "LAW4" for t in selection.targets)

    def test_skip_already_crawled_by_registry_status(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test that registry crawl status alone doesn't skip without disk metadata.

        Per requirements, disk metadata is the primary source for skip detection.
        Registry status is only used as an additional signal when disk metadata exists.
        """
        # Create disk metadata for LAW3 to match registry status
        law3_dir = selector.output_dir / "LAW3" / "latest"
        law3_dir.mkdir(parents=True)

        metadata = {
            "law_id": "LAW3",
            "name": "Law 3",
            "tier": 2,
            "source_domain": "thuvienphapluat.vn",
            "source_type": "pdf",
            "url": "https://thuvienphapluat.vn/law3.pdf",
            "crawl_status": "success",
            "crawled_at": "2026-01-01T00:00:00+00:00",
            "content_hash": "def456",
            "crawler_version": "v1",
            "parser_hint": "test",
        }

        with open(law3_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

        # Create expected artifact for PDF
        attachments_dir = law3_dir / "attachments"
        attachments_dir.mkdir()
        (attachments_dir / "document.pdf").write_bytes(b"%PDF test")

        selection = selector.select(
            targets=sample_targets,
            skip_already_crawled=True,
            include_manual_review=True,
        )

        # LAW3 should now be skipped (both registry and disk agree)
        assert selection.selected_count == 3
        assert not any(t.law_id == "LAW3" for t in selection.targets)

    def test_skip_already_crawled_by_metadata(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test skipping entries with existing metadata.json."""
        # Create metadata for LAW1
        law1_dir = selector.output_dir / "LAW1" / "latest"
        law1_dir.mkdir(parents=True)

        metadata = {
            "law_id": "LAW1",
            "name": "Law 1",
            "tier": 1,
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/law1.aspx",
            "crawl_status": "success",
            "crawled_at": "2026-01-01T00:00:00+00:00",
            "content_hash": "abc123",
            "crawler_version": "v1",
            "parser_hint": "test",
        }

        with open(law1_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

        # Create main.html
        (law1_dir / "main.html").write_text("<html></html>")

        selection = selector.select(
            targets=sample_targets,
            skip_already_crawled=True,
            include_manual_review=True,
        )

        # LAW1 should be skipped due to existing metadata
        assert selection.selected_count == 3
        assert not any(t.law_id == "LAW1" for t in selection.targets)

        # Check skip record has metadata path
        skip_records = selector.get_skip_records()
        law1_skips = [s for s in skip_records if s.target.law_id == "LAW1"]
        assert len(law1_skips) == 1
        assert law1_skips[0].existing_metadata_path is not None

    def test_dry_run_no_side_effects(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test that dry run doesn't perform side effects."""
        selection = selector.select(
            targets=sample_targets,
            dry_run=True,
            skip_already_crawled=True,
            include_manual_review=True,
        )

        assert selection.dry_run is True
        # Dry run still filters but doesn't check disk
        assert selection.selected_count == 4

    def test_composable_filters(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
    ) -> None:
        """Test combining multiple filters."""
        selection = selector.select(
            targets=sample_targets,
            tiers=[2],
            only_statuses=[CrawlStatus.PENDING],
            priorities=[Priority.HIGH],
            skip_already_crawled=False,
            include_manual_review=True,
        )

        # LAW2 is tier 1, LAW3 is tier 2 but crawled, LAW4 is manual_review
        # No target matches all criteria, so should be 0
        assert selection.selected_count == 0

    def test_dry_run_selection_output(
        self,
        selector: CrawlTargetSelector,
        sample_targets: list[CrawlTarget],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test dry run prints selection summary."""
        selection = selector.select(
            targets=sample_targets,
            dry_run=True,
            skip_already_crawled=False,
            include_manual_review=True,
        )

        # Print summary to stdout
        selector.print_selection_summary(selection)
        captured = capsys.readouterr()

        assert "CRAWL SELECTION SUMMARY" in captured.out
        assert "Total targets in registry: 4" in captured.out
        assert "Selected for crawl:        4" in captured.out
