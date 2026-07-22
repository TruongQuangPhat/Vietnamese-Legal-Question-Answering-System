"""Unit tests for deterministic sparse BM25 retrieval."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.retrieval.sparse_retriever import (
    SparseBM25Retriever,
    tokenize_sparse_text,
)


def _write_chunks(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _chunk(
    chunk_id: str,
    text: str,
    *,
    article_number: str = "1",
    parent_text: str | None = None,
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "law_id": "LAW_A",
        "law_name": "Luật A",
        "citation": f"Luật A, Điều {article_number}",
        "hierarchy_path": f"Luật A / Điều {article_number}",
        "article_number": article_number,
        "text": text,
        "parent_text": parent_text or text,
        "source_url": "https://thuvienphapluat.vn/example",
        "source_domain": "thuvienphapluat.vn",
        "metadata": {
            "is_empty_or_repealed": False,
            "is_source_unit_repealed": False,
        },
        "warnings": [],
    }


def test_tokenization_preserves_vietnamese_terms_and_numbers() -> None:
    tokens = tokenize_sparse_text("Khoản 1 Điều 17 Luật Đất đai")

    assert tokens == ["khoản", "1", "điều", "17", "luật", "đất", "đai"]


@pytest.mark.asyncio
async def test_bm25_retrieval_is_deterministic(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(
        chunks_path,
        [
            _chunk("chunk_a", "Điều 17 quy định về quyền sử dụng đất.", article_number="17"),
            _chunk("chunk_b", "Điều 20 quy định về quyền dân sự.", article_number="20"),
        ],
    )
    retriever = SparseBM25Retriever.from_jsonl(chunks_path, default_top_k=2)

    first = await retriever.retrieve("quyền sử dụng đất Điều 17", top_k=2)
    second = await retriever.retrieve("quyền sử dụng đất Điều 17", top_k=2)

    assert [chunk.chunk_id for chunk in first.results] == ["chunk_a", "chunk_b"]
    assert [chunk.chunk_id for chunk in second.results] == ["chunk_a", "chunk_b"]
    assert [chunk.score for chunk in first.results] == pytest.approx(
        [chunk.score for chunk in second.results]
    )
    assert first.results[0].law_id == "LAW_A"
    assert first.results[0].source_url == "https://thuvienphapluat.vn/example"


@pytest.mark.asyncio
async def test_sparse_index_uses_local_parent_context_for_point_chunks(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(
        chunks_path,
        [
            _chunk(
                "notice",
                "a) Ít nhất 45 ngày.",
                article_number="35",
                parent_text=(
                    "Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động\n"
                    "1. Người lao động phải báo trước như sau:\n"
                    "a) Ít nhất 45 ngày."
                ),
            ),
            _chunk(
                "no-notice",
                "a) Không được bố trí theo đúng công việc.",
                article_number="35",
                parent_text=(
                    "Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động\n"
                    "2. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động "
                    "không cần báo trước trong trường hợp sau đây:\n"
                    "a) Không được bố trí theo đúng công việc."
                ),
            ),
        ],
    )
    retriever = SparseBM25Retriever.from_jsonl(chunks_path, default_top_k=2)

    result = await retriever.retrieve("nghỉ việc không cần báo trước", top_k=2)

    assert result.results[0].chunk_id == "no-notice"


@pytest.mark.asyncio
async def test_no_match_query_returns_empty_result(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(chunks_path, [_chunk("chunk_a", "Điều 1 quy định về dân sự.")])
    retriever = SparseBM25Retriever.from_jsonl(chunks_path)

    result = await retriever.retrieve("zzzzzz", top_k=10)

    assert result.results == []
    assert result.issues == []


@pytest.mark.asyncio
async def test_top_k_output_is_stable_for_tied_scores(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(
        chunks_path,
        [
            _chunk("chunk_b", "thuật ngữ chung"),
            _chunk("chunk_a", "thuật ngữ chung"),
            _chunk("chunk_c", "thuật ngữ khác"),
        ],
    )
    retriever = SparseBM25Retriever.from_jsonl(chunks_path)

    result = await retriever.retrieve("thuật ngữ chung", top_k=2)

    assert [chunk.chunk_id for chunk in result.results] == ["chunk_a", "chunk_b"]
