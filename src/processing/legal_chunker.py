"""Deterministic parent-child chunk selection.

This module converts one already-validated legal hierarchy document
into in-memory parent-child chunking chunks. It does not discover files, write JSONL,
validate corpus-wide uniqueness, generate embeddings, or repair legal text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.processing.legal_chunk_models import (
    ChunkingIssue,
    ChunkingIssueCode,
    ChunkingLevel,
    ChunkingMetadata,
    LegalChunk,
)
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalNode,
    LegalNodeLevel,
    ParsingIssueCode,
    StructuredParsingIssue,
)

CHUNK_SCHEMA_VERSION = "1.0"
CHUNKER_VERSION = "v0.1.0"


class LegalChunker:
    """Create parent-child chunks from one canonical legal hierarchy document.

    The chunker uses the final deterministic legal hierarchy parsing node IDs directly. It
    selects Article fallback chunks, Clause chunks, or Point chunks according
    to the parent-child policy, while preserving each chunk's parent Article
    text and offsets for downstream retrieval and citation validation.
    """

    def chunk_document(
        self,
        document: LegalHierarchyDocument,
        *,
        source_file: str | None = None,
    ) -> list[LegalChunk]:
        """Convert a legal hierarchy document into deterministic chunks.

        Args:
            document: Parsed legal hierarchy document to chunk.
            source_file: Optional path to the source `hierarchy.json`; when
                omitted, `document.source_file` is used.

        Returns:
            Legal chunks in deterministic source order.

        Legal assumptions:
            The method never reparses root text and never creates synthetic
            legal nodes. Only real Article, Clause, and Point nodes from the
            hierarchy may become chunks.
        """
        nodes_by_id = {node.node_id: node for node in document.nodes}
        chunks: list[LegalChunk] = []

        for article in _ordered_nodes(
            node for node in document.nodes if node.level == LegalNodeLevel.ARTICLE
        ):
            clauses = self._child_nodes(
                article,
                nodes_by_id,
                expected_level=LegalNodeLevel.CLAUSE,
            )
            if not clauses:
                chunks.append(
                    self._build_chunk(
                        document=document,
                        source=article,
                        article=article,
                        clause=None,
                        source_file=source_file,
                    )
                )
                continue

            for clause in clauses:
                points = self._child_nodes(
                    clause,
                    nodes_by_id,
                    expected_level=LegalNodeLevel.POINT,
                )
                if not points:
                    chunks.append(
                        self._build_chunk(
                            document=document,
                            source=clause,
                            article=article,
                            clause=clause,
                            source_file=source_file,
                        )
                    )
                    continue

                for point in points:
                    chunks.append(
                        self._build_chunk(
                            document=document,
                            source=point,
                            article=article,
                            clause=clause,
                            source_file=source_file,
                        )
                    )

        return chunks

    @staticmethod
    def _child_nodes(
        parent: LegalNode,
        nodes_by_id: dict[str, LegalNode],
        *,
        expected_level: LegalNodeLevel,
    ) -> list[LegalNode]:
        """Return direct child nodes of the expected level in source order."""
        children = [
            nodes_by_id[child_id]
            for child_id in parent.children
            if child_id in nodes_by_id and nodes_by_id[child_id].level == expected_level
        ]
        return _ordered_nodes(children)

    def _build_chunk(
        self,
        *,
        document: LegalHierarchyDocument,
        source: LegalNode,
        article: LegalNode,
        clause: LegalNode | None,
        source_file: str | None,
    ) -> LegalChunk:
        """Build one schema-valid chunk from an Article, Clause, or Point node."""
        level = ChunkingLevel(source.level.value)
        is_source_unit_repealed = _is_repealed_placeholder_text(source.text)
        is_empty_or_repealed = self._is_empty_or_repealed(
            document,
            article,
            source,
        )
        metadata = ChunkingMetadata(
            is_empty_or_repealed=is_empty_or_repealed,
            is_source_unit_repealed=is_source_unit_repealed,
            source_warnings=_source_warning_codes(document.warnings, source, article),
            caveat_references=_source_caveat_references(document.warnings, source, article),
        )
        chunk = LegalChunk(
            schema_version=CHUNK_SCHEMA_VERSION,
            chunker_version=CHUNKER_VERSION,
            chunk_id=f"{source.node_id}__chunk",
            law_id=document.law_id,
            law_name=document.metadata.law_name,
            source_url=document.metadata.source_url,
            source_domain=document.metadata.source_domain,
            source_type=document.metadata.source_type,
            source_file=source_file or document.source_file,
            level=level,
            chunk_kind=_chunk_kind(level, is_empty_or_repealed),
            source_node_id=source.node_id,
            parent_article_node_id=article.node_id,
            parent_chunk_id=f"{article.node_id}__parent",
            article_number=article.number,
            article_title=article.title,
            clause_number=clause.number if clause is not None else None,
            point_label=source.number if source.level == LegalNodeLevel.POINT else None,
            citation=_citation(
                law_name=document.metadata.law_name,
                article=article,
                clause=clause,
                source=source,
            ),
            hierarchy_path=_hierarchy_path(document, source),
            text=source.text,
            parent_text=article.text,
            start_offset=source.start_offset,
            end_offset=source.end_offset,
            article_start_offset=article.start_offset,
            article_end_offset=article.end_offset,
            metadata=metadata,
            warnings=[
                *_chunk_warnings(document, source, article, is_empty_or_repealed),
                *_source_integrity_warnings(document, source, article),
            ],
        )
        return chunk.compute_hashes()

    @staticmethod
    def _is_empty_or_repealed(
        document: LegalHierarchyDocument,
        article: LegalNode,
        source: LegalNode,
    ) -> bool:
        """Return whether an Article should be flagged as empty/repealed."""
        if _is_repealed_placeholder_text(source.text):
            return True
        if _is_repealed_placeholder_text(article.text) and source.node_id == article.node_id:
            return True
        if bool(article.metadata.get("is_empty")):
            return True
        if not article.text.strip():
            return True
        return any(
            warning.code == ParsingIssueCode.EMPTY_ARTICLE_NODE
            and warning.node_id == article.node_id
            for warning in document.warnings
        )


def _is_repealed_placeholder_text(text: str) -> bool:
    """Return whether text contains a deterministic repealed placeholder."""
    return (
        re.search(r"\(\s*được\s+bãi\s+bỏ\s*\)", text, re.IGNORECASE) is not None
        or re.search(
            r"\b(?:Điều|Khoản|Điểm)\s+này\s+được\s+bãi\s+bỏ\b",
            text,
            re.IGNORECASE,
        )
        is not None
    )


def _ordered_nodes(nodes: Iterable[LegalNode]) -> list[LegalNode]:
    """Return legal nodes in deterministic source order."""
    return sorted(nodes, key=lambda node: (node.start_offset, node.end_offset, node.node_id))


def _chunk_kind(level: ChunkingLevel, is_empty_or_repealed: bool) -> str:
    """Return the stable descriptive chunk kind for a selected source level."""
    if level == ChunkingLevel.ARTICLE:
        return "article_level_empty" if is_empty_or_repealed else "article_level"
    if level == ChunkingLevel.CLAUSE:
        return "clause_level"
    return "point_level"


def _citation(
    *,
    law_name: str,
    article: LegalNode,
    clause: LegalNode | None,
    source: LegalNode,
) -> str:
    """Build a deterministic Vietnamese citation for a selected source node."""
    article_part = f"Điều {article.number}" if article.number else "Điều"
    if source.level == LegalNodeLevel.POINT:
        point_part = f"Điểm {source.number}" if source.number else "Điểm"
        clause_part = f"Khoản {clause.number}" if clause is not None and clause.number else "Khoản"
        return f"{law_name}, {point_part}, {clause_part}, {article_part}"
    if source.level == LegalNodeLevel.CLAUSE:
        clause_part = f"Khoản {source.number}" if source.number else "Khoản"
        return f"{law_name}, {clause_part}, {article_part}"
    return f"{law_name}, {article_part}"


def _hierarchy_path(document: LegalHierarchyDocument, source: LegalNode) -> str:
    """Build a display path from the real parent chain only.

    Missing intermediate levels remain missing. For example, an Article that is
    attached directly to the root Law node produces `Law / Điều ...` rather than
    a synthetic Part, Chapter, or Section segment.
    """
    nodes_by_id = {node.node_id: node for node in document.nodes}
    chain: list[LegalNode] = []
    current: LegalNode | None = source
    while current is not None:
        chain.append(current)
        current = nodes_by_id.get(current.parent_id) if current.parent_id is not None else None

    segments = [document.metadata.law_name]
    segments.extend(
        _path_segment(document, node)
        for node in reversed(chain)
        if node.level != LegalNodeLevel.LAW
    )
    return " / ".join(segments)


def _path_segment(document: LegalHierarchyDocument, node: LegalNode) -> str:
    """Return one Vietnamese display segment for a real hierarchy node."""
    if node.level == LegalNodeLevel.LAW:
        return document.metadata.law_name
    labels = {
        LegalNodeLevel.PART: "Phần",
        LegalNodeLevel.CHAPTER: "Chương",
        LegalNodeLevel.SECTION: "Mục",
        LegalNodeLevel.ARTICLE: "Điều",
        LegalNodeLevel.CLAUSE: "Khoản",
        LegalNodeLevel.POINT: "Điểm",
    }
    label = labels[node.level]
    number = f" {node.number}" if node.number else ""
    title = f". {node.title}" if node.title else ""
    return f"{label}{number}{title}"


def _source_warning_codes(
    warnings: list[StructuredParsingIssue],
    source: LegalNode,
    article: LegalNode,
) -> list[str]:
    """Return legal hierarchy parsing warning codes that directly affect this chunk."""
    node_ids = {source.node_id, article.node_id}
    return [warning.code.value for warning in warnings if warning.node_id in node_ids]


def _source_caveat_references(
    warnings: list[StructuredParsingIssue],
    source: LegalNode,
    article: LegalNode,
) -> list[str]:
    """Return deterministic source warning references for chunk metadata."""
    node_ids = {source.node_id, article.node_id}
    return [
        f"{warning.code.value}:{warning.node_id}"
        for warning in warnings
        if warning.node_id in node_ids
    ]


def _chunk_warnings(
    document: LegalHierarchyDocument,
    source: LegalNode,
    article: LegalNode,
    is_empty_or_repealed: bool,
) -> list[ChunkingIssue]:
    """Return non-fatal chunk warnings known during selection."""
    if not is_empty_or_repealed or source.node_id != article.node_id:
        return []
    return [
        ChunkingIssue(
            code=ChunkingIssueCode.EMPTY_ARTICLE_CHUNK,
            message="Article-level chunk preserves an empty or repealed Article.",
            law_id=document.law_id,
            chunk_id=f"{source.node_id}__chunk",
            source_node_id=source.node_id,
            start_offset=source.start_offset,
            end_offset=source.end_offset,
            context={"parent_article_node_id": article.node_id},
        )
    ]


def _source_integrity_warnings(
    document: LegalHierarchyDocument,
    source: LegalNode,
    article: LegalNode,
) -> list[ChunkingIssue]:
    """Return source-slicing warnings when root text is available for checking.

    Real legal hierarchy parsing hierarchy documents store root Law text as the complete
    normalized document, which lets parent-child chunking compare chunk offsets against exact
    source slices. Small legacy unit fixtures may not include full root text;
    those are skipped here and will be replaced by validator-focused fixtures
    in later slices.
    """
    root = next(
        (node for node in document.nodes if node.node_id == document.root_node_id),
        None,
    )
    if root is None or source.end_offset > len(root.text) or article.end_offset > len(root.text):
        return []

    warnings: list[ChunkingIssue] = []
    source_slice = root.text[source.start_offset : source.end_offset]
    article_slice = root.text[article.start_offset : article.end_offset]

    if source_slice != source.text:
        warnings.append(
            ChunkingIssue(
                code=ChunkingIssueCode.TEXT_MISMATCH,
                message="Chunk source node text does not match root text slice.",
                law_id=document.law_id,
                chunk_id=f"{source.node_id}__chunk",
                source_node_id=source.node_id,
                start_offset=source.start_offset,
                end_offset=source.end_offset,
                context={
                    "expected_length": len(source_slice),
                    "actual_length": len(source.text),
                },
            )
        )

    if article_slice != article.text:
        warnings.append(
            ChunkingIssue(
                code=ChunkingIssueCode.PARENT_TEXT_MISMATCH,
                message="Parent Article text does not match root text slice.",
                law_id=document.law_id,
                chunk_id=f"{source.node_id}__chunk",
                source_node_id=source.node_id,
                start_offset=article.start_offset,
                end_offset=article.end_offset,
                context={
                    "parent_article_node_id": article.node_id,
                    "expected_length": len(article_slice),
                    "actual_length": len(article.text),
                },
            )
        )

    if (
        source.level in {LegalNodeLevel.CLAUSE, LegalNodeLevel.POINT}
        and source.text not in article.text
    ):
        warnings.append(
            ChunkingIssue(
                code=ChunkingIssueCode.CHILD_OUTSIDE_ARTICLE,
                message="Child chunk text is not contained in parent Article text.",
                law_id=document.law_id,
                chunk_id=f"{source.node_id}__chunk",
                source_node_id=source.node_id,
                start_offset=source.start_offset,
                end_offset=source.end_offset,
                context={"parent_article_node_id": article.node_id},
            )
        )

    return warnings
