"""Integration tests for legal parsing and parent-child chunking."""

from __future__ import annotations

import json
from pathlib import Path

from src.processing.legal_chunker import LegalChunker
from src.processing.legal_hierarchy_models import LegalNodeLevel, LegalParsingStatus
from src.processing.legal_parser import LegalParser

TINY_LEGAL_TEXT = """Chương I
QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Luật này quy định về phạm vi điều chỉnh.
a) Điểm a quy định nội dung cụ thể.
b) Điểm b quy định nội dung khác.

Điều 2. Đối tượng áp dụng
1. Luật này áp dụng đối với cơ quan, tổ chức, cá nhân có liên quan.
"""


def test_legal_parsing_chunking_workflow_preserves_hierarchy_and_chunks(
    tmp_path: Path,
) -> None:
    """A tiny normalized law is parsed and chunked with deterministic child chunks."""
    normalized_path = _write_normalized_artifact(tmp_path, TINY_LEGAL_TEXT)

    parse_result = LegalParser().parse_file(normalized_path=normalized_path)
    assert parse_result.status == LegalParsingStatus.SUCCESS
    assert parse_result.document is not None
    document = parse_result.document

    levels = [node.level for node in document.nodes]
    assert LegalNodeLevel.CHAPTER in levels
    assert levels.count(LegalNodeLevel.ARTICLE) == 2
    assert levels.count(LegalNodeLevel.CLAUSE) == 2
    assert levels.count(LegalNodeLevel.POINT) == 2
    assert [node.number for node in document.nodes if node.level == LegalNodeLevel.ARTICLE] == [
        "1",
        "2",
    ]

    chunks = LegalChunker().chunk_document(document, source_file=str(tmp_path / "hierarchy.json"))
    repeated_chunks = LegalChunker().chunk_document(
        document,
        source_file=str(tmp_path / "hierarchy.json"),
    )

    assert len(chunks) == 3
    assert [chunk.chunk_id for chunk in chunks] == [chunk.chunk_id for chunk in repeated_chunks]
    assert [chunk.level.value for chunk in chunks] == ["point", "point", "clause"]
    assert [(chunk.article_number, chunk.clause_number, chunk.point_label) for chunk in chunks] == [
        ("1", "1", "a"),
        ("1", "1", "b"),
        ("2", "1", None),
    ]
    assert all(chunk.law_id == "TINY_LAW" for chunk in chunks)
    assert all(chunk.source_url == "https://thuvienphapluat.vn/tiny-law" for chunk in chunks)
    assert all(chunk.citation for chunk in chunks)
    assert chunks[0].text.startswith("a) Điểm a")
    assert chunks[0].parent_text.startswith("Điều 1. Phạm vi điều chỉnh")
    assert chunks[0].text != chunks[0].parent_text
    assert chunks[0].parent_article_node_id != chunks[0].source_node_id
    assert chunks[0].parent_chunk_id.endswith("__parent")


def _write_normalized_artifact(tmp_path: Path, normalized_text: str) -> Path:
    """Write a tiny normalized artifact using only temporary paths."""
    law_dir = tmp_path / "interim" / "TINY_LAW"
    law_dir.mkdir(parents=True)
    normalized_path = law_dir / "normalized.json"
    normalized_path.write_text(
        json.dumps(
            {
                "law_id": "TINY_LAW",
                "law_name": "Luật Kiểm thử",
                "source_url": "https://thuvienphapluat.vn/tiny-law",
                "source_domain": "thuvienphapluat.vn",
                "source_type": "html",
                "raw_artifact_path": str(tmp_path / "raw" / "TINY_LAW" / "latest" / "main.html"),
                "normalized_text": normalized_text,
                "text_stats": {
                    "normalized_text_chars": len(normalized_text),
                    "line_count": len(normalized_text.splitlines()),
                },
                "markers": {
                    "article_reference_count": 2,
                    "article_heading_count": 2,
                    "max_heading_article_number": 2,
                    "has_heading_article_1": True,
                    "heading_sequence_score": 1.0,
                },
                "warnings": [],
                "metadata": {"cleaner_version": "v0.8.0"},
                "candidate_info": {"selection_strategy": "tiny_fixture"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return normalized_path
