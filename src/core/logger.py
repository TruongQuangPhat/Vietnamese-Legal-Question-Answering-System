"""
VnLaw-QA Structured Logging
============================
Cấu hình structlog với output JSON, tự động thêm timestamp và log level.
Mọi module sử dụng ``structlog.get_logger(__name__)`` để lấy logger.

Sử dụng::

    from src.core.logger import configure_logging, get_logger

    configure_logging("DEBUG")
    logger = get_logger(__name__)
    logger.info("pipeline_started", law_id="BLDS_2015")
"""

from __future__ import annotations

import structlog
import logging

def configure_logging(log_level: str = "INFO") -> None:
    # Chuyển chuỗi (VD: "INFO") thành hằng số integer của logging
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level), # Dùng numeric_level ở đây để filter log
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Tạo logger cho một module cụ thể.

    Args:
        name: Tên module, thường truyền ``__name__``.

    Returns:
        BoundLogger: Logger instance với tên module đã bind.
    """
    return structlog.get_logger(name)
