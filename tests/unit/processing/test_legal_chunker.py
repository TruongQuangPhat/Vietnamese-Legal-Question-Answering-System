"""Tests for deterministic Phase 6 parent-child chunk selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.processing.legal_chunk_models import ChunkingIssueCode, ChunkingLevel
from src.processing.legal_chunker import CHUNK_SCHEMA_VERSION, CHUNKER_VERSION, LegalChunker
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "legal_chunking"


def _load_document(name: str) -> LegalHierarchyDocument:
    """Load a committed legal hierarchy fixture for chunker tests."""
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    return LegalHierarchyDocument.model_validate(payload)


def _chunk_ids(name: str) -> list[str]:
    """Return chunk IDs emitted for one fixture."""
    return [chunk.chunk_id for chunk in LegalChunker().chunk_document(_load_document(name))]


def _metadata(law_name: str = "Luật Kiểm thử") -> LegalHierarchyMetadata:
    """Create document metadata for synthetic chunker tests."""
    return LegalHierarchyMetadata(
        law_name=law_name,
        source_url="https://thuvienphapluat.vn/test.aspx",
        source_domain="thuvienphapluat.vn",
        source_type="html",
        raw_artifact_path="data/raw/TEST_LAW/latest/main.html",
        article_heading_count=1,
        max_heading_article_number=1,
        has_heading_article_1=True,
        heading_sequence_score=1.0,
    )


def _full_hierarchy_document() -> LegalHierarchyDocument:
    """Build a hierarchy document containing every real ancestor level."""
    root_text = "\n".join(
        [
            "Luật Kiểm thử VBHN",
            "Phần I. PHẦN CHUNG",
            "Chương I. QUY ĐỊNH CHUNG",
            "Mục 1. PHẠM VI",
            "Điều 1. Phạm vi điều chỉnh",
            "Khoản 1. Nội dung khoản.",
            "Điểm a. Nội dung điểm.",
            "",
        ]
    )
    law_id = "TEST_LAW"
    root_id = f"{law_id}__root"
    part_id = f"{root_id}__part_I"
    chapter_id = f"{part_id}__chapter_I"
    section_id = f"{chapter_id}__section_1"
    article_id = f"{section_id}__article_1"
    clause_id = f"{article_id}__clause_1"
    point_id = f"{clause_id}__point_a"

    part_text = root_text[root_text.index("Phần I.") :]
    chapter_text = root_text[root_text.index("Chương I.") :]
    section_text = root_text[root_text.index("Mục 1.") :]
    article_text = root_text[root_text.index("Điều 1.") :]
    clause_text = root_text[root_text.index("Khoản 1.") :]
    point_text = root_text[root_text.index("Điểm a.") :]

    return LegalHierarchyDocument(
        schema_version="1.0",
        parser_version="v0.1.0",
        cleaner_version="v0.8.0",
        law_id=law_id,
        source_file="data/interim/TEST_LAW/normalized.json",
        root_node_id=root_id,
        metadata=_metadata(law_name="Luật Kiểm thử VBHN"),
        warnings=[],
        nodes=[
            LegalNode(
                node_id=root_id,
                level=LegalNodeLevel.LAW,
                number=None,
                title="Luật Kiểm thử VBHN",
                text=root_text,
                start_offset=0,
                end_offset=len(root_text),
                parent_id=None,
                children=[part_id],
            ),
            LegalNode(
                node_id=part_id,
                level=LegalNodeLevel.PART,
                number="I",
                title="PHẦN CHUNG",
                text=part_text,
                start_offset=root_text.index("Phần I."),
                end_offset=len(root_text),
                parent_id=root_id,
                children=[chapter_id],
            ),
            LegalNode(
                node_id=chapter_id,
                level=LegalNodeLevel.CHAPTER,
                number="I",
                title="QUY ĐỊNH CHUNG",
                text=chapter_text,
                start_offset=root_text.index("Chương I."),
                end_offset=len(root_text),
                parent_id=part_id,
                children=[section_id],
            ),
            LegalNode(
                node_id=section_id,
                level=LegalNodeLevel.SECTION,
                number="1",
                title="PHẠM VI",
                text=section_text,
                start_offset=root_text.index("Mục 1."),
                end_offset=len(root_text),
                parent_id=chapter_id,
                children=[article_id],
            ),
            LegalNode(
                node_id=article_id,
                level=LegalNodeLevel.ARTICLE,
                number="1",
                title="Phạm vi điều chỉnh",
                text=article_text,
                start_offset=root_text.index("Điều 1."),
                end_offset=len(root_text),
                parent_id=section_id,
                children=[clause_id],
            ),
            LegalNode(
                node_id=clause_id,
                level=LegalNodeLevel.CLAUSE,
                number="1",
                title=None,
                text=clause_text,
                start_offset=root_text.index("Khoản 1."),
                end_offset=len(root_text),
                parent_id=article_id,
                children=[point_id],
            ),
            LegalNode(
                node_id=point_id,
                level=LegalNodeLevel.POINT,
                number="a",
                title=None,
                text=point_text,
                start_offset=root_text.index("Điểm a."),
                end_offset=len(root_text),
                parent_id=clause_id,
                children=[],
            ),
        ],
    )


def test_article_only_document_produces_article_level_chunk() -> None:
    """An Article without Clause children becomes one Article chunk."""
    document = _load_document("sample_hierarchy_article_only.json")

    chunks = LegalChunker().chunk_document(document)

    assert len(chunks) == 1
    chunk = chunks[0]
    article = document.nodes[1]
    assert chunk.schema_version == CHUNK_SCHEMA_VERSION
    assert chunk.chunker_version == CHUNKER_VERSION
    assert chunk.level == ChunkingLevel.ARTICLE
    assert chunk.chunk_kind == "article_level"
    assert chunk.chunk_id == f"{article.node_id}__chunk"
    assert chunk.source_node_id == article.node_id
    assert chunk.parent_article_node_id == article.node_id
    assert chunk.parent_chunk_id == f"{article.node_id}__parent"
    assert chunk.text == article.text
    assert chunk.parent_text == article.text
    assert chunk.article_number == "1"
    assert chunk.clause_number is None
    assert chunk.point_label is None


def test_clause_only_article_produces_clause_chunk() -> None:
    """A Clause without Point children becomes one Clause chunk."""
    document = _load_document("sample_hierarchy_article_clause_only.json")

    chunks = LegalChunker().chunk_document(document)

    assert len(chunks) == 1
    chunk = chunks[0]
    article = document.nodes[1]
    clause = document.nodes[2]
    assert chunk.level == ChunkingLevel.CLAUSE
    assert chunk.chunk_kind == "clause_level"
    assert chunk.source_node_id == clause.node_id
    assert chunk.parent_article_node_id == article.node_id
    assert chunk.text == clause.text
    assert chunk.parent_text == article.text
    assert chunk.article_number == "1"
    assert chunk.clause_number == "1"
    assert chunk.point_label is None


def test_clause_with_points_produces_point_chunks_and_clause_without_points_is_clause() -> None:
    """Point children are preferred over their Clause, while leaf Clauses still chunk."""
    document = _load_document("sample_hierarchy_clause_point.json")

    chunks = LegalChunker().chunk_document(document)

    assert [chunk.level for chunk in chunks] == [
        ChunkingLevel.POINT,
        ChunkingLevel.POINT,
        ChunkingLevel.CLAUSE,
    ]
    assert [chunk.source_node_id for chunk in chunks] == [
        "TEST_LAW__root__article_1__clause_1__point_a",
        "TEST_LAW__root__article_1__clause_1__point_b",
        "TEST_LAW__root__article_1__clause_2",
    ]
    assert [chunk.point_label for chunk in chunks] == ["a", "b", None]
    assert [chunk.clause_number for chunk in chunks] == ["1", "1", "2"]
    assert all(chunk.parent_article_node_id == "TEST_LAW__root__article_1" for chunk in chunks)


def test_mixed_document_preserves_source_order() -> None:
    """Source order is stable across Clause and Article fallback chunks."""
    assert _chunk_ids("sample_hierarchy_no_part_chapter.json") == [
        "TEST_LAW__root__article_1__clause_1__chunk",
        "TEST_LAW__root__article_2__chunk",
    ]


def test_collision_resolved_node_ids_are_preserved() -> None:
    """Resolved Phase 5 node IDs are used directly for chunk IDs."""
    assert _chunk_ids("sample_hierarchy_collision_ids.json") == [
        "TEST_LAW__root__article_1__clause_1__point_a__chunk",
        "TEST_LAW__root__article_1__clause_1__point_a__occurrence_2__chunk",
        "TEST_LAW__root__article_2__chunk",
    ]


def test_empty_article_produces_flagged_article_level_chunk() -> None:
    """Empty/repealed Articles are preserved as flagged Article chunks."""
    document = _load_document("sample_hierarchy_empty_article.json")

    chunks = LegalChunker().chunk_document(document)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.level == ChunkingLevel.ARTICLE
    assert chunk.chunk_kind == "article_level_empty"
    assert chunk.metadata.is_empty_or_repealed is True
    assert chunk.metadata.source_warnings == ["EMPTY_ARTICLE_NODE"]
    assert len(chunk.warnings) == 1
    assert chunk.warnings[0].code == "EMPTY_ARTICLE_CHUNK"


def test_chunks_include_minimal_citation_path_offsets_and_hashes() -> None:
    """Step 2 chunks are already schema-valid and traceable to hierarchy nodes."""
    document = _load_document("sample_hierarchy_article_clause_only.json")

    chunk = LegalChunker().chunk_document(document)[0]

    assert chunk.citation == "Luật Kiểm thử, Khoản 1, Điều 1"
    assert chunk.hierarchy_path == "Luật Kiểm thử / Điều 1. Phạm vi điều chỉnh / Khoản 1"
    assert chunk.start_offset == 38
    assert chunk.end_offset == 64
    assert chunk.article_start_offset == 14
    assert chunk.article_end_offset == 64
    assert len(chunk.text_hash) == 64
    assert len(chunk.parent_text_hash) == 64


def test_article_clause_and_point_citations_are_vietnamese() -> None:
    """Citation format follows Article, Clause, and Point legal hierarchy."""
    article_chunk = LegalChunker().chunk_document(_load_document("sample_hierarchy_article_only.json"))[0]
    clause_chunk = LegalChunker().chunk_document(
        _load_document("sample_hierarchy_article_clause_only.json")
    )[0]
    point_chunk = LegalChunker().chunk_document(_load_document("sample_hierarchy_clause_point.json"))[
        0
    ]

    assert article_chunk.citation == "Luật Kiểm thử, Điều 1"
    assert clause_chunk.citation == "Luật Kiểm thử, Khoản 1, Điều 1"
    assert point_chunk.citation == "Luật Kiểm thử, Điểm a, Khoản 1, Điều 1"


def test_vbhn_metadata_title_is_used_without_inventing_dates() -> None:
    """Citation uses hierarchy metadata law name exactly as provided."""
    document = _load_document("sample_hierarchy_article_only.json")
    document = document.model_copy(
        update={"metadata": document.metadata.model_copy(update={"law_name": "BLHS VBHN"})},
        deep=True,
    )

    chunk = LegalChunker().chunk_document(document)[0]

    assert chunk.law_name == "BLHS VBHN"
    assert chunk.citation == "BLHS VBHN, Điều 1"
    assert "2015" not in chunk.citation
    assert "2026" not in chunk.citation


def test_hierarchy_path_includes_only_real_full_parent_chain() -> None:
    """Real Part/Chapter/Section ancestors appear when present."""
    chunk = LegalChunker().chunk_document(_full_hierarchy_document())[0]

    assert chunk.hierarchy_path == (
        "Luật Kiểm thử VBHN / Phần I. PHẦN CHUNG / "
        "Chương I. QUY ĐỊNH CHUNG / Mục 1. PHẠM VI / "
        "Điều 1. Phạm vi điều chỉnh / Khoản 1 / Điểm a"
    )


def test_missing_part_chapter_section_are_not_synthesized_in_path() -> None:
    """Missing intermediate levels remain absent from hierarchy_path."""
    chunks = LegalChunker().chunk_document(_load_document("sample_hierarchy_no_part_chapter.json"))

    assert chunks[0].hierarchy_path == "Luật Kiểm thử / Điều 1. Quy định đầu tiên / Khoản 1"
    assert chunks[1].hierarchy_path == "Luật Kiểm thử / Điều 2. Quy định thứ hai"
    assert "Phần" not in chunks[0].hierarchy_path
    assert "Chương" not in chunks[0].hierarchy_path
    assert "Mục" not in chunks[0].hierarchy_path


def test_chunk_offsets_match_exact_root_slices_when_root_text_is_complete() -> None:
    """Chunk text and parent text stay tied to exact hierarchy source offsets."""
    document = _full_hierarchy_document()
    root = document.nodes[0]
    chunk = LegalChunker().chunk_document(document)[0]

    assert chunk.text == root.text[chunk.start_offset : chunk.end_offset]
    assert chunk.parent_text == root.text[chunk.article_start_offset : chunk.article_end_offset]
    assert chunk.article_start_offset <= chunk.start_offset
    assert chunk.end_offset <= chunk.article_end_offset
    assert chunk.text in chunk.parent_text
    assert chunk.warnings == []


def test_chunk_hashes_are_sha256_of_text_and_parent_text() -> None:
    """Text hashes are deterministic SHA-256 digests over UTF-8 content."""
    chunk = LegalChunker().chunk_document(_full_hierarchy_document())[0]

    assert chunk.text_hash == hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
    assert chunk.parent_text_hash == hashlib.sha256(
        chunk.parent_text.encode("utf-8")
    ).hexdigest()


def test_source_slice_mismatch_adds_structured_warning() -> None:
    """A hierarchy text/offset mismatch is surfaced without rewriting text."""
    document = _full_hierarchy_document()
    nodes = [node.model_copy(deep=True) for node in document.nodes]
    nodes[-1].text = "Điểm a. Nội dung bị lệch.\n"
    document = document.model_copy(update={"nodes": nodes}, deep=True)

    chunk = LegalChunker().chunk_document(document)[0]
    root_slice = document.nodes[0].text[chunk.start_offset : chunk.end_offset]

    assert chunk.text == "Điểm a. Nội dung bị lệch.\n"
    assert root_slice
    assert chunk.text != root_slice
    assert [warning.code for warning in chunk.warnings] == [
        ChunkingIssueCode.TEXT_MISMATCH,
        ChunkingIssueCode.CHILD_OUTSIDE_ARTICLE,
    ]


def test_source_file_override_is_used_for_traceability() -> None:
    """The caller can set the real hierarchy.json source path."""
    document = _load_document("sample_hierarchy_article_only.json")

    chunk = LegalChunker().chunk_document(
        document,
        source_file="data/interim/TEST_LAW/hierarchy.json",
    )[0]

    assert chunk.source_file == "data/interim/TEST_LAW/hierarchy.json"
