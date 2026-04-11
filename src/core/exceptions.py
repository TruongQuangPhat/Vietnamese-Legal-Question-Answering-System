"""
VnLaw-QA Custom Exceptions
===========================
Định nghĩa các exception tùy chỉnh cho từng tầng trong pipeline.
Mỗi exception phải mang theo thông tin ngữ cảnh đủ để debug,
KHÔNG BAO GIỜ dùng ``except Exception: pass``.

Hệ thống phân cấp exception::

    VnLawQAError (base)
    ├── CrawlError          — Lỗi khi crawl HTML từ nguồn
    ├── ParseError           — Lỗi khi parse HTML hoặc cấu trúc pháp lý
    ├── ChunkingError        — Lỗi khi chia chunk Parent-Child
    ├── EmbeddingError       — Lỗi khi tạo embedding vectors
    ├── VectorStoreError     — Lỗi khi tương tác Qdrant
    └── PipelineError        — Lỗi tổng hợp trong orchestration
"""

from __future__ import annotations


class VnLawQAError(Exception):
    """
    Base exception cho toàn bộ hệ thống VnLaw-QA.

    Mọi exception tùy chỉnh đều kế thừa từ class này,
    giúp dễ dàng catch toàn bộ lỗi domain-specific.
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        """
        Args:
            message: Mô tả lỗi ngắn gọn.
            details: Dict chứa thông tin bổ sung để debug (law_id, url, ...).
        """
        super().__init__(message)
        self.details = details or {}


class CrawlError(VnLawQAError):
    """
    Lỗi xảy ra khi crawl dữ liệu từ thuvienphapluat.vn.

    VD: Timeout, HTTP 403, rate limit bị block, network error.
    """


class ParseError(VnLawQAError):
    """
    Lỗi xảy ra khi parse HTML hoặc phân tích cấu trúc pháp lý.

    VD: HTML structure thay đổi, không tìm thấy content div,
    Regex không match được cấu trúc Điều/Khoản/Điểm.
    """


class ChunkingError(VnLawQAError):
    """
    Lỗi xảy ra khi chia chunk theo chiến lược Parent-Child.

    VD: Điều không có nội dung, hierarchy bị đứt gãy.
    """


class EmbeddingError(VnLawQAError):
    """
    Lỗi xảy ra khi tạo embedding vectors bằng BGE-M3.

    VD: Model không load được, OOM trên GPU, batch size quá lớn.
    """


class VectorStoreError(VnLawQAError):
    """
    Lỗi xảy ra khi tương tác với Qdrant vector database.

    VD: Connection refused, collection không tồn tại,
    upsert thất bại, search timeout.
    """


class PipelineError(VnLawQAError):
    """
    Lỗi xảy ra trong quá trình orchestration pipeline tổng thể.

    Thường wrap các exception cụ thể khác khi một bước trong
    pipeline thất bại và cần context tổng hợp.
    """
