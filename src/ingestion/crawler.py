"""
VnLaw-QA Async Crawler
========================
Crawler bất đồng bộ cho thuvienphapluat.vn với rate limiting và auto-retry.

**Nguyên tắc crawl** (từ rules.md / data-sources.md):
- Nguồn dữ liệu DUY NHẤT: thuvienphapluat.vn
- Rate limit: nghỉ 2 giây giữa mỗi request
- Max concurrent: 3 request song song (Semaphore)
- User-Agent hợp lệ: ``VnLawQA-Research/1.0``
- Auto-retry 3 lần với exponential backoff khi gặp lỗi network

Sử dụng::

    from src.ingestion.crawler import ThuvienphapluatCrawler

    crawler = ThuvienphapluatCrawler()
    html = await crawler.fetch_law_page("https://thuvienphapluat.vn/...")
    await crawler.save_raw_html(html, "BLDS_2015")
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import PROJECT_ROOT, get_settings
from src.core.exceptions import CrawlError
from src.core.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


class ThuvienphapluatCrawler:
    """
    Async crawler cho thuvienphapluat.vn với cơ chế bảo vệ tránh bị block.

    Features:
    - Semaphore giới hạn số request đồng thời (mặc định 3)
    - Rate limiting: nghỉ tối thiểu N giây giữa 2 request (mặc định 2s)
    - Tenacity auto-retry: 3 lần, exponential backoff 2-10s
    - Timeout: 30s cho mỗi request
    - Lưu HTML thô vào ``data/raw/{law_id}/main.html``

    Attributes:
        BASE_URL: Domain gốc của thuvienphapluat.vn.
        USER_AGENT: Chuỗi User-Agent dùng khi crawl.
    """

    BASE_URL: str = "https://thuvienphapluat.vn"
    USER_AGENT: str = "VnLawQA-Research/1.0"

    def __init__(
        self,
        rate_limit: float | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        """
        Khởi tạo crawler.

        Args:
            rate_limit: Số giây nghỉ tối thiểu giữa 2 request.
                        Mặc định đọc từ config (2.0s).
            max_concurrent: Số request tối đa chạy song song.
                           Mặc định đọc từ config (3).
        """
        settings = get_settings()
        self._rate_limit = rate_limit or settings.crawl_rate_limit
        self._max_concurrent = max_concurrent or settings.crawl_max_concurrent
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._last_request_time: float = 0.0

    async def _wait_rate_limit(self) -> None:
        """
        Chờ đủ thời gian rate limit trước khi gửi request tiếp theo.

        So sánh thời gian hiện tại với thời gian gửi request cuối cùng,
        nếu chưa đủ khoảng cách rate_limit thì sleep thêm.
        """
        now = time.monotonic()
        elapsed = now - self._last_request_time
        wait_time = self._rate_limit - elapsed

        if wait_time > 0:
            logger.debug(
                "rate_limit_waiting",
                wait_seconds=round(wait_time, 2),
            )
            await asyncio.sleep(wait_time)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def fetch_law_page(self, url: str) -> str:
        """
        Tải nội dung HTML từ một trang luật trên thuvienphapluat.vn.

        Áp dụng semaphore + rate limiting + auto-retry.

        Args:
            url: URL đầy đủ của trang luật cần crawl.

        Returns:
            str: Nội dung HTML thô của trang.

        Raises:
            CrawlError: Khi tất cả retry đều thất bại hoặc HTTP error.
        """
        async with self._semaphore:
            # Chờ rate limit
            await self._wait_rate_limit()

            logger.info("crawl_started", url=url)

            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.get(
                        url,
                        headers={
                            "User-Agent": self.USER_AGENT,
                            "Accept": "text/html,application/xhtml+xml",
                            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
                        },
                    ) as response,
                ):
                    # Cập nhật thời gian request cuối cùng
                    self._last_request_time = time.monotonic()

                    # Kiểm tra HTTP status
                    if response.status != 200:
                        raise CrawlError(
                            f"HTTP {response.status} for {url}",
                            details={"url": url, "status": response.status},
                        )

                    html = await response.text()
                    logger.info(
                        "crawl_completed",
                        url=url,
                        content_length=len(html),
                    )
                    return html

            except aiohttp.ClientError as e:
                logger.error("crawl_network_error", url=url, error=str(e))
                raise
            except TimeoutError:
                logger.error("crawl_timeout", url=url)
                raise

    async def save_raw_html(
        self,
        html: str,
        law_id: str,
        output_dir: Path | None = None,  # noqa: UP007
    ) -> Path:
        """
        Lưu HTML thô vào hệ thống file.

        Cấu trúc lưu trữ::

            data/raw/{law_id}/main.html

        Args:
            html: Nội dung HTML thô.
            law_id: Mã ID luật (VD: "BLDS_2015").
            output_dir: Thư mục gốc chứa data. Mặc định: ``data/raw/``.

        Returns:
            Path: Đường dẫn file đã lưu.

        Raises:
            CrawlError: Khi không thể ghi file.
        """
        if output_dir is None:
            output_dir = PROJECT_ROOT / "data" / "raw"

        # Tạo thư mục con cho law_id
        law_dir = output_dir / law_id
        law_dir.mkdir(parents=True, exist_ok=True)

        file_path = law_dir / "main.html"

        try:
            file_path.write_text(html, encoding="utf-8")
            logger.info(
                "html_saved",
                law_id=law_id,
                path=str(file_path),
                size_bytes=len(html.encode("utf-8")),
            )
            return file_path

        except OSError as e:
            logger.error("html_save_failed", law_id=law_id, error=str(e))
            raise CrawlError(
                f"Failed to save HTML for {law_id}: {e}",
                details={"law_id": law_id, "path": str(file_path)},
            ) from e
