"""Legal text processing components for VnLaw-QA."""

from __future__ import annotations

from src.processing.legal_heading_recognizer import LegalHeadingRecognizer, RecognizedHeading
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
from src.processing.normalized_input import (
    NormalizedInputLoadResult,
    NormalizedLegalArtifact,
    compare_cleaned_text,
    load_normalized_artifact,
    load_normalized_input,
)

__all__ = [
    "LegalHeadingRecognizer",
    "LegalHierarchyDocument",
    "LegalHierarchyMetadata",
    "LegalNode",
    "LegalNodeLevel",
    "LegalParsingReport",
    "LegalParsingResult",
    "LegalParsingStatus",
    "NormalizedInputLoadResult",
    "NormalizedLegalArtifact",
    "ParsingIssueCode",
    "RecognizedHeading",
    "StructuredParsingIssue",
    "ValidationSummary",
    "compare_cleaned_text",
    "load_normalized_artifact",
    "load_normalized_input",
]
