"""Integration tests for sparse BM25 retrieval workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.retrieval.sparse_retriever import SparseBM25Retriever


@pytest.mark.asyncio
async def test_sparse_bm25_workflow_retrieves_exact_legal_keyword_match(
    tmp_path: Path,
) -> None:
    """A tiny local BM25 index retrieves exact Vietnamese legal terms deterministically."""
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(
        chunks_path,
        [
            _chunk(
                "probation-pay",
                "Người lao động thử việc được trả tiền lương theo thỏa thuận.",
                law_id="BLLD_2019",
                article_number="26",
                clause_number="1",
            ),
            _chunk(
                "salary",
                "Tiền lương bao gồm mức lương theo công việc hoặc chức danh.",
                law_id="BLLD_2019",
                article_number="90",
                clause_number="1",
            ),
            _chunk(
                "civil-transaction",
                "Giao dịch dân sự có hiệu lực khi chủ thể có năng lực pháp luật dân sự.",
                law_id="BLDS_2015",
                article_number="117",
                clause_number="1",
            ),
            _chunk(
                "distractor",
                "Nội dung về đăng ký hộ tịch không liên quan đến thử việc.",
                law_id="HOTICH_2014",
                article_number="1",
                clause_number="1",
            ),
        ],
    )
    retriever = SparseBM25Retriever.from_jsonl(chunks_path, default_top_k=3)

    first = await retriever.retrieve("thử việc thỏa thuận", top_k=3)
    second = await retriever.retrieve("thử việc thỏa thuận", top_k=3)

    assert first.results[0].chunk_id == "probation-pay"
    assert [chunk.chunk_id for chunk in first.results] == [
        chunk.chunk_id for chunk in second.results
    ]
    assert [chunk.score for chunk in first.results] == pytest.approx(
        [chunk.score for chunk in second.results]
    )
    top = first.results[0]
    assert top.law_id == "BLLD_2019"
    assert top.article_number == "26"
    assert top.clause_number == "1"
    assert top.source_url == "https://thuvienphapluat.vn/BLLD_2019"
    assert top.citation == "Luật Kiểm thử, Khoản 1, Điều 26"
    assert first.vector_name == "sparse_bm25"
    assert first.query_vector_dimension == 0


def _write_chunks(path: Path, records: list[dict[str, object]]) -> None:
    """Write tiny chunk records as JSONL under a temporary directory."""
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _chunk(
    chunk_id: str,
    text: str,
    *,
    law_id: str,
    article_number: str,
    clause_number: str,
) -> dict[str, object]:
    """Build a tiny sparse-retrieval payload with legal metadata."""
    return {
        "chunk_id": chunk_id,
        "law_id": law_id,
        "law_name": "Luật Kiểm thử",
        "level": "clause",
        "chunk_kind": "clause_level",
        "article_number": article_number,
        "article_title": "Quy định kiểm thử",
        "clause_number": clause_number,
        "point_label": None,
        "citation": f"Luật Kiểm thử, Khoản {clause_number}, Điều {article_number}",
        "hierarchy_path": f"Luật Kiểm thử / Điều {article_number} / Khoản {clause_number}",
        "text": text,
        "parent_text": f"Điều {article_number}. Quy định kiểm thử\n{text}",
        "source_url": f"https://thuvienphapluat.vn/{law_id}",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "metadata": {
            "is_empty_or_repealed": False,
            "is_source_unit_repealed": False,
        },
        "warnings": [],
    }
