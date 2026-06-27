"""Unit tests for deterministic embedding/indexing vector payload construction."""

from __future__ import annotations

import uuid

import pytest

from src.indexing.indexing_models import VectorPayload
from src.indexing.payload_builder import (
    build_point_id,
    build_vector_payload,
    vector_payload_to_qdrant_payload,
)
from src.processing.legal_chunk_models import LegalChunk


def _chunk(**overrides: object) -> LegalChunk:
    """Build one minimal valid point-level legal chunk."""
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "chunker_version": "v0.1.0",
        "chunk_id": "LAW_1__article_1__clause_1__point_a__chunk",
        "law_id": "LAW_1",
        "law_name": "Luật Thử nghiệm 2026",
        "source_url": "https://thuvienphapluat.vn/example",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "source_file": "data/interim/LAW_1/hierarchy.json",
        "level": "point",
        "chunk_kind": "point_level",
        "source_node_id": "LAW_1__article_1__clause_1__point_a",
        "parent_article_node_id": "LAW_1__article_1",
        "parent_chunk_id": "LAW_1__article_1__parent",
        "article_number": "1",
        "article_title": "Phạm vi điều chỉnh",
        "clause_number": "1",
        "point_label": "a",
        "citation": "Luật Thử nghiệm 2026, điểm a khoản 1 Điều 1",
        "hierarchy_path": "Luật Thử nghiệm 2026 / Điều 1 / Khoản 1 / Điểm a",
        "text": "a)",
        "parent_text": "Điều 1. Phạm vi điều chỉnh\n1. Nội dung\n a)",
        "start_offset": 40,
        "end_offset": 42,
        "article_start_offset": 0,
        "article_end_offset": 42,
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
                "chunk_id": "LAW_1__article_1__clause_1__point_a__chunk",
                "source_node_id": "LAW_1__article_1__clause_1__point_a",
                "context": {"accepted": True},
            }
        ],
    }
    payload.update(overrides)
    return LegalChunk.model_validate(payload)


def _payload(chunk: LegalChunk | None = None) -> VectorPayload:
    """Build a payload with stable embedding provenance."""
    return build_vector_payload(
        chunk or _chunk(),
        embedding_model="BAAI/bge-m3",
        embedding_revision="revision-1",
        indexing_run_id="run-2026-06-10",
    )


class TestBuildVectorPayload:
    """Legal traceability and non-inference payload tests."""

    def test_preserves_required_legal_fields(self) -> None:
        chunk = _chunk()

        payload = _payload(chunk)

        assert payload.chunk_id == chunk.chunk_id
        assert payload.law_id == chunk.law_id
        assert payload.law_name == chunk.law_name
        assert payload.level == chunk.level
        assert payload.chunk_kind == chunk.chunk_kind
        assert payload.article_number == chunk.article_number
        assert payload.article_title == chunk.article_title
        assert payload.clause_number == chunk.clause_number
        assert payload.point_label == chunk.point_label
        assert payload.citation == chunk.citation
        assert payload.hierarchy_path == chunk.hierarchy_path
        assert payload.source_node_id == chunk.source_node_id
        assert payload.parent_article_node_id == chunk.parent_article_node_id
        assert payload.parent_chunk_id == chunk.parent_chunk_id

    def test_preserves_text_and_hashes_exactly(self) -> None:
        text = "a) Nội dung tiếng Việt.  \n"
        parent_text = "Điều 1.\n1. Nội dung\n" + text
        chunk = _chunk(
            text=text,
            parent_text=parent_text,
            end_offset=65,
            article_end_offset=65,
        )

        payload = _payload(chunk)

        assert payload.text == text
        assert payload.parent_text == parent_text
        assert payload.text_hash == chunk.text_hash
        assert payload.parent_text_hash == chunk.parent_text_hash

    def test_preserves_source_fields(self) -> None:
        chunk = _chunk()

        payload = _payload(chunk)

        assert payload.source_url == chunk.source_url
        assert payload.source_domain == chunk.source_domain
        assert payload.source_type == chunk.source_type
        assert payload.source_file == chunk.source_file

    def test_deep_copies_metadata_and_warnings(self) -> None:
        chunk = _chunk()
        original = chunk.model_dump(mode="json")

        payload = _payload(chunk)

        assert chunk.model_dump(mode="json") == original
        assert payload.metadata == chunk.metadata
        assert payload.metadata is not chunk.metadata
        assert payload.warnings == chunk.warnings
        assert payload.warnings is not chunk.warnings
        assert payload.warnings[0] is not chunk.warnings[0]

    def test_adds_embedding_and_indexing_provenance(self) -> None:
        payload = _payload()

        assert payload.schema_version == "0.1.0"
        assert payload.embedding_model == "BAAI/bge-m3"
        assert payload.embedding_revision == "revision-1"
        assert payload.indexing_run_id == "run-2026-06-10"

    def test_does_not_infer_temporal_status_or_domain_metadata(self) -> None:
        payload = _payload()

        assert payload.effective_date is None
        assert payload.expiry_date is None
        assert payload.status is None
        assert payload.domain_tags == []

    def test_preserves_short_chunk(self) -> None:
        payload = _payload(_chunk(text="a", end_offset=41))

        assert payload.text == "a"

    def test_duplicate_text_chunks_remain_distinct(self) -> None:
        first = _payload(_chunk(chunk_id="chunk-1"))
        second = _payload(_chunk(chunk_id="chunk-2"))

        assert first.text == second.text
        assert first.chunk_id != second.chunk_id

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("embedding_model", " "),
            ("embedding_revision", " "),
            ("indexing_run_id", ""),
            ("payload_schema_version", " "),
        ],
    )
    def test_rejects_blank_provenance(self, field: str, value: str) -> None:
        kwargs: dict[str, object] = {
            "embedding_model": "BAAI/bge-m3",
            "embedding_revision": None,
            "indexing_run_id": "run-1",
            "payload_schema_version": "0.1.0",
        }
        kwargs[field] = value

        with pytest.raises(ValueError, match="must not be blank"):
            build_vector_payload(_chunk(), **kwargs)


class TestPayloadSerialization:
    """Qdrant-ready dictionary serialization tests."""

    def test_returns_deterministic_json_compatible_dict(self) -> None:
        payload = _payload()

        first = vector_payload_to_qdrant_payload(payload)
        second = vector_payload_to_qdrant_payload(payload)

        assert first == second
        assert first["level"] == "point"
        assert first["metadata"]["source_warnings"] == ["SOURCE_NOTE_EXCLUDED"]
        assert first["warnings"][0]["code"] == "EMPTY_CHUNK_TEXT"
        assert first["effective_date"] is None
        assert first["domain_tags"] == []

    def test_contains_no_vector_values(self) -> None:
        serialized = vector_payload_to_qdrant_payload(_payload())

        assert "values" not in serialized
        assert "vector" not in serialized
        assert "dense" not in serialized


class TestBuildPointId:
    """Deterministic UUIDv5 point identifier tests."""

    def test_is_deterministic_and_valid_uuid(self) -> None:
        first = build_point_id("chunk-1", namespace="vnlaw-qa-legal-chunks")
        second = build_point_id("chunk-1", namespace="vnlaw-qa-legal-chunks")

        assert first == second
        assert uuid.UUID(first).version == 5

    def test_differs_for_different_chunk_ids(self) -> None:
        first = build_point_id("chunk-1", namespace="vnlaw-qa-legal-chunks")
        second = build_point_id("chunk-2", namespace="vnlaw-qa-legal-chunks")

        assert first != second

    def test_rejects_blank_chunk_id(self) -> None:
        with pytest.raises(ValueError, match="chunk_id must not be blank"):
            build_point_id(" ", namespace="vnlaw-qa-legal-chunks")

    def test_rejects_blank_namespace(self) -> None:
        with pytest.raises(ValueError, match="namespace must not be blank"):
            build_point_id("chunk-1", namespace="")
