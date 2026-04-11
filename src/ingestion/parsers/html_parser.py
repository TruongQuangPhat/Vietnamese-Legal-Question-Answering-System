"""
HTML Parser cho thuvienphapluat.vn
====================================
Trích xuất nội dung văn bản luật từ HTML thô của thuvienphapluat.vn,
loại bỏ navigation, ads, header/footer, chỉ giữ lại phần nội dung chính.

**Cấu trúc HTML của thuvienphapluat.vn** (phân tích thực tế):
- Nội dung luật nằm trong các thẻ chứa text Điều, Khoản, Điểm
- Các link nội bộ ``[Điều X...]`` chứa cross-reference → capture URL
- Cần strip markdown links ``[text](url)`` nếu parse từ markdown converted

Sử dụng::

    from src.ingestion.parsers.html_parser import ThuvienphapluatHTMLParser

    parser = ThuvienphapluatHTMLParser()
    clean_text = parser.parse(raw_html)
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from src.core.exceptions import ParseError
from src.core.logger import get_logger
from src.ingestion.parsers.base import BaseLawParser

logger = get_logger(__name__)


class ThuvienphapluatHTMLParser(BaseLawParser):
    """
    Parser HTML chuyên dụng cho trang thuvienphapluat.vn.

    Xử lý:
    1. Loại bỏ header, footer, sidebar, ads, scripts, styles
    2. Trích xuất nội dung luật chính (div chứa các Điều)
    3. Bảo toàn cấu trúc phân cấp (Phần, Chương, Điều, Khoản, Điểm)
    4. Capture cross-reference links để phục vụ GraphRAG (Phase 3)
    5. Trả về clean text sẵn sàng cho legal parser

    Attributes:
        cross_reference_urls: Danh sách URLs tham chiếu chéo thu thập được.
    """

    def __init__(self) -> None:
        """Khởi tạo parser, reset danh sách cross references."""
        self.cross_reference_urls: list[str] = []

    def parse(self, content: str) -> str:
        """
        Parse HTML thô từ thuvienphapluat.vn thành plain text sạch.

        Args:
            content: HTML thô hoặc nội dung đã convert sang markdown.

        Returns:
            str: Nội dung văn bản luật đã làm sạch, giữ cấu trúc phân cấp.

        Raises:
            ParseError: Khi không tìm thấy nội dung luật trong HTML.
        """
        # Reset cross references mỗi lần parse
        self.cross_reference_urls = []

        logger.info("html_parse_started", content_length=len(content))

        # Nếu input là HTML thật (có tag), dùng BeautifulSoup
        if "<html" in content.lower() or "<div" in content.lower():
            text = self._parse_html(content)
        else:
            # Input đã là text/markdown (VD: từ read_url_content)
            text = self._parse_markdown_content(content)

        if not text or len(text.strip()) < 100:
            raise ParseError(
                "No legal content found in the document",
                details={"content_length": len(content)},
            )

        logger.info(
            "html_parse_completed",
            output_length=len(text),
            cross_refs_found=len(self.cross_reference_urls),
        )
        return text

    def _parse_html(self, html: str) -> str:
        """
        Parse HTML thuần từ BeautifulSoup.

        Chiến lược:
        1. Loại bỏ script, style, nav, footer
        2. Tìm div chứa nội dung chính (dựa vào pattern Điều)
        3. Lấy text giữ cấu trúc dòng

        Args:
            html: HTML thô.

        Returns:
            str: Text đã làm sạch.
        """
        soup = BeautifulSoup(html, "lxml")

        # Bước 1: Loại bỏ các phần tử không cần thiết
        for tag_name in ["script", "style", "nav", "footer", "header", "aside"]:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Bước 2: Tìm nội dung chính
        # thuvienphapluat.vn thường đặt nội dung trong div có class chứa 'content'
        # hoặc div chứa text "Điều 1."
        content_div = self._find_content_div(soup)

        if content_div:
            # Bước 3: Capture cross-reference links trước khi strip HTML
            self._extract_cross_refs_from_html(content_div)
            # Bước 4: Lấy text giữ cấu trúc dòng
            text = content_div.get_text(separator="\n", strip=True)
        else:
            # Fallback: lấy toàn bộ body text
            logger.warning("content_div_not_found", fallback="full_body")
            body = soup.find("body")
            text = body.get_text(separator="\n", strip=True) if body else ""

        return text

    def _find_content_div(self, soup: BeautifulSoup) -> Tag | None:
        """
        Tìm div chứa nội dung luật chính trong HTML.

        Thử nhiều chiến lược theo thứ tự ưu tiên:
        1. Div có class chứa 'content' và chứa text 'Điều 1.'
        2. Div có id chứa 'noidung', 'content', 'vanban'
        3. Div chứa nhiều text 'Điều' nhất

        Args:
            soup: BeautifulSoup object đã parse.

        Returns:
            Tag hoặc None nếu không tìm thấy.
        """
        # Chiến lược 1: Tìm theo class phổ biến
        for class_pattern in ["content", "noidung", "fulltext", "van-ban"]:
            pattern = class_pattern  # Bind loop variable for lambda (B023)
            candidates = soup.find_all(
                "div",
                class_=lambda c, p=pattern: c and p in str(c).lower()
            )
            for div in candidates:
                if "Điều 1." in div.get_text() or "Điều 1 " in div.get_text():
                    return div

        # Chiến lược 2: Tìm div chứa nhiều "Điều" nhất
        all_divs = soup.find_all("div")
        best_div: Tag | None = None
        max_dieu_count = 0

        for div in all_divs:
            text = div.get_text()
            dieu_count = text.count("Điều ")
            if dieu_count > max_dieu_count:
                max_dieu_count = dieu_count
                best_div = div

        # Chỉ trả về nếu tìm thấy ít nhất 5 Điều (tránh false positive)
        if max_dieu_count >= 5:
            return best_div

        return None

    def _extract_cross_refs_from_html(self, element: Tag) -> None:
        """
        Thu thập URLs tham chiếu chéo từ các link nội bộ trong HTML.

        Tìm các thẻ <a> chứa text "Điều" hoặc link đến trang luật khác
        trên thuvienphapluat.vn.

        Args:
            element: Tag HTML chứa nội dung luật.
        """
        base_domain = "thuvienphapluat.vn"

        for link in element.find_all("a", href=True):
            href = str(link.get("href", ""))
            link_text = link.get_text(strip=True)

            # Chỉ capture link tham chiếu đến các điều luật khác
            if (
                base_domain in href
                and ("Điều" in link_text or "van-ban" in href)
                and href not in self.cross_reference_urls
            ):
                self.cross_reference_urls.append(href)

    def _parse_markdown_content(self, content: str) -> str:
        """
        Parse nội dung đã convert sang markdown (từ read_url_content).

        Khi dùng tool read_url_content, HTML được tự động convert sang markdown.
        Cần strip markdown formatting và chỉ giữ lại text.

        Args:
            content: Nội dung markdown.

        Returns:
            str: Text đã làm sạch.
        """
        lines: list[str] = []
        # Flag: bắt đầu tracking từ khi gặp nội dung luật
        in_law_content = False

        for line in content.split("\n"):
            stripped = line.strip()

            # Bỏ qua các dòng trống ở đầu
            if not in_law_content and any(
                marker in stripped
                for marker in [
                    "Điều 1.",
                    "Điều 1 ",
                    "QUỐC HỘI",
                    "Phần thứ nhất",
                    "PHẦN THỨ NHẤT",
                    "Chương I",
                    "CHƯƠNG I",
                ]
            ):
                in_law_content = True

            if not in_law_content:
                continue

            # Strip markdown link syntax: [text](url) → text
            clean_line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", stripped)

            # Strip markdown heading syntax
            clean_line = re.sub(r"^#{1,6}\s+", "", clean_line)

            # Bỏ qua dòng chỉ chứa markdown decorators
            if clean_line in ("---", "***", "___"):
                continue

            # Bỏ qua dòng quảng cáo / navigation
            skip_patterns = [
                "Đăng nhập", "Đăng ký", "Quên mật khẩu",
                "dịch vụ", "Widget", "mobile", "Rss",
                "Tóm tắt nội dung", "Tiếng Anh", "Lược đồ",
                "MỤC LỤC", "In mục lục", "Tải về",
                "Liên quan hiệu lực", "Thuộc tính",
                "Các bản dự thảo", "Văn bản gốc/PDF",
            ]
            if any(pattern in clean_line for pattern in skip_patterns):
                continue

            if clean_line:
                lines.append(clean_line)

        return "\n".join(lines)
