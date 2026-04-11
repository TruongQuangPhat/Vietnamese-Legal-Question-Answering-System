"""
Base Parser — Abstract Interface
==================================
Định nghĩa interface chung cho mọi parser trong hệ thống.

Mọi parser cụ thể (HTML, Legal) đều kế thừa từ ``BaseLawParser``
để đảm bảo tính nhất quán trong API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLawParser(ABC):
    """
    Abstract base class cho các parser pháp luật.

    Subclass phải implement phương thức ``parse()`` để chuyển đổi
    dữ liệu đầu vào (HTML, text) thành dạng đã xử lý.
    """

    @abstractmethod
    def parse(self, content: str) -> str:
        """
        Parse nội dung đầu vào và trả về kết quả đã xử lý.

        Args:
            content: Nội dung thô cần parse (HTML hoặc text).

        Returns:
            str: Nội dung đã được làm sạch và chuẩn hóa.

        Raises:
            ParseError: Khi không thể parse nội dung đầu vào.
        """
        ...
