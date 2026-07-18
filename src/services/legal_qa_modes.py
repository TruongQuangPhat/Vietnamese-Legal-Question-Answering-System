"""Lightweight Legal QA runtime mode enums.

This module intentionally has no retrieval, embedding, Qdrant, or LLM imports
so API startup and liveness checks can inspect runtime mode without loading the
heavy RAG workflow.
"""

from __future__ import annotations

from enum import StrEnum


class LegalQAServiceMode(StrEnum):
    """Runtime mode for the Legal QA API service."""

    FAKE = "fake"
    REAL = "real"


class LegalQARetrievalMode(StrEnum):
    """Real-mode retrieval strategy supported by the production API."""

    HYBRID = "hybrid"
    SPARSE = "sparse"
