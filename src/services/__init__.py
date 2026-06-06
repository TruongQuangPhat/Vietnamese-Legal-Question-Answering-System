"""Service-layer orchestration components for VnLaw-QA."""

from __future__ import annotations

from src.services.legal_parsing_service import (
    DiscoveredNormalizedInput,
    LegalParsingService,
    LegalParsingServiceError,
    LegalParsingServiceResult,
    discover_normalized_inputs,
    write_hierarchy_document,
    write_parsing_report,
)

__all__ = [
    "DiscoveredNormalizedInput",
    "LegalParsingService",
    "LegalParsingServiceError",
    "LegalParsingServiceResult",
    "discover_normalized_inputs",
    "write_hierarchy_document",
    "write_parsing_report",
]
