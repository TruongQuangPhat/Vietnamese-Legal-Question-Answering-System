"""Build canonical legal hierarchy nodes from segmented legal units."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.processing.legal_heading_recognizer import CandidateClassification
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
    ParsingIssueCode,
    StructuredParsingIssue,
)
from src.processing.legal_span_segmenter import SegmentedLegalUnit

SCHEMA_VERSION = "1.0"
PARSER_VERSION = "v0.1.0"

_ROMAN_NUMBER_RE = re.compile(r"^[ivxlc]+$", re.IGNORECASE)


class LegalHierarchyBuildError(ValueError):
    """Raised when segmented units cannot be safely converted into a hierarchy."""


class HierarchyBuildResult(BaseModel):
    """Result of deterministic hierarchy construction.

    Attributes:
        document: Canonical hierarchy document containing root, flat nodes, and
            non-fatal warnings produced or inherited during construction.
    """

    model_config = ConfigDict(extra="forbid")

    document: LegalHierarchyDocument = Field(...)

    @property
    def warnings(self) -> list[StructuredParsingIssue]:
        """Return canonical document warnings without duplicating storage."""
        return self.document.warnings


class LegalHierarchyBuilder:
    """Build flat legal hierarchy nodes from already segmented legal units.

    The builder does not read files, recognize headings, segment spans, write
    artifacts, or perform full tree validation. It creates the root Law node,
    assigns deterministic parents from active legal context, generates stable
    hierarchy-path node IDs, and records recoverable ID collision warnings.
    """

    def build(
        self,
        *,
        law_id: str,
        law_name: str,
        normalized_text: str,
        source_file: str,
        cleaner_version: str,
        metadata: LegalHierarchyMetadata,
        segmented_units: list[SegmentedLegalUnit],
        inherited_warnings: list[StructuredParsingIssue] | None = None,
    ) -> HierarchyBuildResult:
        """Build a canonical hierarchy document from segmented legal units.

        Args:
            law_id: Stable law identifier used in every deterministic node ID.
            law_name: Official legal document name used as root title.
            normalized_text: Exact authoritative source text.
            source_file: Path to the normalized artifact consumed by the caller.
            cleaner_version: Cleaner version copied from normalized input.
            metadata: Document-level hierarchy metadata.
            segmented_units: Already-segmented certain legal units in or out of
                source order.
            inherited_warnings: Optional structured warnings from earlier
                parser steps to preserve in the resulting document.

        Returns:
            A hierarchy build result containing the canonical document.

        Raises:
            LegalHierarchyBuildError: If local parent assignment or ID
                construction would produce an invalid hierarchy.

        Legal assumptions:
            All offsets and node text come from `segmented_units`, which must
            already reference the immutable `normalized_text` source string.
        """
        warnings = list(inherited_warnings or [])
        root_node_id = f"{law_id}__root"
        root = LegalNode(
            node_id=root_node_id,
            level=LegalNodeLevel.LAW,
            number=None,
            title=law_name,
            text=normalized_text,
            start_offset=0,
            end_offset=len(normalized_text),
            parent_id=None,
            children=[],
            metadata={},
        )
        nodes: list[LegalNode] = [root]
        nodes_by_id: dict[str, LegalNode] = {root.node_id: root}
        active: dict[LegalNodeLevel, LegalNode] = {LegalNodeLevel.LAW: root}
        base_id_counts: dict[str, int] = {}

        for unit in sorted(segmented_units, key=lambda item: (item.start_offset, item.end_offset)):
            if unit.classification != CandidateClassification.CERTAIN:
                raise LegalHierarchyBuildError("Hierarchy builder only accepts certain units")

            parent = self._select_parent(unit, active)
            self._assert_parent_contains_child(parent, unit)
            base_node_id = self._base_node_id(parent.node_id, unit)
            node_id, collision_warning = self._resolve_node_id(
                base_node_id=base_node_id,
                existing_node_ids=nodes_by_id,
                occurrence_counts=base_id_counts,
                law_id=law_id,
                parent_id=parent.node_id,
                unit=unit,
            )
            if collision_warning is not None:
                warnings.append(collision_warning)

            node = self._build_node(unit=unit, node_id=node_id, parent_id=parent.node_id)
            parent.children.append(node.node_id)
            nodes.append(node)
            nodes_by_id[node.node_id] = node
            self._update_active_context(active, node)

        if len(nodes_by_id) != len(nodes):
            raise LegalHierarchyBuildError("Resolved node IDs are not unique")

        document = LegalHierarchyDocument(
            schema_version=SCHEMA_VERSION,
            parser_version=PARSER_VERSION,
            cleaner_version=cleaner_version,
            law_id=law_id,
            source_file=source_file,
            root_node_id=root_node_id,
            metadata=metadata,
            warnings=warnings,
            nodes=nodes,
        )
        return HierarchyBuildResult(document=document)

    def _select_parent(
        self,
        unit: SegmentedLegalUnit,
        active: dict[LegalNodeLevel, LegalNode],
    ) -> LegalNode:
        """Select the nearest structurally valid active parent for a unit."""
        if unit.level == LegalNodeLevel.PART:
            return active[LegalNodeLevel.LAW]
        if unit.level == LegalNodeLevel.CHAPTER:
            return active.get(LegalNodeLevel.PART, active[LegalNodeLevel.LAW])
        if unit.level == LegalNodeLevel.SECTION:
            return (
                active.get(LegalNodeLevel.CHAPTER)
                or active.get(LegalNodeLevel.PART)
                or active[LegalNodeLevel.LAW]
            )
        if unit.level == LegalNodeLevel.ARTICLE:
            return (
                active.get(LegalNodeLevel.SECTION)
                or active.get(LegalNodeLevel.CHAPTER)
                or active.get(LegalNodeLevel.PART)
                or active[LegalNodeLevel.LAW]
            )
        if unit.level == LegalNodeLevel.CLAUSE:
            parent = active.get(LegalNodeLevel.ARTICLE)
            if parent is None:
                raise LegalHierarchyBuildError("Clause requires an active Article parent")
            return parent
        if unit.level == LegalNodeLevel.POINT:
            parent = active.get(LegalNodeLevel.CLAUSE)
            if parent is None:
                raise LegalHierarchyBuildError("Point requires an active Clause parent")
            return parent

        raise LegalHierarchyBuildError(f"Unsupported legal unit level: {unit.level}")

    @staticmethod
    def _assert_parent_contains_child(parent: LegalNode, unit: SegmentedLegalUnit) -> None:
        """Ensure local parent assignment is compatible with segmented spans."""
        if parent.start_offset <= unit.start_offset and unit.end_offset <= parent.end_offset:
            return
        raise LegalHierarchyBuildError(
            f"Selected parent {parent.node_id} does not contain child span "
            f"{unit.start_offset}:{unit.end_offset}"
        )

    def _base_node_id(self, parent_node_id: str, unit: SegmentedLegalUnit) -> str:
        """Build the non-collision-resolved base node ID for a unit."""
        if unit.number is None:
            raise LegalHierarchyBuildError(f"{unit.level.value} unit is missing a legal number")
        number_token = normalize_number_for_node_id(unit.level, unit.number)
        return f"{parent_node_id}__{unit.level.value}_{number_token}"

    def _resolve_node_id(
        self,
        *,
        base_node_id: str,
        existing_node_ids: dict[str, LegalNode],
        occurrence_counts: dict[str, int],
        law_id: str,
        parent_id: str,
        unit: SegmentedLegalUnit,
    ) -> tuple[str, StructuredParsingIssue | None]:
        """Resolve deterministic sibling ID collisions and build warnings."""
        occurrence = occurrence_counts.get(base_node_id, 0) + 1
        occurrence_counts[base_node_id] = occurrence
        resolved_node_id = base_node_id if occurrence == 1 else f"{base_node_id}__occurrence_{occurrence}"

        if resolved_node_id in existing_node_ids:
            raise LegalHierarchyBuildError("Duplicate node ID could not be resolved deterministically")
        if occurrence == 1:
            return resolved_node_id, None

        return resolved_node_id, StructuredParsingIssue(
            code=ParsingIssueCode.NODE_ID_COLLISION_RESOLVED,
            message="Sibling node ID collision resolved with deterministic occurrence suffix.",
            law_id=law_id,
            node_id=resolved_node_id,
            start_offset=unit.start_offset,
            end_offset=unit.end_offset,
            context={
                "base_node_id": base_node_id,
                "resolved_node_id": resolved_node_id,
                "occurrence": occurrence,
                "level": unit.level.value,
                "number": unit.number,
                "parent_id": parent_id,
            },
        )

    @staticmethod
    def _build_node(
        *,
        unit: SegmentedLegalUnit,
        node_id: str,
        parent_id: str,
    ) -> LegalNode:
        """Create a canonical `LegalNode` from one segmented unit."""
        metadata: dict[str, Any] = {
            "heading_text": unit.heading_text,
            "heading_start_offset": unit.heading_start_offset,
            "heading_end_offset": unit.heading_end_offset,
            "line_number": unit.line_number,
            "recognition_classification": unit.classification.value,
        }
        if unit.footnote is not None:
            metadata["footnote"] = unit.footnote

        return LegalNode(
            node_id=node_id,
            level=unit.level,
            number=unit.number,
            title=unit.title,
            text=unit.text,
            start_offset=unit.start_offset,
            end_offset=unit.end_offset,
            parent_id=parent_id,
            children=[],
            metadata=metadata,
        )

    @staticmethod
    def _update_active_context(
        active: dict[LegalNodeLevel, LegalNode],
        node: LegalNode,
    ) -> None:
        """Update active structural context after adding a source-ordered node."""
        if node.level == LegalNodeLevel.PART:
            _clear_active(active, LegalNodeLevel.CHAPTER, LegalNodeLevel.SECTION)
            _clear_active(active, LegalNodeLevel.ARTICLE, LegalNodeLevel.CLAUSE)
            active[LegalNodeLevel.PART] = node
            return

        if node.level == LegalNodeLevel.CHAPTER:
            _clear_active(active, LegalNodeLevel.SECTION, LegalNodeLevel.ARTICLE)
            _clear_active(active, LegalNodeLevel.CLAUSE)
            active[LegalNodeLevel.CHAPTER] = node
            return

        if node.level == LegalNodeLevel.SECTION:
            _clear_active(active, LegalNodeLevel.ARTICLE, LegalNodeLevel.CLAUSE)
            active[LegalNodeLevel.SECTION] = node
            return

        if node.level == LegalNodeLevel.ARTICLE:
            _clear_active(active, LegalNodeLevel.CLAUSE)
            active[LegalNodeLevel.ARTICLE] = node
            return

        if node.level == LegalNodeLevel.CLAUSE:
            active[LegalNodeLevel.CLAUSE] = node


def normalize_number_for_node_id(level: LegalNodeLevel, number: str) -> str:
    """Normalize a legal display number into a deterministic node-ID token.

    Args:
        level: Legal hierarchy level for context-sensitive normalization.
        number: Original legal number or label from the source document.

    Returns:
        Filesystem-safe hierarchy ID token that preserves legal distinctions.

    Raises:
        LegalHierarchyBuildError: If the number cannot produce a non-empty ID
            token.
    """
    raw = number.strip()
    if not raw:
        raise LegalHierarchyBuildError("Legal number cannot be empty")

    if level == LegalNodeLevel.CHAPTER and _ROMAN_NUMBER_RE.fullmatch(raw):
        return raw.upper()

    if level == LegalNodeLevel.PART:
        raw = raw.lower()
    elif level in {LegalNodeLevel.ARTICLE, LegalNodeLevel.POINT}:
        raw = raw.lower()

    token = _remove_vietnamese_tone_marks(raw)
    token = token.replace("/", "_").replace("\\", "_")
    token = re.sub(r"\s+", "_", token)
    token = re.sub(r"[^0-9A-Za-z_đĐ-]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")

    if not token:
        raise LegalHierarchyBuildError(f"Could not normalize {level.value} number for node ID")
    return token


def _remove_vietnamese_tone_marks(text: str) -> str:
    """Remove combining tone marks while preserving Vietnamese `đ`."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def _clear_active(
    active: dict[LegalNodeLevel, LegalNode],
    *levels: LegalNodeLevel,
) -> None:
    """Remove active contexts for levels that cannot contain the next node."""
    for level in levels:
        active.pop(level, None)
