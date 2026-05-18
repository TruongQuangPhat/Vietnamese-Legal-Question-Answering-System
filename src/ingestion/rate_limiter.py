"""Async HTTP rate limiter for crawl coordination.

This module provides rate limiting functionality to:
- Control request frequency per host
- Enforce concurrency limits
- Track timing between requests
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime


class RateLimiter:
    """Rate limiter for concurrent crawling.

    This class implements per-host rate limiting and global concurrency
    control for async crawling operations.

    Features:
        - Per-host request delay enforcement
        - Global concurrency semaphore
        - Async context manager for request scoping

    Attributes:
        delay_seconds: Minimum delay between requests to the same host.
        max_concurrency: Maximum concurrent requests across all hosts.
    """

    def __init__(
        self,
        delay_seconds: float = 2.0,
        max_concurrency: int = 2,
    ):
        """Initialize the rate limiter.

        Args:
            delay_seconds: Minimum delay between requests to the same host.
            max_concurrency: Maximum concurrent requests overall.
        """
        self.delay_seconds = delay_seconds
        self.max_concurrency = max_concurrency

        # Per-host last request times
        self._last_request: dict[str, datetime] = defaultdict(
            lambda: datetime.fromtimestamp(0, tz=UTC)
        )

        # Per-host lock for thread-safe access
        self._host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Global concurrency semaphore
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _get_host_lock(self, host: str) -> asyncio.Lock:
        """Get or create a lock for a host.

        Args:
            host: Hostname to get lock for.

        Returns:
            asyncio.Lock for the host.
        """
        async with asyncio.Lock():
            if host not in self._host_locks:
                self._host_locks[host] = asyncio.Lock()
            return self._host_locks[host]

    async def acquire(self, host: str) -> None:
        """Acquire rate limit permission for a host.

        This method:
        1. Acquires the global concurrency semaphore
        2. Waits until the required delay has passed for the host
        3. Records the current time as the last request time

        Args:
            host: Hostname to acquire permission for.
        """
        # Acquire global concurrency control
        await self._semaphore.acquire()

        # Get host lock
        host_lock = await self._get_host_lock(host)

        async with host_lock:
            now = datetime.now(UTC)
            last = self._last_request[host]

            # Calculate delay needed
            elapsed = (now - last).total_seconds()
            delay_needed = max(0, self.delay_seconds - elapsed)

            if delay_needed > 0:
                await asyncio.sleep(delay_needed)

            # Record this request time
            self._last_request[host] = datetime.now(UTC)

    async def release(self, host: str) -> None:
        """Release rate limit permission for a host.

        Args:
            host: Hostname to release permission for.
        """
        # Release the semaphore
        self._semaphore.release()

        # Note: We don't release the host lock; it's only used
        # for synchronizing last_request updates

    @asynccontextmanager
    async def limit(self, host: str):
        """Async context manager for rate-limited requests.

        Usage:
            async with rate_limiter.limit(host):
                await session.get(url)

        Args:
            host: Hostname to limit.

        Yields:
            None, after acquiring rate limit permission.
        """
        await self.acquire(host)
        try:
            yield
        finally:
            await self.release(host)

    def reset(self) -> None:
        """Reset all rate limit state.

        Clears all host tracking data and resets the semaphore.
        """
        self._last_request.clear()
        self._host_locks.clear()
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
