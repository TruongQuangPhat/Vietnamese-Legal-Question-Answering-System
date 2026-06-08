"""Read-only validation for Phase 6 legal chunks."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from src.processing.legal_chunk_models import (
    ChunkingIssue,
    ChunkingIssueCode,
    ChunkValidationSummary,
    LegalChunk,
)
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalNode,
    LegalNodeLevel,
)


class LegalChunkValidationResult(BaseModel):
    """Result of read-only legal chunk validation.

    Attributes:
        is_valid: Whether validation found no hard errors.
        validation_summary: Aggregated chunk invariant counters.
        warnings: Non-fatal chunk warnings preserved from chunk creation.
        errors: Hard validation errors that should block JSONL output.
    """

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(...)
    validation_summary: ChunkValidationSummary = Field(default_factory=ChunkValidationSummary)
    warnings: list[ChunkingIssue] = Field(default_factory=list)
    errors: list[ChunkingIssue] = Field(default_factory=list)


class LegalChunkValidator:
    """Validate chunks against their source legal hierarchy document.

    The validator checks chunk IDs, source node references, parent Article
    references, exact source text, parent Article text, offsets, legal levels,
    and parent-child containment. It is read-only and never repairs chunks or
    hierarchy nodes.
    """

    def validate(
        self,
        *,
        document: LegalHierarchyDocument,
        chunks: list[LegalChunk],
    ) -> LegalChunkValidationResult:
        """Validate chunk-level invariants for one hierarchy document.

        Args:
            document: Source legal hierarchy document.
            chunks: Chunks produced from the document.

        Returns:
            Validation result containing warnings, errors, and summary counts.

        Legal assumptions:
            A valid chunk must point back to a real Article, Clause, or Point
            node from the hierarchy. The validator does not create synthetic
            parents or reinterpret legal text.
        """
        nodes_by_id = {node.node_id: node for node in document.nodes}
        summary = ChunkValidationSummary(total_chunks_checked=len(chunks))
        warnings = [warning for chunk in chunks for warning in chunk.warnings]
        errors: list[ChunkingIssue] = []

        self._validate_duplicate_chunk_ids(chunks, errors, summary)
        for chunk in chunks:
            self._validate_chunk(
                document=document,
                chunk=chunk,
                nodes_by_id=nodes_by_id,
                errors=errors,
                summary=summary,
            )

        return LegalChunkValidationResult(
            is_valid=len(errors) == 0,
            validation_summary=summary,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def _validate_duplicate_chunk_ids(
        chunks: list[LegalChunk],
        errors: list[ChunkingIssue],
        summary: ChunkValidationSummary,
    ) -> None:
        """Append duplicate chunk ID errors."""
        counts = Counter(chunk.chunk_id for chunk in chunks)
        for chunk_id, count in sorted(counts.items()):
            if count <= 1:
                continue
            summary.duplicate_chunk_ids += 1
            first = next(chunk for chunk in chunks if chunk.chunk_id == chunk_id)
            errors.append(
                _issue(
                    chunk=first,
                    code=ChunkingIssueCode.DUPLICATE_CHUNK_ID,
                    message="Duplicate chunk_id found.",
                    context={"chunk_id": chunk_id, "count": count},
                )
            )

    def _validate_chunk(
        self,
        *,
        document: LegalHierarchyDocument,
        chunk: LegalChunk,
        nodes_by_id: dict[str, LegalNode],
        errors: list[ChunkingIssue],
        summary: ChunkValidationSummary,
    ) -> None:
        """Validate one chunk against hierarchy nodes."""
        source = nodes_by_id.get(chunk.source_node_id)
        article = nodes_by_id.get(chunk.parent_article_node_id)

        if source is None:
            summary.missing_source_nodes += 1
            errors.append(
                _issue(
                    chunk=chunk,
                    code=ChunkingIssueCode.SOURCE_NODE_NOT_FOUND,
                    message="Chunk source_node_id does not exist in hierarchy.",
                    context={"source_node_id": chunk.source_node_id},
                )
            )
            return

        if article is None or article.level != LegalNodeLevel.ARTICLE:
            summary.invalid_parent_articles += 1
            errors.append(
                _issue(
                    chunk=chunk,
                    code=ChunkingIssueCode.INVALID_PARENT_ARTICLE,
                    message="Chunk parent_article_node_id must reference an Article node.",
                    context={
                        "parent_article_node_id": chunk.parent_article_node_id,
                        "actual_level": article.level.value if article is not None else None,
                    },
                )
            )
            return

        self._validate_levels(chunk, source, errors, summary)
        self._validate_text(chunk, source, article, errors, summary)
        self._validate_offsets(chunk, source, article, errors, summary)
        self._validate_parent_child_relationship(document, chunk, source, article, errors, summary)

    @staticmethod
    def _validate_levels(
        chunk: LegalChunk,
        source: LegalNode,
        errors: list[ChunkingIssue],
        summary: ChunkValidationSummary,
    ) -> None:
        """Validate source node level and chunk level compatibility."""
        if source.level not in {
            LegalNodeLevel.ARTICLE,
            LegalNodeLevel.CLAUSE,
            LegalNodeLevel.POINT,
        } or chunk.level.value != source.level.value:
            summary.invalid_chunk_levels += 1
            errors.append(
                _issue(
                    chunk=chunk,
                    code=ChunkingIssueCode.INVALID_CHUNK_LEVEL,
                    message="Chunk level must match an Article, Clause, or Point source node.",
                    context={
                        "chunk_level": chunk.level.value,
                        "source_level": source.level.value,
                    },
                )
            )

    @staticmethod
    def _validate_text(
        chunk: LegalChunk,
        source: LegalNode,
        article: LegalNode,
        errors: list[ChunkingIssue],
        summary: ChunkValidationSummary,
    ) -> None:
        """Validate chunk text and parent text against hierarchy nodes."""
        if chunk.text != source.text:
            summary.text_mismatches += 1
            errors.append(
                _issue(
                    chunk=chunk,
                    code=ChunkingIssueCode.TEXT_MISMATCH,
                    message="Chunk text must equal source node text.",
                    context={
                        "expected_length": len(source.text),
                        "actual_length": len(chunk.text),
                    },
                )
            )
        if chunk.parent_text != article.text:
            summary.parent_text_mismatches += 1
            errors.append(
                _issue(
                    chunk=chunk,
                    code=ChunkingIssueCode.PARENT_TEXT_MISMATCH,
                    message="Chunk parent_text must equal parent Article text.",
                    context={
                        "parent_article_node_id": article.node_id,
                        "expected_length": len(article.text),
                        "actual_length": len(chunk.parent_text),
                    },
                )
            )

    @staticmethod
    def _validate_offsets(
        chunk: LegalChunk,
        source: LegalNode,
        article: LegalNode,
        errors: list[ChunkingIssue],
        summary: ChunkValidationSummary,
    ) -> None:
        """Validate chunk offsets against source and parent Article nodes."""
        invalid_offset = (
            chunk.start_offset != source.start_offset
            or chunk.end_offset != source.end_offset
            or chunk.article_start_offset != article.start_offset
            or chunk.article_end_offset != article.end_offset
            or chunk.start_offset < article.start_offset
            or chunk.end_offset > article.end_offset
        )
        if not invalid_offset:
            return

        summary.invalid_offsets += 1
        errors.append(
            _issue(
                chunk=chunk,
                code=ChunkingIssueCode.OFFSET_MISMATCH,
                message="Chunk offsets must match source and parent Article nodes.",
                context={
                    "expected_start_offset": source.start_offset,
                    "expected_end_offset": source.end_offset,
                    "expected_article_start_offset": article.start_offset,
                    "expected_article_end_offset": article.end_offset,
                    "actual_start_offset": chunk.start_offset,
                    "actual_end_offset": chunk.end_offset,
                    "actual_article_start_offset": chunk.article_start_offset,
                    "actual_article_end_offset": chunk.article_end_offset,
                },
            )
        )

    @staticmethod
    def _validate_parent_child_relationship(
        document: LegalHierarchyDocument,
        chunk: LegalChunk,
        source: LegalNode,
        article: LegalNode,
        errors: list[ChunkingIssue],
        summary: ChunkValidationSummary,
    ) -> None:
        """Validate that Clause/Point chunks are truly under their Article."""
        if source.level == LegalNodeLevel.ARTICLE:
            if source.node_id != article.node_id:
                summary.invalid_parent_articles += 1
                errors.append(
                    _issue(
                        chunk=chunk,
                        code=ChunkingIssueCode.INVALID_PARENT_ARTICLE,
                        message="Article-level chunk must use itself as parent Article.",
                        context={"source_node_id": source.node_id},
                    )
                )
            return

        if not _is_descendant(document, source, article):
            summary.invalid_parent_articles += 1
            errors.append(
                _issue(
                    chunk=chunk,
                    code=ChunkingIssueCode.INVALID_PARENT_ARTICLE,
                    message="Clause/Point chunk source must descend from parent Article.",
                    context={"parent_article_node_id": article.node_id},
                )
            )

        if source.text not in article.text:
            summary.invalid_offsets += 1
            errors.append(
                _issue(
                    chunk=chunk,
                    code=ChunkingIssueCode.CHILD_OUTSIDE_ARTICLE,
                    message="Clause/Point chunk text must be contained in parent Article text.",
                    context={"parent_article_node_id": article.node_id},
                )
            )


def _is_descendant(
    document: LegalHierarchyDocument,
    source: LegalNode,
    ancestor: LegalNode,
) -> bool:
    """Return whether source reaches ancestor through parent links."""
    nodes_by_id = {node.node_id: node for node in document.nodes}
    current = source
    while current.parent_id is not None:
        if current.parent_id == ancestor.node_id:
            return True
        parent = nodes_by_id.get(current.parent_id)
        if parent is None:
            return False
        current = parent
    return False


def _issue(
    *,
    chunk: LegalChunk,
    code: ChunkingIssueCode,
    message: str,
    context: dict[str, object],
) -> ChunkingIssue:
    """Build a structured validator issue for one chunk."""
    return ChunkingIssue(
        code=code,
        message=message,
        law_id=chunk.law_id,
        chunk_id=chunk.chunk_id,
        source_node_id=chunk.source_node_id,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
        context=context,
    )
