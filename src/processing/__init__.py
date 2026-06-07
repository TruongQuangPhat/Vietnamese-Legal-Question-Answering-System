"""Legal text processing components for VnLaw-QA."""

from __future__ import annotations

from src.processing.legal_chunk_models import (
    ChunkingIssue,
    ChunkingIssueCode,
    ChunkingLevel,
    ChunkingMetadata,
    ChunkingReport,
    ChunkingStatus,
    ChunkingSummary,
    ChunkValidationSummary,
    LegalChunk,
)
from src.processing.legal_chunk_validator import LegalChunkValidationResult, LegalChunkValidator
from src.processing.legal_chunker import CHUNK_SCHEMA_VERSION, CHUNKER_VERSION, LegalChunker
from src.processing.legal_heading_recognizer import LegalHeadingRecognizer, RecognizedHeading
from src.processing.legal_hierarchy_builder import (
    HierarchyBuildResult,
    LegalHierarchyBuilder,
    LegalHierarchyBuildError,
)
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
    LegalParsingReport,
    LegalParsingResult,
    LegalParsingStatus,
    ParsingIssueCode,
    StructuredParsingIssue,
    ValidationSummary,
)
from src.processing.legal_parser import (
    LegalParser,
    LegalParserExecutionResult,
    LegalParserRecognitionSummary,
)
from src.processing.legal_span_segmenter import (
    LegalSpanSegmenter,
    SegmentedLegalUnit,
    SpanSegmentationResult,
)
from src.processing.legal_tree_validator import LegalTreeValidationResult, LegalTreeValidator
from src.processing.normalized_input import (
    NormalizedInputLoadResult,
    NormalizedLegalArtifact,
    compare_cleaned_text,
    load_normalized_artifact,
    load_normalized_input,
)

__all__ = [
    "ChunkingIssue",
    "ChunkingIssueCode",
    "ChunkingLevel",
    "ChunkingMetadata",
    "ChunkingReport",
    "ChunkingStatus",
    "ChunkingSummary",
    "ChunkValidationSummary",
    "CHUNKER_VERSION",
    "CHUNK_SCHEMA_VERSION",
    "LegalChunk",
    "LegalChunkValidationResult",
    "LegalChunkValidator",
    "LegalChunker",
    "LegalHeadingRecognizer",
    "LegalHierarchyBuildError",
    "LegalHierarchyBuilder",
    "LegalHierarchyDocument",
    "LegalHierarchyMetadata",
    "LegalNode",
    "LegalNodeLevel",
    "LegalParser",
    "LegalParserExecutionResult",
    "LegalParserRecognitionSummary",
    "LegalParsingReport",
    "LegalParsingResult",
    "LegalParsingStatus",
    "LegalSpanSegmenter",
    "LegalTreeValidationResult",
    "LegalTreeValidator",
    "HierarchyBuildResult",
    "NormalizedInputLoadResult",
    "NormalizedLegalArtifact",
    "ParsingIssueCode",
    "RecognizedHeading",
    "SegmentedLegalUnit",
    "SpanSegmentationResult",
    "StructuredParsingIssue",
    "ValidationSummary",
    "compare_cleaned_text",
    "load_normalized_artifact",
    "load_normalized_input",
]
