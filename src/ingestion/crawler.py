"""Async HTTP client for legal document crawling.

This module provides the core crawling functionality:
- Fetching from trusted domains
- Retry with exponential backoff
- Status tracking and error handling
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from urllib.parse import urlparse

import structlog
from httpx import AsyncClient, RequestError, TimeoutException, codes

from src.core.config import get_settings
from src.core.exceptions import TrustedDomainError
from src.ingestion.models import CrawlResult, CrawlTarget
from src.ingestion.rate_limiter import RateLimiter
from src.ingestion.storage import RawArtifactStore

logger = structlog.get_logger(__name__)


class BaseCrawler:
    """Abstract base class for legal document crawlers.

    This class defines the interface for all crawler implementations.
    Subclasses must implement the crawl method.

    Attributes:
        rate_limiter: Rate limiter for request throttling.
        storage: Raw artifact storage handler.
        timeout_seconds: Request timeout in seconds.
    """

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        storage: RawArtifactStore | None = None,
    ):
        """Initialize the base crawler.

        Args:
            rate_limiter: Rate limiter instance.
            storage: Raw artifact storage instance.
        """
        self.rate_limiter = rate_limiter or RateLimiter()
        self.storage = storage
        self._settings = get_settings()
        self.timeout_seconds = self._settings.crawler_timeout_seconds

    async def crawl(self, target: CrawlTarget) -> CrawlResult:
        """Crawl a single target.

        This method must be implemented by subclasses.

        Args:
            target: CrawlTarget to crawl.

        Returns:
            CrawlResult with success/failure information.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError("Subclasses must implement crawl()")

    def _validate_trusted_domain(self, url: str) -> None:
        """Validate that a URL is from a trusted domain.

        Args:
            url: URL to validate.

        Raises:
            TrustedDomainError: If the URL is not from a trusted domain.
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            raise TrustedDomainError(url, self._settings.trusted_domain)

        if self._settings.trusted_domain not in hostname:
            raise TrustedDomainError(url, self._settings.trusted_domain)


class ThuvienPhapLuatCrawler(BaseCrawler):
    """Crawler for thuvienphapluat.vn legal documents.

    This crawler implements:
    - Async I/O with httpx
    - Retry with exponential backoff
    - Rate limiting per host
    - Content storage with metadata

    Attributes:
        rate_limiter: Rate limiter for request throttling.
        storage: Raw artifact storage handler.
        max_retries: Maximum retry attempts.
        timeout_seconds: Request timeout in seconds.
    """

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        storage: RawArtifactStore | None = None,
        max_retries: int | None = None,
    ):
        """Initialize the ThuvienPhapLuat crawler.

        Args:
            rate_limiter: Rate limiter instance.
            storage: Raw artifact storage instance.
            max_retries: Maximum retry attempts. If None, uses config default.
        """
        super().__init__(rate_limiter, storage)
        self.max_retries = max_retries or self._settings.crawler_max_retries

    async def crawl(self, target: CrawlTarget) -> CrawlResult:
        """Crawl a legal document from thuvienphapluat.vn.

        This method:
        1. Validates the target URL is from a trusted domain
        2. Fetches the content with retry and exponential backoff
        3. Stores the raw HTML and metadata
        4. Returns a CrawlResult with the outcome

        Args:
            target: CrawlTarget to crawl.

        Returns:
            CrawlResult with success/failure information.
        """
        if target.url:
            self._validate_trusted_domain(target.url)

        host = self._extract_host(target.url or "")

        logger.info(
            "Starting crawl",
            law_id=target.law_id,
            url=target.url,
            source_type=target.source_type.value,
        )

        start_time = time.time()
        retry_count = 0
        content: bytes | None = None
        http_status: int | None = None
        error_message: str | None = None

        async with AsyncClient(
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": "VnLaw-QA-Crawler/1.0.0 (Legal Research Bot; vnlaw-qa@thuvienphapluat.vn)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            while retry_count <= self.max_retries:
                try:
                    # Apply rate limiting
                    async with self.rate_limiter.limit(host):
                        response = await client.get(
                            target.url or "",
                            follow_redirects=True,
                        )

                    http_status = response.status_code

                    if response.status_code == codes.OK:
                        content = response.read()
                        break

                    # Check for rate limiting
                    if response.status_code == codes.TOO_MANY_REQUESTS:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(
                            "Rate limited, waiting",
                            law_id=target.law_id,
                            retry_after=retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        retry_count += 1
                        continue

                    # Other error status
                    error_message = f"HTTP {response.status_code}"
                    break

                except TimeoutException:
                    error_message = "Request timeout"
                    retry_count += 1

                except RequestError as e:
                    error_message = str(e)
                    retry_count += 1

                except Exception as e:
                    # Log unexpected errors but don't suppress them
                    logger.error(
                        "Unexpected crawl error",
                        law_id=target.law_id,
                        error=str(e),
                        exc_info=True,
                    )
                    error_message = f"Unexpected error: {e}"
                    break

            else:
                # Exhausted all retries
                error_message = f"Failed after {retry_count} retries: {error_message}"

        duration = time.time() - start_time

        # Prepare result
        if content is not None and http_status == codes.OK:
            content_hash = self._compute_hash(content) if content else None

            # Store artifacts if storage is configured
            if self.storage:
                try:
                    self.storage.save_html(
                        law_id=target.law_id,
                        content=content,
                        http_status=http_status,
                        refresh=False,
                        previous_content_hash=None,
                        name=target.name,
                        tier=target.tier,
                        group=target.group,
                        source_type=target.source_type.value,
                        url=target.url or "",
                        effective_date=target.effective_date,
                        expiry_date=target.expiry_date,
                    )
                    logger.info(
                        "Crawl completed successfully",
                        law_id=target.law_id,
                        content_hash=(content_hash or "")[:16],
                        duration=duration,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to save crawl artifacts",
                        law_id=target.law_id,
                        error=str(e),
                    )
                    error_message = f"Content fetched but save failed: {e}"
                    content = None
                    content_hash = None

            return CrawlResult(
                target=target,
                success=content is not None,
                http_status=http_status,
                content=content,
                content_hash=content_hash,
                retry_count=retry_count,
                duration_seconds=duration,
            )
        else:
            logger.warning(
                "Crawl failed",
                law_id=target.law_id,
                error=error_message,
                retry_count=retry_count,
            )
            return CrawlResult(
                target=target,
                success=False,
                http_status=http_status,
                error_message=error_message,
                retry_count=retry_count,
                duration_seconds=duration,
            )

    def _extract_host(self, url: str) -> str:
        """Extract hostname from URL.

        Args:
            url: URL to extract host from.

        Returns:
            Hostname string.
        """
        parsed = urlparse(url)
        return parsed.hostname or "unknown"

    def _compute_hash(self, data: bytes) -> str:
        """Compute SHA-256 hash of content.

        Args:
            data: Raw bytes to hash.

        Returns:
            SHA-256 hash as hexadecimal string.
        """
        return hashlib.sha256(data).hexdigest()


async def crawl_with_retry(
    client: AsyncClient,
    url: str,
    rate_limiter: RateLimiter,
    max_retries: int,
) -> tuple[bytes | None, int | None, str | None, int]:
    """Fetch content with retry and exponential backoff.

    Args:
        client: httpx AsyncClient instance.
        url: URL to fetch.
        rate_limiter: Rate limiter instance.
        max_retries: Maximum retry attempts.

    Returns:
        Tuple of (content, http_status, error_message, retry_count).
    """
    host = urlparse(url).hostname or "unknown"
    retry_count = 0
    content: bytes | None = None
    http_status: int | None = None
    error_message: str | None = None

    while retry_count <= max_retries:
        try:
            async with rate_limiter.limit(host):
                response = await client.get(url, follow_redirects=True)

            http_status = response.status_code

            if response.status_code == codes.OK:
                content = response.read()
                return content, http_status, None, retry_count

            # Handle rate limiting
            if response.status_code == codes.TOO_MANY_REQUESTS:
                retry_after = int(response.headers.get("Retry-After", 5))
                await asyncio.sleep(retry_after)
                retry_count += 1
                continue

            # Other errors
            error_message = f"HTTP {response.status_code}"
            return None, http_status, error_message, retry_count

        except TimeoutException:
            error_message = "Request timeout"

        except RequestError as e:
            error_message = str(e)

        retry_count += 1

        # Exponential backoff
        if retry_count <= max_retries:
            backoff = 2**retry_count
            await asyncio.sleep(min(backoff, 30))

    return None, http_status, error_message, retry_count
