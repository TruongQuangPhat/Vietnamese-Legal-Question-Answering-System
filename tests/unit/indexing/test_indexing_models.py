"""Unit tests for Phase 8 indexing configuration and typed contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.indexing.indexing_models import (
    DenseEmbedding,
    EmbeddingInput,
    IndexingConfig,
    IndexingReport,
    SparseEmbedding,
    VectorPayload,
)

CONFIG_PATH = Path("configs/indexing/embedding_indexing.yml")


def _load_config() -> IndexingConfig:
    """Load the repository's default Slice 8A YAML configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file)
    return IndexingConfig.model_validate(payload)


def _config_payload() -> dict[str, object]:
    """Return a mutable serialized copy of the default indexing config."""
    return _load_config().model_dump(mode="python")


def _embedding_input(**overrides: object) -> EmbeddingInput:
    """Build one valid embedding input contract."""
    payload: dict[str, object] = {
        "chunk_id": "BLDS_2015__article_1__chunk",
        "law_id": "BLDS_2015",
        "chunk_kind": "article_level",
        "level": "article",
        "embedding_text": "Điều 1. Phạm vi điều chỉnh",
        "text_hash": "text-hash",
        "parent_text_hash": "parent-text-hash",
        "citation": "Bộ luật Dân sự 2015, Điều 1",
        "hierarchy_path": "Bộ luật Dân sự 2015 / Điều 1",
    }
    payload.update(overrides)
    return EmbeddingInput(**payload)


def _vector_payload(**overrides: object) -> VectorPayload:
    """Build one valid vector payload preserving legal traceability."""
    payload: dict[str, object] = {
        "schema_version": "0.1.0",
        "chunk_id": "BLDS_2015__article_1__chunk",
        "law_id": "BLDS_2015",
        "law_name": "Bộ luật Dân sự 2015",
        "level": "article",
        "chunk_kind": "article_level",
        "article_number": "1",
        "article_title": "Phạm vi điều chỉnh",
        "clause_number": None,
        "point_label": None,
        "citation": "Bộ luật Dân sự 2015, Điều 1",
        "hierarchy_path": "Bộ luật Dân sự 2015 / Điều 1",
        "source_node_id": "BLDS_2015__article_1",
        "parent_article_node_id": "BLDS_2015__article_1",
        "parent_chunk_id": "BLDS_2015__article_1__parent",
        "text": "Điều 1. Phạm vi điều chỉnh",
        "parent_text": "Điều 1. Phạm vi điều chỉnh\nNội dung điều luật.",
        "text_hash": "text-hash",
        "parent_text_hash": "parent-text-hash",
        "source_url": "https://thuvienphapluat.vn/example",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "source_file": "data/interim/BLDS_2015/hierarchy.json",
        "metadata": {
            "is_empty_or_repealed": False,
            "is_source_unit_repealed": False,
            "source_warnings": [],
            "caveat_references": [],
        },
        "warnings": [],
        "embedding_model": "BAAI/bge-m3",
        "embedding_revision": None,
        "indexing_run_id": "planned-run",
    }
    payload.update(overrides)
    return VectorPayload(**payload)


class TestIndexingConfig:
    """Validation tests for the complete Slice 8A configuration."""

    def test_default_config_loads(self) -> None:
        config = _load_config()

        assert config.embedding.model_name == "BAAI/bge-m3"
        assert config.embedding.dense_dimension is None
        assert config.embedding.dense_dimension_policy == "measure_from_model_output"
        assert config.sparse.enabled is False
        assert config.qdrant.recreate is False
        assert config.qdrant.resume is True
        assert config.payload.unknown_temporal_metadata_policy == "store_null_do_not_infer"

    @pytest.mark.parametrize(
        ("section", "field"),
        [
            ("embedding", "batch_size"),
            ("indexing", "batch_size"),
        ],
    )
    def test_rejects_non_positive_batch_sizes(self, section: str, field: str) -> None:
        payload = _config_payload()
        section_payload = payload[section]
        assert isinstance(section_payload, dict)
        section_payload[field] = 0

        with pytest.raises(ValidationError):
            IndexingConfig.model_validate(payload)

    def test_rejects_invalid_text_template(self) -> None:
        payload = _config_payload()
        embedding = payload["embedding"]
        assert isinstance(embedding, dict)
        embedding["text_template"] = "parent_text"

        with pytest.raises(ValidationError):
            IndexingConfig.model_validate(payload)

    @pytest.mark.parametrize(
        ("section", "field"),
        [
            ("embedding", "model_name"),
            ("qdrant", "collection_name"),
        ],
    )
    def test_rejects_blank_required_names(self, section: str, field: str) -> None:
        payload = _config_payload()
        section_payload = payload[section]
        assert isinstance(section_payload, dict)
        section_payload[field] = "   "

        with pytest.raises(ValidationError):
            IndexingConfig.model_validate(payload)

    def test_allows_null_dense_dimension(self) -> None:
        assert _load_config().embedding.dense_dimension is None

    @pytest.mark.parametrize("dimension", [0, -1])
    def test_rejects_non_positive_dense_dimension(self, dimension: int) -> None:
        payload = _config_payload()
        embedding = payload["embedding"]
        assert isinstance(embedding, dict)
        embedding["dense_dimension"] = dimension

        with pytest.raises(ValidationError):
            IndexingConfig.model_validate(payload)

    def test_rejects_same_enabled_dense_and_sparse_vector_names(self) -> None:
        payload = _config_payload()
        sparse = payload["sparse"]
        embedding = payload["embedding"]
        assert isinstance(sparse, dict)
        assert isinstance(embedding, dict)
        sparse["enabled"] = True
        sparse["vector_name"] = embedding["dense_vector_name"]

        with pytest.raises(ValidationError):
            IndexingConfig.model_validate(payload)


class TestEmbeddingContracts:
    """Validation tests for dense, sparse, and input embedding contracts."""

    def test_embedding_input_rejects_blank_embedding_text(self) -> None:
        with pytest.raises(ValidationError):
            _embedding_input(embedding_text="   ")

    def test_dense_embedding_rejects_empty_vector(self) -> None:
        with pytest.raises(ValidationError):
            DenseEmbedding(
                chunk_id="chunk-1",
                values=[],
                dimension=0,
                model_name="BAAI/bge-m3",
            )

    def test_dense_embedding_rejects_dimension_mismatch(self) -> None:
        with pytest.raises(ValidationError):
            DenseEmbedding(
                chunk_id="chunk-1",
                values=[0.1, 0.2],
                dimension=3,
                model_name="BAAI/bge-m3",
            )

    @pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
    def test_dense_embedding_rejects_non_finite_values(self, invalid_value: float) -> None:
        with pytest.raises(ValidationError):
            DenseEmbedding(
                chunk_id="chunk-1",
                values=[0.1, invalid_value],
                dimension=2,
                model_name="BAAI/bge-m3",
            )

    def test_sparse_embedding_rejects_mismatched_lengths(self) -> None:
        with pytest.raises(ValidationError):
            SparseEmbedding(
                chunk_id="chunk-1",
                indices=[1, 4],
                values=[0.5],
                model_name="BAAI/bge-m3",
            )

    def test_sparse_embedding_rejects_negative_indices(self) -> None:
        with pytest.raises(ValidationError):
            SparseEmbedding(
                chunk_id="chunk-1",
                indices=[-1],
                values=[0.5],
                model_name="BAAI/bge-m3",
            )


class TestVectorPayload:
    """Validation tests for legal traceability payloads."""

    def test_accepts_nullable_temporal_and_status_metadata(self) -> None:
        payload = _vector_payload(
            effective_date=None,
            expiry_date=None,
            status=None,
            domain_tags=[],
        )

        assert payload.effective_date is None
        assert payload.expiry_date is None
        assert payload.status is None
        assert payload.domain_tags == []

    def test_preserves_legal_traceability_fields(self) -> None:
        payload = _vector_payload()

        assert payload.chunk_id == "BLDS_2015__article_1__chunk"
        assert payload.law_id == "BLDS_2015"
        assert payload.article_number == "1"
        assert payload.article_title == "Phạm vi điều chỉnh"
        assert payload.citation == "Bộ luật Dân sự 2015, Điều 1"
        assert payload.parent_article_node_id == "BLDS_2015__article_1"
        assert payload.text_hash == "text-hash"
        assert payload.parent_text_hash == "parent-text-hash"
        assert payload.source_domain == "thuvienphapluat.vn"
        assert payload.metadata.is_empty_or_repealed is False
        assert payload.warnings == []


class TestIndexingReport:
    """Validation tests for the non-executing indexing report contract."""

    def test_represents_planned_not_yet_run_report(self) -> None:
        report = IndexingReport(
            schema_version="0.1.0",
            status="planned",
            processed_validation_status="pass_with_warnings",
            processed_validation_errors_total=0,
            processed_validation_invalid_chunks=0,
            processed_validation_warnings_total=8206,
            processed_validation_embedding_ready=True,
            processed_validation_payload_ready_rate=1.0,
            input_chunks_path="data/processed/legal_chunks.jsonl",
            input_chunk_count=40389,
            expected_chunk_count=40389,
            model_name="BAAI/bge-m3",
            model_revision=None,
            dense_vector_name="dense",
            dense_dimension=None,
            sparse_enabled=False,
            collection_name="vnlaw_chunks_bgem3_v1",
            indexed_points=0,
            failed_chunks=0,
            issues=[],
            payload_completeness_rate=0.0,
        )

        assert report.status == "planned"
        assert report.dense_dimension is None
        assert report.indexed_points == 0
        assert report.processed_validation_status == "pass_with_warnings"
