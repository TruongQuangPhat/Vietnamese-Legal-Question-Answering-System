"""Unit tests for the crawler module.

Tests cover:
- Trusted domain validation
- Rate limiting
- Retry with exponential backoff
- Concurrency limits
- Continue on failure
- Crawl summary
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from src.core.exceptions import TrustedDomainError
from src.ingestion.crawler import (
    BaseCrawler,
    ThuvienPhapLuatCrawler,
)
from src.ingestion.models import CrawlStatus, CrawlTarget, Priority, SourceType
from src.ingestion.rate_limiter import RateLimiter
from src.ingestion.storage import RawArtifactStore


class TestBaseCrawler:
    """Tests for BaseCrawler class."""

    @pytest.fixture
    def base_crawler(self) -> BaseCrawler:
        """Create a BaseCrawler instance."""
        return BaseCrawler()

    def test_validate_trusted_domain_valid(self, base_crawler: BaseCrawler) -> None:
        """Test validating a trusted domain URL."""
        # Should not raise
        base_crawler._validate_trusted_domain("https://thuvienphapluat.vn/test")

    def test_validate_trusted_domain_invalid(self, base_crawler: BaseCrawler) -> None:
        """Test validating an untrusted domain URL."""
        with pytest.raises(TrustedDomainError, match="thuvienphapluat.vn"):
            base_crawler._validate_trusted_domain("https://example.com/test")

    def test_validate_trusted_domain_with_subdomain(self, base_crawler: BaseCrawler) -> None:
        """Test validating URL with subdomain."""
        # Should not raise - subdomain of trusted domain is OK
        base_crawler._validate_trusted_domain("https://sub.thuvienphapluat.vn/test")

    def test_crawl_not_implemented(self, base_crawler: BaseCrawler) -> None:
        """Test that crawl raises NotImplementedError."""
        import asyncio

        target = CrawlTarget(
            law_id="TEST",
            name="Test",
            tier=1,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test",
            crawl_status=CrawlStatus.PENDING,
            priority=Priority.HIGH,
        )

        with pytest.raises(NotImplementedError):
            asyncio.run(base_crawler.crawl(target))


class TestThuvienPhapLuatCrawler:
    """Tests for ThuvienPhapLuatCrawler class."""

    @pytest.fixture
    def crawler(self, tmp_path: Path) -> ThuvienPhapLuatCrawler:
        """Create a ThuvienPhapLuatCrawler instance."""
        storage = RawArtifactStore(tmp_path)
        rate_limiter = RateLimiter(delay_seconds=0.1, max_concurrency=2)
        return ThuvienPhapLuatCrawler(
            rate_limiter=rate_limiter,
            storage=storage,
            max_retries=2,
        )

    @pytest.fixture
    def sample_target(self) -> CrawlTarget:
        """Create a sample crawl target."""
        return CrawlTarget(
            law_id="TEST_LAW",
            name="Test Law",
            tier=1,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test.aspx",
            crawl_status=CrawlStatus.PENDING,
            priority=Priority.HIGH,
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_crawl_success(
        self,
        crawler: ThuvienPhapLuatCrawler,
        sample_target: CrawlTarget,
        tmp_path: Path,
    ) -> None:
        """Test successful crawl."""
        # Mock successful response
        respx.get("https://thuvienphapluat.vn/test.aspx").mock(
            return_value=httpx.Response(
                200,
                content=b"<html><body>Test content</body></html>",
            )
        )

        result = await crawler.crawl(sample_target)

        assert result.success is True
        assert result.http_status == 200
        assert result.content is not None
        assert result.content_hash is not None
        assert result.duration_seconds is not None

    @respx.mock
    @pytest.mark.asyncio
    async def test_crawl_with_retry_on_timeout(
        self,
        crawler: ThuvienPhapLuatCrawler,
        sample_target: CrawlTarget,
    ) -> None:
        """Test retry behavior on timeout."""
        # Mock timeout on first attempt, success on second
        call_count = 0

        def mock_timeout(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Connection timeout")
            return httpx.Response(200, content=b"<html></html>")

        respx.get("https://thuvienphapluat.vn/test.aspx").mock(side_effect=mock_timeout)

        result = await crawler.crawl(sample_target)

        # Should have retried and eventually succeeded
        assert result.success is True
        assert result.retry_count >= 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_crawl_rate_limit_429(
        self,
        crawler: ThuvienPhapLuatCrawler,
        sample_target: CrawlTarget,
    ) -> None:
        """Test handling of 429 rate limit response."""
        # Mock 429 then success
        call_count = 0

        def mock_rate_limit(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(200, content=b"<html></html>")

        respx.get("https://thuvienphapluat.vn/test.aspx").mock(side_effect=mock_rate_limit)

        result = await crawler.crawl(sample_target)

        assert result.success is True
        assert call_count >= 2  # At least one retry

    @pytest.mark.asyncio
    async def test_trusted_domain_validation(
        self,
        crawler: ThuvienPhapLuatCrawler,
    ) -> None:
        """Test that untrusted domains are rejected."""
        # Test the _validate_trusted_domain method directly
        with pytest.raises(TrustedDomainError, match="thuvienphapluat.vn"):
            crawler._validate_trusted_domain("https://example.com/test")


class TestRateLimiter:
    """Tests for RateLimiter class."""

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_delay(self) -> None:
        """Test that rate limiter enforces delay between requests."""
        limiter = RateLimiter(delay_seconds=0.5, max_concurrency=10)

        start = asyncio.get_event_loop().time()

        # Make two requests to same host
        await limiter.acquire("test.com")
        await limiter.release("test.com")

        await limiter.acquire("test.com")
        await limiter.release("test.com")

        elapsed = asyncio.get_event_loop().time() - start

        # Should have waited at least 0.5 seconds
        assert elapsed >= 0.4  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_concurrency_limit(self) -> None:
        """Test that concurrency limit is respected."""
        limiter = RateLimiter(delay_seconds=0, max_concurrency=2)

        # Acquire twice (should succeed)
        await limiter.acquire("test.com")
        await limiter.acquire("test.com")

        # Try to acquire third time with timeout
        try:
            await asyncio.wait_for(limiter.acquire("test.com"), timeout=0.1)
            # If we get here, release one and try again
            await limiter.release("test.com")
            raise AssertionError("Should have timed out")
        except TimeoutError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        """Test that reset clears state."""
        limiter = RateLimiter(delay_seconds=0.5, max_concurrency=2)

        await limiter.acquire("test.com")
        await limiter.release("test.com")

        limiter.reset()

        # After reset, should be able to acquire immediately without delay
        await limiter.acquire("test.com")
        await limiter.release("test.com")


class TestCrawlIntegration:
    """Integration tests for crawl behavior."""

    @pytest.fixture
    def tmp_storage(self, tmp_path: Path) -> RawArtifactStore:
        """Create storage in temporary directory."""
        return RawArtifactStore(tmp_path)

    @respx.mock
    @pytest.mark.asyncio
    async def test_continue_on_failure(
        self,
        tmp_storage: RawArtifactStore,
    ) -> None:
        """Test that batch crawl continues after individual failures."""
        rate_limiter = RateLimiter(delay_seconds=0.1, max_concurrency=2)
        crawler = ThuvienPhapLuatCrawler(
            rate_limiter=rate_limiter,
            storage=tmp_storage,
            max_retries=1,
        )

        # Mock different responses
        respx.get("https://thuvienphapluat.vn/success.aspx").mock(
            return_value=httpx.Response(200, content=b"<html>OK</html>")
        )
        respx.get("https://thuvienphapluat.vn/fail.aspx").mock(return_value=httpx.Response(500))

        targets = [
            CrawlTarget(
                law_id="SUCCESS",
                name="Success Law",
                tier=1,
                group="Test",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.HTML,
                url="https://thuvienphapluat.vn/success.aspx",
                crawl_status=CrawlStatus.PENDING,
                priority=Priority.HIGH,
            ),
            CrawlTarget(
                law_id="FAIL",
                name="Fail Law",
                tier=1,
                group="Test",
                source_domain="thuvienphapluat.vn",
                source_type=SourceType.HTML,
                url="https://thuvienphapluat.vn/fail.aspx",
                crawl_status=CrawlStatus.PENDING,
                priority=Priority.HIGH,
            ),
        ]

        # Run both crawls
        results = await asyncio.gather(
            crawler.crawl(targets[0]),
            crawler.crawl(targets[1]),
            return_exceptions=True,
        )

        # First should succeed, second should fail
        assert results[0].success is True
        assert results[1].success is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_produce_crawl_summary(
        self,
        tmp_storage: RawArtifactStore,
    ) -> None:
        """Test that crawl produces proper summary data."""
        rate_limiter = RateLimiter(delay_seconds=0.1, max_concurrency=2)
        crawler = ThuvienPhapLuatCrawler(
            rate_limiter=rate_limiter,
            storage=tmp_storage,
            max_retries=1,
        )

        respx.get("https://thuvienphapluat.vn/test.aspx").mock(
            return_value=httpx.Response(200, content=b"<html>OK</html>")
        )

        target = CrawlTarget(
            law_id="SUMMARY_TEST",
            name="Summary Test",
            tier=1,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type=SourceType.HTML,
            url="https://thuvienphapluat.vn/test.aspx",
            crawl_status=CrawlStatus.PENDING,
            priority=Priority.HIGH,
        )

        result = await crawler.crawl(target)

        # Result should have all summary fields
        assert result.duration_seconds is not None
        assert result.retry_count >= 0
        assert result.http_status == 200
