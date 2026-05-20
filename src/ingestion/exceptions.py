"""Ingestion-specific exceptions.

This module defines exception classes specific to the ingestion pipeline.
"""

from __future__ import annotations


class IngestionError(Exception):
    """Base exception for ingestion pipeline errors."""

    pass


class CrawlSelectionError(IngestionError):
    """Raised when there is an error selecting crawl targets.

    This exception is raised when:
    - Selection filters are invalid
    - No targets match the selection criteria
    - Selection conflicts are detected

    Attributes:
        message: Error description.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CrawlStatusError(IngestionError):
    """Raised when there is an error updating crawl status.

    This exception is raised when:
    - Status update fails due to file system errors
    - Registry update fails

    Attributes:
        message: Error description.
        law_id: Optional law_id associated with the error.
    """

    def __init__(self, message: str, law_id: str | None = None):
        self.law_id = law_id
        if law_id:
            super().__init__(f"[{law_id}] {message}")
        else:
            super().__init__(message)
