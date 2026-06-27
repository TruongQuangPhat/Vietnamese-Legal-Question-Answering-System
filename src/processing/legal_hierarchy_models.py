"""Canonical schemas for legal hierarchy parsing.

The models in this module describe external legal hierarchy parsing data contracts, not the
full parser implementation. They preserve Vietnamese legal hierarchy metadata
and structured issue reporting without writing parser artifacts by themselves.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LegalNodeLevel(StrEnum):
    """Allowed Vietnamese legal hierarchy node levels."""

    LAW = "law"
    PART = "part"
    CHAPTER = "chapter"
    SECTION = "section"
    ARTICLE = "article"
    CLAUSE = "clause"
    POINT = "point"


class ParsingIssueCode(StrEnum):
    """Stable warning and error codes emitted by legal hierarchy parsing components."""

    NO_ARTICLES_FOUND = "NO_ARTICLES_FOUND"
    INVALID_TREE = "INVALID_TREE"
    INVALID_OFFSET = "INVALID_OFFSET"
    TEXT_OFFSET_MISMATCH = "TEXT_OFFSET_MISMATCH"
    ORPHAN_NODE = "ORPHAN_NODE"
    PARENT_CYCLE = "PARENT_CYCLE"
    UNRESOLVED_DUPLICATE_NODE_ID = "UNRESOLVED_DUPLICATE_NODE_ID"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    GLOBAL_INPUT_OR_OUTPUT_FAILURE = "GLOBAL_INPUT_OR_OUTPUT_FAILURE"
    ARTICLE_COUNT_MISMATCH = "ARTICLE_COUNT_MISMATCH"
    MAX_ARTICLE_NUMBER_MISMATCH = "MAX_ARTICLE_NUMBER_MISMATCH"
    NODE_ID_COLLISION_RESOLVED = "NODE_ID_COLLISION_RESOLVED"
    POINT_LIKE_LINE_OUTSIDE_CLAUSE = "POINT_LIKE_LINE_OUTSIDE_CLAUSE"
    AMBIGUOUS_CLAUSE_CANDIDATE = "AMBIGUOUS_CLAUSE_CANDIDATE"
    CLEANED_TEXT_MISMATCH = "CLEANED_TEXT_MISMATCH"
    UNUSUAL_HEADING_PATTERN = "UNUSUAL_HEADING_PATTERN"
    TRAILING_UNCLASSIFIED_TEXT = "TRAILING_UNCLASSIFIED_TEXT"
    SOURCE_NOTE_EXCLUDED = "SOURCE_NOTE_EXCLUDED"
    APPENDIX_EXCLUDED = "APPENDIX_EXCLUDED"
    MISSING_ARTICLE_1 = "MISSING_ARTICLE_1"
    EMPTY_ARTICLE_NODE = "EMPTY_ARTICLE_NODE"


class LegalParsingStatus(StrEnum):
    """Per-law batch parsing result statuses."""

    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    FAILED = "failed"


class StructuredParsingIssue(BaseModel):
    """Machine-readable parser warning or error.

    Attributes:
        code: Stable issue code for downstream report aggregation.
        message: Human-readable explanation of the issue.
        law_id: Law identifier associated with the issue.
        node_id: Optional hierarchy node identifier, when available.
        start_offset: Optional inclusive source offset for the issue.
        end_offset: Optional exclusive source offset for the issue.
        context: Small structured payload with issue-specific facts.

    Legal assumptions:
        Issues describe deterministic preprocessing conditions only. They do
        not interpret legal meaning or supply legal advice.
    """

    model_config = ConfigDict(extra="forbid")

    code: ParsingIssueCode = Field(..., description="Stable parser issue code")
    message: str = Field(..., min_length=1, description="Human-readable issue message")
    law_id: str = Field(..., description="Stable law identifier")
    node_id: str | None = Field(None, description="Optional affected node ID")
    start_offset: int | None = Field(None, ge=0, description="Inclusive source offset")
    end_offset: int | None = Field(None, ge=0, description="Exclusive source offset")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Small structured issue context",
    )

    @model_validator(mode="after")
    def validate_offsets(self) -> StructuredParsingIssue:
        """Ensure nullable issue offsets are valid when both are present."""
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must be greater than or equal to start_offset")
        return self


class LegalNode(BaseModel):
    """Flat hierarchy node with parent-inclusive source text.

    Attributes:
        node_id: Deterministic node identifier.
        level: Legal hierarchy level.
        number: Legal number or label, null for the root Law node.
        title: Semantic title only, never the complete heading line.
        text: Exact source span text for this node.
        start_offset: Inclusive source offset.
        end_offset: Exclusive source offset.
        parent_id: Parent node identifier, null for root.
        children: Child node identifiers, not nested objects.
        metadata: Small node-specific metadata payload.

    Legal assumptions:
        Parent text intentionally includes descendant text so later citation and
        parent-child chunking can derive Article context without reparsing.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Deterministic node ID")
    level: LegalNodeLevel = Field(..., description="Legal hierarchy level")
    number: str | None = Field(None, description="Legal number or label")
    title: str | None = Field(None, description="Semantic title only")
    text: str = Field(..., description="Exact source text slice")
    start_offset: int = Field(..., ge=0, description="Inclusive source offset")
    end_offset: int = Field(..., ge=0, description="Exclusive source offset")
    parent_id: str | None = Field(None, description="Parent node ID")
    children: list[str] = Field(default_factory=list, description="Child node IDs")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-specific parser metadata",
    )

    @model_validator(mode="after")
    def validate_offset_order(self) -> LegalNode:
        """Validate that offsets can represent a non-empty Python slice."""
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class LegalHierarchyMetadata(BaseModel):
    """Document-level metadata copied from normalized input and cleaning/normalization metrics."""

    model_config = ConfigDict(extra="forbid")

    law_name: str = Field(..., min_length=1, description="Official legal document name")
    source_url: str = Field(..., min_length=1, description="Trusted source URL")
    source_domain: str = Field(..., min_length=1, description="Trusted source domain")
    source_type: str = Field(..., min_length=1, description="Source content type")
    raw_artifact_path: str = Field(..., min_length=1, description="Raw HTML artifact path")
    article_heading_count: int = Field(
        ..., ge=0, description="cleaning/normalization Article heading count"
    )
    max_heading_article_number: int = Field(
        ...,
        ge=0,
        description="cleaning/normalization maximum real Article heading number",
    )
    has_heading_article_1: bool = Field(
        ..., description="Whether cleaning/normalization saw Article 1"
    )
    heading_sequence_score: float = Field(
        ...,
        ge=0.0,
        description="cleaning/normalization Article heading sequence score",
    )


class LegalHierarchyDocument(BaseModel):
    """Canonical per-law `hierarchy.json` contract.

    Legal assumptions:
        This schema stores nodes as a flat list. It validates the root Law node
        contract but leaves full graph validation for the future tree validator.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1, description="Hierarchy schema version")
    parser_version: str = Field(..., min_length=1, description="Parser version")
    cleaner_version: str = Field(..., min_length=1, description="Producing cleaner version")
    law_id: str = Field(..., min_length=1, description="Stable law identifier")
    source_file: str = Field(..., min_length=1, description="Exact normalized input path")
    root_node_id: str = Field(..., min_length=1, description="Root Law node ID")
    metadata: LegalHierarchyMetadata = Field(..., description="Document-level metadata")
    warnings: list[StructuredParsingIssue] = Field(
        default_factory=list,
        description="Document-level non-fatal parser warnings",
    )
    nodes: list[LegalNode] = Field(..., description="Flat LegalNode list")

    @model_validator(mode="after")
    def validate_root_contract(self) -> LegalHierarchyDocument:
        """Validate the root Law node invariants required by legal hierarchy parsing."""
        root_nodes = [node for node in self.nodes if node.level == LegalNodeLevel.LAW]
        if len(root_nodes) != 1:
            raise ValueError("hierarchy must contain exactly one root Law node")

        root = root_nodes[0]
        if root.node_id != self.root_node_id:
            raise ValueError("root_node_id must point to the root Law node")
        if root.parent_id is not None:
            raise ValueError("root parent_id must be null")
        if root.number is not None:
            raise ValueError("root number must be null")
        if root.start_offset != 0:
            raise ValueError("root start_offset must be 0")
        if root.end_offset != len(root.text):
            raise ValueError("root end_offset must equal len(root.text)")
        return self


class ValidationSummary(BaseModel):
    """Aggregated structural validation counters for parsing reports."""

    model_config = ConfigDict(extra="forbid")

    missing_article_1: int = Field(0, ge=0)
    article_heading_mismatch: int = Field(0, ge=0)
    orphan_nodes: int = Field(0, ge=0)
    invalid_parent_chain: int = Field(0, ge=0)
    invalid_offsets: int = Field(0, ge=0)
    invalid_sibling_overlap: int = Field(0, ge=0)
    empty_article_nodes: int = Field(0, ge=0)
    duplicate_node_ids: int = Field(0, ge=0)


class LegalParsingResult(BaseModel):
    """Per-law entry in `legal_parsing_report.json`."""

    model_config = ConfigDict(extra="forbid")

    law_id: str = Field(..., min_length=1)
    status: LegalParsingStatus = Field(...)
    input_path: str = Field(..., min_length=1)
    output_path: str | None = Field(None)
    duration_seconds: float = Field(..., ge=0.0)
    node_count: int = Field(..., ge=0)
    counts_by_level: dict[str, int] = Field(default_factory=dict)
    has_article_1: bool = Field(...)
    max_article_number: int = Field(..., ge=0)
    expected_article_heading_count: int = Field(..., ge=0)
    article_heading_count_matches: bool = Field(...)
    expected_max_heading_article_number: int = Field(..., ge=0)
    max_article_number_matches: bool = Field(...)
    warnings: list[StructuredParsingIssue] = Field(default_factory=list)
    errors: list[StructuredParsingIssue] = Field(default_factory=list)


class LegalParsingReport(BaseModel):
    """Canonical batch `legal_parsing_report.json` schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1)
    parser_version: str = Field(..., min_length=1)
    started_at: str = Field(..., min_length=1)
    finished_at: str = Field(..., min_length=1)
    duration_seconds: float = Field(..., ge=0.0)
    input_dir: str = Field(..., min_length=1)
    output_dir: str = Field(..., min_length=1)
    total_documents: int = Field(..., ge=0)
    successful: int = Field(..., ge=0)
    success_with_warnings: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    nodes_by_level: dict[str, int] = Field(default_factory=dict)
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    results: list[LegalParsingResult] = Field(default_factory=list)
    warnings: list[StructuredParsingIssue] = Field(default_factory=list)
    errors: list[StructuredParsingIssue] = Field(default_factory=list)
