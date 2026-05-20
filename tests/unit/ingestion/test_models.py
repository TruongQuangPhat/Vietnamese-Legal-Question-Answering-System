"""Unit tests for ingestion models.

Tests cover:
- CrawlTarget validation
- MetadataSchema contract
- Enum values
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ingestion.models import (
    CrawlStatus,
    CrawlTarget,
    LegalStatus,
    MetadataSchema,
    Priority,
    SourceType,
)


class TestCrawlTarget:
    """Tests for CrawlTarget model."""

    def test_valid_target_minimal(self) -> None:
        """Test creating minimal valid CrawlTarget."""
        target = CrawlTarget(
            law_id="TEST",
            name="Test Law",
            tier=1,
            group="Test Group",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test.aspx",
        )

        assert target.law_id == "TEST"
        assert target.name == "Test Law"
        assert target.tier == 1
        assert target.source_domain == "thuvienphapluat.vn"
        assert target.source_type == SourceType.HTML
        assert target.crawl_status == CrawlStatus.PENDING

    def test_valid_target_full(self) -> None:
        """Test creating full CrawlTarget with all fields."""
        target = CrawlTarget(
            law_id="BLDS_2015",
            name="Bộ luật Dân sự 2015",
            tier=1,
            group="Bộ luật cốt lõi",
            domain_tags=["dân sự", "hợp đồng"],
            status=LegalStatus.ACTIVE,
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test.aspx",
            effective_date="2017-01-01",
            expiry_date=None,
            crawl_status=CrawlStatus.PENDING,
            priority=Priority.CRITICAL,
            notes="Test law",
        )

        assert target.law_id == "BLDS_2015"
        assert target.domain_tags == ["dân sự", "hợp đồng"]
        assert target.status == LegalStatus.ACTIVE
        assert target.effective_date == "2017-01-01"
        assert target.priority == Priority.CRITICAL

    def test_reject_untrusted_domain(self) -> None:
        """Test that untrusted domains are rejected."""
        with pytest.raises(ValidationError, match="thuvienphapluat.vn"):
            CrawlTarget(
                law_id="TEST",
                name="Test",
                tier=1,
                group="Test",
                source_domain="example.com",
                source_type=SourceType.HTML,
                url="https://example.com/test",
            )

    def test_reject_invalid_url_domain(self) -> None:
        """Test that URLs from untrusted domains are rejected."""
        with pytest.raises(ValidationError, match="thuvienphapluat.vn"):
            CrawlTarget(
                law_id="TEST",
                name="Test",
                tier=1,
                group="Test",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.HTML,
                url="https://example.com/test",
            )

    def test_allow_null_url_for_planned(self) -> None:
        """Test that planned entries can have null URL."""
        target = CrawlTarget(
            law_id="PLANNED",
            name="Planned Law",
            tier=2,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.UNKNOWN,
            status=LegalStatus.PLANNED,
            url=None,
            crawl_status=CrawlStatus.MANUAL_REVIEW,
            priority=Priority.LOW,
        )

        assert target.url is None
        assert target.status == LegalStatus.PLANNED

    def test_status_methods(self) -> None:
        """Test status checking methods."""
        pending = CrawlTarget(
            law_id="PENDING",
            name="Pending",
            tier=1,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test.aspx",
            crawl_status=CrawlStatus.PENDING,
            priority=Priority.HIGH,
        )

        crawled = CrawlTarget(
            law_id="CRAWLED",
            name="Crawled",
            tier=1,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test2.aspx",
            crawl_status=CrawlStatus.CRAWLED,
            priority=Priority.HIGH,
        )

        assert pending.is_pending() is True
        assert pending.is_crawled() is False
        assert pending.is_manual_review() is False

        assert crawled.is_pending() is False
        assert crawled.is_crawled() is True
        assert crawled.is_manual_review() is False

    def test_invalid_tier(self) -> None:
        """Test that invalid tier values are rejected."""
        with pytest.raises(ValidationError):
            CrawlTarget(
                law_id="TEST",
                name="Test",
                tier=-1,  # Invalid: negative
                group="Test",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.HTML,
                url="https://thuvienphapluat.vn/test.aspx",
            )

    def test_empty_domain_tags_filtered(self) -> None:
        """Test that empty domain tags are filtered out."""
        target = CrawlTarget(
            law_id="TEST",
            name="Test",
            tier=1,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test.aspx",
            domain_tags=["valid", "", "  ", "also-valid"],
        )

        assert target.domain_tags == ["valid", "also-valid"]


class TestMetadataSchema:
    """Tests for MetadataSchema model."""

    def test_required_fields(self) -> None:
        """Test that required fields must be provided."""
        metadata = MetadataSchema(
            law_id="TEST",
            name="Test Law",
            tier=1,
            source_domain="thuvienphapluat.vn",
            source_type="html",
            url="https://thuvienphapluat.vn/test.aspx",
            crawl_status="success",
            crawled_at="2026-01-01T00:00:00+00:00",
            content_hash="a" * 64,
            crawler_version="v1.0.0",
            parser_hint="test",
        )

        assert metadata.law_id == "TEST"
        assert metadata.crawl_status == "success"

    def test_optional_fields_default(self) -> None:
        """Test optional fields have defaults."""
        metadata = MetadataSchema(
            law_id="TEST",
            name="Test Law",
            tier=1,
            source_domain="thuvienphapluat.vn",
            source_type="html",
            url="https://thuvienphapluat.vn/test.aspx",
            crawl_status="success",
            crawled_at="2026-01-01T00:00:00+00:00",
            content_hash="a" * 64,
            crawler_version="v1.0.0",
            parser_hint="test",
        )

        assert metadata.group is None
        assert metadata.effective_date is None
        assert metadata.expiry_date is None
        assert metadata.attachment_paths == []
        assert metadata.error_message is None
        assert metadata.refresh is False
        assert metadata.previous_content_hash is None

    def test_to_dict_excludes_none(self) -> None:
        """Test that to_dict excludes None values."""
        metadata = MetadataSchema(
            law_id="TEST",
            name="Test Law",
            tier=1,
            source_domain="thuvienphapluat.vn",
            source_type="html",
            url="https://thuvienphapluat.vn/test.aspx",
            crawl_status="success",
            crawled_at="2026-01-01T00:00:00+00:00",
            content_hash="a" * 64,
            crawler_version="v1.0.0",
            parser_hint="test",
            group="Test Group",
        )

        data = metadata.to_dict()

        assert "law_id" in data
        assert "group" in data
        assert "effective_date" not in data  # None, should be excluded


class TestEnums:
    """Tests for enumeration types."""

    def test_crawl_status_values(self) -> None:
        """Test CrawlStatus enum values."""
        assert CrawlStatus.PENDING.value == "pending"
        assert CrawlStatus.CRAWLED.value == "crawled"
        assert CrawlStatus.FAILED.value == "failed"
        assert CrawlStatus.MANUAL_REVIEW.value == "manual_review"

    def test_source_type_values(self) -> None:
        """Test SourceType enum values."""
        assert SourceType.HTML.value == "html"
        assert SourceType.PDF.value == "pdf"
        assert SourceType.DOC.value == "doc"
        assert SourceType.DOCX.value == "docx"
        assert SourceType.MIXED.value == "mixed"

    def test_priority_values(self) -> None:
        """Test Priority enum values."""
        assert Priority.CRITICAL.value == "critical"
        assert Priority.HIGH.value == "high"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.LOW.value == "low"

    def test_legal_status_values(self) -> None:
        """Test LegalStatus enum values."""
        assert LegalStatus.ACTIVE.value == "active"
        assert LegalStatus.PLANNED.value == "planned"
        assert LegalStatus.INACTIVE.value == "inactive"
