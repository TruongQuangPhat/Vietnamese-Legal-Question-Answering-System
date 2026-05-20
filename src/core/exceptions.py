"""VnLaw-QA custom exceptions.

This module defines exception classes for different error scenarios
in the crawler, registry, and storage components.
"""

from __future__ import annotations


class VnLawError(Exception):
    """Base exception for all VnLaw-QA errors."""

    pass


class TrustedDomainError(VnLawError):
    """Raised when attempting to crawl from an untrusted domain.

    The crawler only allows thuvienphapluat.vn by default.
    This exception is raised when a URL from a different domain
    is encountered during validation.

    Attributes:
        url: The URL that failed validation.
        expected_domain: The expected trusted domain.
    """

    def __init__(self, url: str, expected_domain: str = "thuvienphapluat.vn"):
        self.url = url
        self.expected_domain = expected_domain
        message = f"URL '{url}' is not from trusted domain '{expected_domain}'"
        super().__init__(message)


class RegistryError(VnLawError):
    """Raised when there is an error loading or validating the registry.

    This exception is raised when:
    - The registry file does not exist or is not valid YAML
    - A registry entry is missing required fields
    - A pending entry has no URL specified

    Attributes:
        message: Error description.
        law_id: Optional law_id that caused the error.
    """

    def __init__(self, message: str, law_id: str | None = None):
        self.message = message
        self.law_id = law_id
        if law_id:
            super().__init__(f"[{law_id}] {message}")
        else:
            super().__init__(message)


class CrawlError(VnLawError):
    """Raised when a crawl operation fails.

    This exception is raised when:
    - Network requests fail after all retries
    - The server returns an error status
    - Content cannot be saved to disk

    Attributes:
        message: Error description.
        url: The URL that failed.
        law_id: Optional law_id associated with the crawl.
        http_status: Optional HTTP status code.
        retry_count: Number of retry attempts made.
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        law_id: str | None = None,
        http_status: int | None = None,
        retry_count: int = 0,
    ):
        self.url = url
        self.law_id = law_id
        self.http_status = http_status
        self.retry_count = retry_count

        parts = [message]
        if url:
            parts.append(f"URL: {url}")
        if law_id:
            parts.append(f"Law ID: {law_id}")
        if http_status:
            parts.append(f"HTTP Status: {http_status}")
        if retry_count:
            parts.append(f"Retry attempts: {retry_count}")

        super().__init__(" | ".join(parts))


class StorageError(VnLawError):
    """Raised when there is an error writing raw artifacts.

    This exception is raised when:
    - The output directory does not exist or is not writable
    - Content cannot be saved to disk
    - Metadata serialization fails

    Attributes:
        message: Error description.
        path: Optional path that caused the error.
    """

    def __init__(self, message: str, path: str | None = None):
        self.path = path
        if path:
            super().__init__(f"[{path}] {message}")
        else:
            super().__init__(message)
