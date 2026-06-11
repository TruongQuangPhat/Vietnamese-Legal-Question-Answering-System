"""Unit tests for the read-only Phase 8 legal chunk loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.indexing.chunk_loader import (
    ChunkLoaderError,
    build_embedding_input,
    iter_embedding_inputs,
    iter_legal_chunks,
)
from src.processing.legal_chunk_models import LegalChunk


def _chunk_payload(**overrides: object) -> dict[str, object]:
    """Build one minimal valid serialized LegalChunk."""
    text = "1."
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "chunker_version": "v0.1.0",
        "chunk_id": "LAW_1__article_1__clause_1__chunk",
        "law_id": "LAW_1",
        "law_name": "Luật Thử nghiệm 2026",
        "source_url": "https://thuvienphapluat.vn/example",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "source_file": "data/interim/LAW_1/hierarchy.json",
        "level": "clause",
        "chunk_kind": "clause_level",
        "source_node_id": "LAW_1__article_1__clause_1",
        "parent_article_node_id": "LAW_1__article_1",
        "parent_chunk_id": "LAW_1__article_1__parent",
        "article_number": "1",
        "article_title": "Phạm vi điều chỉnh",
        "clause_number": "1",
        "point_label": None,
        "citation": "Luật Thử nghiệm 2026, khoản 1 Điều 1",
        "hierarchy_path": "Luật Thử nghiệm 2026 / Điều 1 / Khoản 1",
        "text": text,
        "parent_text": "Điều 1. Phạm vi điều chỉnh\n1.",
        "start_offset": 30,
        "end_offset": 32,
        "article_start_offset": 0,
        "article_end_offset": 32,
        "text_hash": "text-hash",
        "parent_text_hash": "parent-text-hash",
        "metadata": {
            "is_empty_or_repealed": False,
            "is_source_unit_repealed": False,
            "source_warnings": ["SOURCE_NOTE_EXCLUDED"],
            "caveat_references": ["ref-1"],
        },
        "warnings": [
            {
                "code": "EMPTY_CHUNK_TEXT",
                "message": "Cảnh báo thử nghiệm",
                "law_id": "LAW_1",
                "chunk_id": "LAW_1__article_1__clause_1__chunk",
                "source_node_id": "LAW_1__article_1__clause_1",
                "context": {"accepted": True},
            }
        ],
    }
    payload.update(overrides)
    return payload


def _chunk(**overrides: object) -> LegalChunk:
    """Build one validated LegalChunk."""
    return LegalChunk.model_validate(_chunk_payload(**overrides))


def _write_jsonl(path: Path, payloads: list[dict[str, object]]) -> None:
    """Write serialized chunk payloads to a temporary JSONL file."""
    path.write_text(
        "".join(f"{json.dumps(payload, ensure_ascii=False)}\n" for payload in payloads),
        encoding="utf-8",
    )


class TestIterLegalChunks:
    """Tests for streaming and validating processed JSONL rows."""

    def test_streams_valid_chunks(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        _write_jsonl(
            path,
            [
                _chunk_payload(chunk_id="chunk-1"),
                _chunk_payload(chunk_id="chunk-2"),
            ],
        )

        chunks = iter_legal_chunks(path)

        assert iter(chunks) is chunks
        assert [chunk.chunk_id for chunk in chunks] == ["chunk-1", "chunk-2"]

    def test_invalid_json_includes_path_and_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        path.write_text(
            f"{json.dumps(_chunk_payload(), ensure_ascii=False)}\n{{invalid\n",
            encoding="utf-8",
        )

        with pytest.raises(ChunkLoaderError) as exc_info:
            list(iter_legal_chunks(path))

        message = str(exc_info.value)
        assert str(path) in message
        assert ":2:" in message
        assert "invalid JSON" in message

    def test_invalid_legal_chunk_includes_path_and_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        _write_jsonl(path, [_chunk_payload(chunk_id="")])

        with pytest.raises(ChunkLoaderError) as exc_info:
            list(iter_legal_chunks(path))

        message = str(exc_info.value)
        assert str(path) in message
        assert ":1:" in message
        assert "invalid LegalChunk" in message

    def test_missing_file_raises_clear_error(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.jsonl"

        with pytest.raises(ChunkLoaderError) as exc_info:
            list(iter_legal_chunks(path))

        message = str(exc_info.value)
        assert str(path) in message
        assert "unable to read input file" in message


class TestBuildEmbeddingInput:
    """Tests for deterministic embedding text and traceability mapping."""

    def test_maps_chunk_to_embedding_input(self) -> None:
        chunk = _chunk()

        embedding_input = build_embedding_input(chunk)

        assert embedding_input.chunk_id == chunk.chunk_id
        assert embedding_input.law_id == chunk.law_id
        assert embedding_input.level == chunk.level
        assert embedding_input.text_hash == chunk.text_hash
        assert embedding_input.parent_text_hash == chunk.parent_text_hash
        assert embedding_input.citation == chunk.citation
        assert embedding_input.hierarchy_path == chunk.hierarchy_path

    def test_text_only_uses_exact_chunk_text(self) -> None:
        text = "Khoản ngắn có khoảng trắng cuối.  \n"
        chunk = _chunk(text=text, end_offset=35, article_end_offset=35)

        embedding_input = build_embedding_input(chunk)

        assert embedding_input.embedding_text == text
        assert chunk.text == text

    def test_citation_plus_text_template(self) -> None:
        chunk = _chunk()

        embedding_input = build_embedding_input(chunk, text_template="citation_plus_text")

        assert embedding_input.embedding_text == f"{chunk.citation}\n{chunk.text}"

    def test_law_citation_plus_text_template(self) -> None:
        chunk = _chunk()

        embedding_input = build_embedding_input(chunk, text_template="law_citation_plus_text")

        assert embedding_input.embedding_text == (
            f"{chunk.law_name}\n{chunk.citation}\n{chunk.text}"
        )

    def test_unsupported_template_fails(self) -> None:
        with pytest.raises(ChunkLoaderError, match="unsupported text template"):
            build_embedding_input(_chunk(), text_template="parent_text")

    def test_citation_template_rejects_blank_citation(self) -> None:
        chunk = _chunk(citation="   ")

        with pytest.raises(ChunkLoaderError, match="blank citation"):
            build_embedding_input(chunk, text_template="citation_plus_text")

    def test_law_citation_template_rejects_blank_law_name(self) -> None:
        chunk = _chunk(law_name="   ")

        with pytest.raises(ChunkLoaderError, match="blank law_name"):
            build_embedding_input(chunk, text_template="law_citation_plus_text")

    def test_blank_embedding_text_fails(self) -> None:
        chunk = _chunk(text="   ", end_offset=33, article_end_offset=33)

        with pytest.raises(ChunkLoaderError, match="blank text"):
            build_embedding_input(chunk)

    def test_short_chunk_is_preserved(self) -> None:
        chunk = _chunk(text="a", end_offset=31, article_end_offset=31)

        embedding_input = build_embedding_input(chunk)

        assert embedding_input.embedding_text == "a"

    def test_metadata_and_warnings_are_preserved(self) -> None:
        chunk = _chunk()

        embedding_input = build_embedding_input(chunk)

        assert embedding_input.metadata == chunk.metadata
        assert embedding_input.metadata is not chunk.metadata
        assert embedding_input.warnings == chunk.warnings
        assert embedding_input.warnings is not chunk.warnings


class TestIterEmbeddingInputs:
    """Tests for filtering and limiting the embedding input stream."""

    def test_maps_valid_chunks(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        _write_jsonl(path, [_chunk_payload()])

        inputs = list(iter_embedding_inputs(path))

        assert len(inputs) == 1
        assert inputs[0].embedding_text == "1."

    def test_law_id_filter_works(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        _write_jsonl(
            path,
            [
                _chunk_payload(chunk_id="chunk-1", law_id="LAW_1"),
                _chunk_payload(chunk_id="chunk-2", law_id="LAW_2"),
            ],
        )

        inputs = list(iter_embedding_inputs(path, law_id="LAW_2"))

        assert [item.chunk_id for item in inputs] == ["chunk-2"]

    def test_limit_applies_after_filtering(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        _write_jsonl(
            path,
            [
                _chunk_payload(chunk_id="chunk-1", law_id="LAW_1"),
                _chunk_payload(chunk_id="chunk-2", law_id="LAW_2"),
                _chunk_payload(chunk_id="chunk-3", law_id="LAW_2"),
            ],
        )

        inputs = list(iter_embedding_inputs(path, law_id="LAW_2", limit=1))

        assert [item.chunk_id for item in inputs] == ["chunk-2"]

    def test_zero_limit_reads_no_records(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.jsonl"

        assert list(iter_embedding_inputs(path, limit=0)) == []

    def test_negative_limit_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"

        with pytest.raises(ChunkLoaderError, match="limit must be"):
            list(iter_embedding_inputs(path, limit=-1))

    def test_mapping_error_includes_path_and_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        _write_jsonl(path, [_chunk_payload(text="   ")])

        with pytest.raises(ChunkLoaderError) as exc_info:
            list(iter_embedding_inputs(path))

        message = str(exc_info.value)
        assert str(path) in message
        assert ":1:" in message
        assert "blank text" in message

    def test_duplicate_text_chunks_remain_separate(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        _write_jsonl(
            path,
            [
                _chunk_payload(chunk_id="chunk-1"),
                _chunk_payload(chunk_id="chunk-2"),
            ],
        )

        inputs = list(iter_embedding_inputs(path))

        assert [item.chunk_id for item in inputs] == ["chunk-1", "chunk-2"]
        assert inputs[0].embedding_text == inputs[1].embedding_text
