"""VnLaw-QA Ingestion Module.

This module implements the data ingestion pipeline for legal documents:
- Registry loading and validation
- Target selection with filtering
- Async crawling with rate limiting and retry
- Raw artifact storage with metadata
"""

from __future__ import annotations

__all__ = [
    "CrawlTarget",
    "CrawlResult",
    "CrawlSelection",
    "CrawlSkipRecord",
    "MetadataSchema",
    "CorpusRegistryLoader",
    "CrawlTargetSelector",
    "RawArtifactStore",
    "BaseCrawler",
    "ThuvienPhapLuatCrawler",
    "RateLimiter",
]
