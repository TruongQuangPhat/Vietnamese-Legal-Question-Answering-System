"""Tests for Phase 6 legal chunk validation."""

from __future__ import annotations

from src.processing.legal_chunk_models import ChunkingIssueCode, ChunkingLevel
from src.processing.legal_chunk_validator import LegalChunkValidator
from src.processing.legal_chunker import LegalChunker
from tests.unit.processing.test_legal_chunker import _full_hierarchy_document


def _valid_chunks():
    """Return a full-chain document and its valid chunks."""
    document = _full_hierarchy_document()
    return document, LegalChunker().chunk_document(document)


def test_valid_chunks_pass_validation() -> None:
    """Chunks produced from a valid hierarchy pass chunk validation."""
    document, chunks = _valid_chunks()

    result = LegalChunkValidator().validate(document=document, chunks=chunks)

    assert result.is_valid is True
    assert result.errors == []
    assert result.validation_summary.total_chunks_checked == 1
    assert result.validation_summary.duplicate_chunk_ids == 0
    assert result.validation_summary.invalid_offsets == 0


def test_existing_chunk_warnings_are_preserved_as_warnings() -> None:
    """Validator preserves non-fatal chunk warnings without converting them to errors."""
    document, chunks = _valid_chunks()
    bad_source_nodes = [node.model_copy(deep=True) for node in document.nodes]
    bad_source_nodes[-1].text = "Điểm a. Nội dung bị lệch.\n"
    warning_document = document.model_copy(update={"nodes": bad_source_nodes}, deep=True)
    warning_chunks = LegalChunker().chunk_document(warning_document)

    result = LegalChunkValidator().validate(document=warning_document, chunks=warning_chunks)

    assert result.is_valid is False
    assert [warning.code for warning in result.warnings] == [
        ChunkingIssueCode.TEXT_MISMATCH,
        ChunkingIssueCode.CHILD_OUTSIDE_ARTICLE,
    ]
    assert [error.code for error in result.errors] == [ChunkingIssueCode.CHILD_OUTSIDE_ARTICLE]


def test_duplicate_chunk_id_fails() -> None:
    """Duplicate chunk IDs are hard validation errors."""
    document, chunks = _valid_chunks()
    duplicate = chunks[0].model_copy(deep=True)

    result = LegalChunkValidator().validate(document=document, chunks=[chunks[0], duplicate])

    assert result.is_valid is False
    assert result.validation_summary.duplicate_chunk_ids == 1
    assert [error.code for error in result.errors] == [ChunkingIssueCode.DUPLICATE_CHUNK_ID]


def test_missing_source_node_fails() -> None:
    """A chunk source_node_id must exist in the hierarchy."""
    document, chunks = _valid_chunks()
    chunk = chunks[0].model_copy(update={"source_node_id": "missing_node"}, deep=True)

    result = LegalChunkValidator().validate(document=document, chunks=[chunk])

    assert result.is_valid is False
    assert result.validation_summary.missing_source_nodes == 1
    assert [error.code for error in result.errors] == [ChunkingIssueCode.SOURCE_NODE_NOT_FOUND]


def test_invalid_parent_article_fails() -> None:
    """parent_article_node_id must point to an Article node."""
    document, chunks = _valid_chunks()
    chunk = chunks[0].model_copy(
        update={"parent_article_node_id": document.root_node_id},
        deep=True,
    )

    result = LegalChunkValidator().validate(document=document, chunks=[chunk])

    assert result.is_valid is False
    assert result.validation_summary.invalid_parent_articles == 1
    assert [error.code for error in result.errors] == [ChunkingIssueCode.INVALID_PARENT_ARTICLE]


def test_text_mismatch_fails() -> None:
    """Chunk text must exactly equal source node text."""
    document, chunks = _valid_chunks()
    chunk = chunks[0].model_copy(update={"text": "Điểm a. Sai text.\n"}, deep=True)

    result = LegalChunkValidator().validate(document=document, chunks=[chunk])

    assert result.is_valid is False
    assert result.validation_summary.text_mismatches == 1
    assert [error.code for error in result.errors] == [ChunkingIssueCode.TEXT_MISMATCH]


def test_parent_text_mismatch_fails() -> None:
    """parent_text must exactly equal the parent Article node text."""
    document, chunks = _valid_chunks()
    chunk = chunks[0].model_copy(update={"parent_text": "Điều 1. Sai parent.\n"}, deep=True)

    result = LegalChunkValidator().validate(document=document, chunks=[chunk])

    assert result.is_valid is False
    assert result.validation_summary.parent_text_mismatches == 1
    assert [error.code for error in result.errors] == [ChunkingIssueCode.PARENT_TEXT_MISMATCH]


def test_offset_mismatch_fails() -> None:
    """Chunk offsets must match source and parent Article node offsets."""
    document, chunks = _valid_chunks()
    chunk = chunks[0].model_copy(update={"start_offset": chunks[0].start_offset + 1}, deep=True)

    result = LegalChunkValidator().validate(document=document, chunks=[chunk])

    assert result.is_valid is False
    assert result.validation_summary.invalid_offsets == 1
    assert [error.code for error in result.errors] == [ChunkingIssueCode.OFFSET_MISMATCH]


def test_invalid_chunk_level_fails() -> None:
    """Chunk level must match the real source node level."""
    document, chunks = _valid_chunks()
    chunk = chunks[0].model_copy(update={"level": ChunkingLevel.CLAUSE}, deep=True)

    result = LegalChunkValidator().validate(document=document, chunks=[chunk])

    assert result.is_valid is False
    assert result.validation_summary.invalid_chunk_levels == 1
    assert [error.code for error in result.errors] == [ChunkingIssueCode.INVALID_CHUNK_LEVEL]


def test_law_part_chapter_section_source_node_fails() -> None:
    """Chunks cannot use Law/Part/Chapter/Section nodes as source nodes."""
    document, chunks = _valid_chunks()
    chunk = chunks[0].model_copy(
        update={
            "level": ChunkingLevel.ARTICLE,
            "source_node_id": document.root_node_id,
            "text": document.nodes[0].text,
            "start_offset": document.nodes[0].start_offset,
            "end_offset": document.nodes[0].end_offset,
        },
        deep=True,
    )

    result = LegalChunkValidator().validate(document=document, chunks=[chunk])

    assert result.is_valid is False
    assert result.validation_summary.invalid_chunk_levels == 1
    assert ChunkingIssueCode.INVALID_CHUNK_LEVEL in [error.code for error in result.errors]
