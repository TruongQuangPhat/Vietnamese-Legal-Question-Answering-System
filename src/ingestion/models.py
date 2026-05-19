"""Pydantic models for ingestion data structures.

This module defines Pydantic V2 models for:
- CrawlTarget: Validated registry entry
- CrawlResult: Success/failure outcome
- CrawlSelection: Batch selection summary
- CrawlSkipRecord: Skip reason and metadata
- MetadataSchema: metadata.json contract
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class LegalStatus(StrEnum):
    """Legal document status values."""

    ACTIVE = "active"
    PLANNED = "planned"
    INACTIVE = "inactive"
    AMENDED = "amended"
    REPLACED = "replaced"


class CrawlStatus(StrEnum):
    """Crawl state values."""

    PENDING = "pending"
    CRAWLING = "crawling"
    CRAWLED = "crawled"
    PARSED = "parsed"
    INGESTED = "ingested"
    VERIFIED = "verified"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class SourceType(StrEnum):
    """Source type values."""

    HTML = "html"
    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Priority(StrEnum):
    """Priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CrawlTarget(BaseModel):
    """Validated registry entry for a legal document.

    Attributes:
        law_id: Unique identifier for the law (e.g., "BLDS_2015", "LDD_VBHN").
        name: Official name of the legal document.
        tier: Legal hierarchy tier (0 = Constitution, 1 = Core Codes, 2 = Laws).
        group: Logical grouping for organization.
        domain_tags: List of topic tags for search/discovery.
        status: Legal document status (active/planned/inactive/amended/replaced).
        source_domain: Expected domain (must be thuvienphapluat.vn).
        source_type: Type of source content (html/pdf/doc/docx/mixed/unknown).
        url: URL to crawl (null for planned entries).
        effective_date: Date when the law became effective.
        expiry_date: Date when the law expired (null if still active).
        crawl_status: Current crawl state (pending/crawled/failed/etc.).
        priority: Priority level for crawl scheduling.
        notes: Optional notes or comments.
    """

    law_id: str = Field(..., description="Unique identifier for the law")
    name: str = Field(..., description="Official name of the legal document")
    tier: int = Field(..., ge=0, description="Legal hierarchy tier")
    group: str = Field(..., description="Logical grouping")
    domain_tags: list[str] = Field(default_factory=list, description="Topic tags")
    status: LegalStatus = Field(default=LegalStatus.ACTIVE, description="Legal document status")
    source_domain: str = Field(..., description="Expected source domain")
    source_type: SourceType = Field(..., description="Source content type")
    url: str | None = Field(None, description="URL to crawl")
    effective_date: str | None = Field(None, description="Effective date (YYYY-MM-DD)")
    expiry_date: str | None = Field(None, description="Expiry date (YYYY-MM-DD)")
    crawl_status: CrawlStatus = Field(
        default=CrawlStatus.PENDING, description="Current crawl state"
    )
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority level")
    notes: str | None = Field(None, description="Optional notes")

    @field_validator("url")
    @classmethod
    def validate_url_domain(cls, v: str | None, info: Any) -> str | None:
        """Validate that URL is from trusted domain."""
        if v is None:
            return v

        parsed = urlparse(v)
        hostname = parsed.hostname

        if hostname and "thuvienphapluat.vn" not in hostname:
            raise ValueError(f"URL must be from thuvienphapluat.vn, got: {hostname}")

        return v

    @field_validator("source_domain")
    @classmethod
    def validate_source_domain(cls, v: str) -> str:
        """Validate source domain."""
        if "thuvienphapluat.vn" not in v:
            raise ValueError(f"source_domain must be thuvienphapluat.vn, got: {v}")
        return v

    @field_validator("domain_tags")
    @classmethod
    def validate_domain_tags(cls, v: list[str]) -> list[str]:
        """Validate domain tags are non-empty strings."""
        return [tag.strip() for tag in v if tag and tag.strip()]

    def is_pending(self) -> bool:
        """Check if target is pending crawl."""
        return self.crawl_status == CrawlStatus.PENDING

    def is_crawled(self) -> bool:
        """Check if target has been successfully crawled."""
        return self.crawl_status in {
            CrawlStatus.CRAWLED,
            CrawlStatus.PARSED,
            CrawlStatus.INGESTED,
            CrawlStatus.VERIFIED,
        }

    def is_manual_review(self) -> bool:
        """Check if target is marked for manual review."""
        return self.crawl_status == CrawlStatus.MANUAL_REVIEW

    def has_url(self) -> bool:
        """Check if target has a URL."""
        return self.url is not None


class MetadataSchema(BaseModel):
    """Schema for metadata.json files.

    This schema defines the required and optional fields for
    tracking crawled legal documents.

    Required fields:
        law_id, name, tier, source_domain, source_type, url,
        crawl_status, http_status, crawled_at, content_hash,
        crawler_version, parser_hint

    Optional fields:
        group, effective_date, expiry_date, attachment_paths,
        error_message, refresh, previous_content_hash
    """

    law_id: str = Field(..., description="Unique law identifier")
    name: str = Field(..., description="Official law name")
    tier: int = Field(..., ge=0, description="Legal hierarchy tier")
    group: str | None = Field(None, description="Logical grouping")
    source_domain: str = Field(..., description="Source domain")
    source_type: str = Field(..., description="Source content type")
    url: str = Field(..., description="Crawled URL")
    crawl_status: str = Field(..., description="Crawl status (success/failed)")
    http_status: int | None = Field(None, description="HTTP response status code")
    crawled_at: str = Field(..., description="ISO 8601 timestamp of crawl")
    content_hash: str = Field(..., description="SHA-256 hash of content")
    crawler_version: str = Field(..., description="Crawler version")
    parser_hint: str = Field(..., description="Hint for parser selection")
    effective_date: str | None = Field(None, description="Legal effective date")
    expiry_date: str | None = Field(None, description="Legal expiry date")
    attachment_paths: list[str] = Field(
        default_factory=list, description="Paths to downloaded attachments"
    )
    error_message: str | None = Field(None, description="Error message if failed")
    refresh: bool = Field(default=False, description="Whether this is a refresh crawl")
    previous_content_hash: str | None = Field(None, description="Content hash from previous crawl")

    @staticmethod
    def now_iso() -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(exclude_none=True)


@dataclass
class CrawlResult:
    """Result of a single crawl operation.

    Attributes:
        target: The CrawlTarget that was attempted.
        success: Whether the crawl succeeded.
        http_status: HTTP status code if available.
        content: Raw content bytes if successful.
        content_hash: SHA-256 hash of content.
        error_message: Error message if failed.
        retry_count: Number of retry attempts.
        duration_seconds: Time taken for crawl.
        refreshed: Whether this was a refresh of existing content.
    """

    target: CrawlTarget
    success: bool
    http_status: int | None = None
    content: bytes | None = None
    content_hash: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    duration_seconds: float | None = None
    refreshed: bool = False


@dataclass
class CrawlSkipRecord:
    """Record of a skipped crawl target.

    Attributes:
        target: The CrawlTarget that was skipped.
        reason: Reason for skipping.
        existing_metadata_path: Path to existing metadata if any.
        existing_crawled_at: Previous crawl timestamp if available.
        existing_content_hash: Previous content hash if available.
    """

    target: CrawlTarget
    reason: str
    existing_metadata_path: str | None = None
    existing_crawled_at: str | None = None
    existing_content_hash: str | None = None


@dataclass
class CrawlSelection:
    """Result of target selection.

    Attributes:
        targets: Selected CrawlTarget list.
        total_available: Total targets in registry.
        selected_count: Number of targets selected.
        skipped_count: Number of targets skipped.
        skip_reasons: Map of skip reasons to counts.
        dry_run: Whether this was a dry run.
    """

    targets: list[CrawlTarget]
    total_available: int
    selected_count: int
    skipped_count: int = 0
    skip_reasons: dict[str, int] | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.skip_reasons is None:
            self.skip_reasons = {}
