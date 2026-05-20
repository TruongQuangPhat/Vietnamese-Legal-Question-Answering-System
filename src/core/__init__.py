"""VnLaw-QA core module.

This module contains core infrastructure components:
- Custom exceptions for the application
- Configuration management via Pydantic Settings
"""

from __future__ import annotations

from .config import Settings
from .exceptions import (
    CrawlError,
    RegistryError,
    TrustedDomainError,
)

__all__ = [
    "CrawlError",
    "RegistryError",
    "TrustedDomainError",
    "Settings",
]
