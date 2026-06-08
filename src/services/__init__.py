"""Service-layer orchestration components for VnLaw-QA."""

from __future__ import annotations

from src.services.chunking_service import (
    ChunkingService,
    ChunkingServiceError,
    ChunkingServiceResult,
    DiscoveredHierarchyInput,
    discover_hierarchy_inputs,
    load_hierarchy_document,
    write_chunking_report,
    write_legal_chunks_jsonl,
)
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
    "ChunkingService",
    "ChunkingServiceError",
    "ChunkingServiceResult",
    "DiscoveredHierarchyInput",
    "DiscoveredNormalizedInput",
    "LegalParsingService",
    "LegalParsingServiceError",
    "LegalParsingServiceResult",
    "discover_hierarchy_inputs",
    "discover_normalized_inputs",
    "load_hierarchy_document",
    "write_chunking_report",
    "write_hierarchy_document",
    "write_legal_chunks_jsonl",
    "write_parsing_report",
]
