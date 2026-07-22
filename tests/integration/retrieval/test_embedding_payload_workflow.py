"""Integration tests for embedding payload workflow contracts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.indexing.indexing_models import DenseEmbedding, EmbeddingInput
from src.indexing.indexing_service import IndexingService
from src.processing.legal_chunk_models import LegalChunk


class FakeEmbeddingModel:
    """Deterministic chunk embedding fake for workflow tests."""

    model_name = "fake-legal-embedding"
    model_revision = "fixture"

    def __init__(self) -> None:
        self.calls: list[list[EmbeddingInput]] = []

    def embed_dense(
        self,
        inputs: list[EmbeddingInput],
        *,
        batch_size: int,
    ) -> list[DenseEmbedding]:
        self.calls.append(inputs)
        vectors = {
            "chunk-a": [0.1, 0.2, 0.3],
            "chunk-b": [0.2, 0.1, 0.4],
        }
        return [
            DenseEmbedding(
                chunk_id=item.chunk_id,
                vector_name="dense",
                values=vectors[item.chunk_id],
                dimension=3,
                model_name=self.model_name,
                model_revision=self.model_revision,
            )
            for item in inputs
        ]


class FakePointStruct:
    """Qdrant point shape used without importing qdrant-client."""

    def __init__(self, *, id: str, vector: dict[str, list[float]], payload: dict[str, Any]):
        self.id = id
        self.vector = vector
        self.payload = payload


class FakeQdrantClient:
    """Fake Qdrant client that captures upserts and rejects unrelated calls."""

    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, Any]] = []

    async def upsert(
        self,
        *,
        collection_name: str,
        points: list[FakePointStruct],
        wait: bool,
    ) -> Any:
        self.upsert_calls.append(
            {
                "collection_name": collection_name,
                "points": points,
                "wait": wait,
            }
        )
        return SimpleNamespace(status=SimpleNamespace(value="completed"))

    async def query_points(self, **kwargs: Any) -> None:
        raise AssertionError("embedding payload workflow must not query Qdrant")


@pytest.fixture(autouse=True)
def fake_qdrant_point_struct(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the workflow independent from qdrant-client."""

    async def inline_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "src.indexing.indexing_service._load_qdrant_models",
        lambda: SimpleNamespace(PointStruct=FakePointStruct),
    )
    monkeypatch.setattr("src.indexing.indexing_service.asyncio.to_thread", inline_to_thread)


@pytest.mark.asyncio
async def test_embedding_payload_workflow_preserves_vectors_and_legal_metadata() -> None:
    """Chunk text is embedded and legal metadata reaches named-vector payloads."""
    model = FakeEmbeddingModel()
    client = FakeQdrantClient()
    chunks = [
        _legal_chunk(
            chunk_id="chunk-a",
            text="1. Người lao động được trả lương trong thời gian thử việc.",
            law_id="BLLD_2019",
            article_number="24",
            clause_number="1",
            point_label=None,
        ),
        _legal_chunk(
            chunk_id="chunk-b",
            text="a) Giao dịch dân sự có hiệu lực khi chủ thể có năng lực pháp luật.",
            law_id="BLDS_2015",
            article_number="117",
            clause_number="1",
            point_label="a",
        ),
    ]
    service = IndexingService(
        qdrant_client=client,
        embedding_model=model,
        collection_name="fixture_collection",
        point_id_namespace="vnlaw-qa-test",
        dense_vector_name="dense",
        dense_dimension=3,
        batch_size=2,
        indexing_run_id="embedding-payload-workflow",
    )

    report = await service.index_chunks(
        chunks,
        input_path="tmp/legal_chunks.jsonl",
        allow_full_corpus=True,
    )

    assert report.embedded_count == 2
    assert report.upserted_count == 2
    assert [[item.embedding_text for item in call] for call in model.calls] == [
        [chunks[0].text, chunks[1].text]
    ]
    points = client.upsert_calls[0]["points"]
    assert client.upsert_calls[0]["collection_name"] == "fixture_collection"
    assert all(set(point.vector) == {"dense"} for point in points)
    assert [point.vector["dense"] for point in points] == [[0.1, 0.2, 0.3], [0.2, 0.1, 0.4]]
    assert all(len(point.vector["dense"]) == 3 for point in points)
    assert [point.payload["chunk_id"] for point in points] == ["chunk-a", "chunk-b"]
    assert points[0].payload["law_id"] == "BLLD_2019"
    assert points[0].payload["source_url"] == "https://thuvienphapluat.vn/BLLD_2019"
    assert points[0].payload["citation"] == "Luật Kiểm thử, Khoản 1, Điều 24"
    assert points[1].payload["point_label"] == "a"
    assert points[1].payload["metadata"]["is_empty_or_repealed"] is False


def test_embedding_payload_workflow_rejects_missing_required_metadata() -> None:
    """Missing traceability metadata is rejected before embedding or fake Qdrant."""
    with pytest.raises(ValueError, match="source_url"):
        _legal_chunk(source_url="")


def _legal_chunk(
    *,
    chunk_id: str = "chunk-a",
    text: str = "1. Nội dung kiểm thử.",
    law_id: str = "LAW_TEST",
    article_number: str = "1",
    clause_number: str = "1",
    point_label: str | None = None,
    source_url: str | None = None,
) -> LegalChunk:
    """Build a tiny schema-valid legal chunk with traceability metadata."""
    text_length = len(text)
    citation = (
        f"Luật Kiểm thử, Điểm {point_label}, Khoản {clause_number}, Điều {article_number}"
        if point_label
        else f"Luật Kiểm thử, Khoản {clause_number}, Điều {article_number}"
    )
    return LegalChunk.model_validate(
        {
            "schema_version": "1.0",
            "chunker_version": "v0.1.0",
            "chunk_id": chunk_id,
            "law_id": law_id,
            "law_name": "Luật Kiểm thử",
            "source_url": source_url
            if source_url is not None
            else f"https://thuvienphapluat.vn/{law_id}",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "source_file": f"tmp/{law_id}/hierarchy.json",
            "level": "point" if point_label else "clause",
            "chunk_kind": "point_level" if point_label else "clause_level",
            "source_node_id": f"{chunk_id}__source",
            "parent_article_node_id": f"{law_id}__article_{article_number}",
            "parent_chunk_id": f"{law_id}__article_{article_number}__parent",
            "article_number": article_number,
            "article_title": "Quy định kiểm thử",
            "clause_number": clause_number,
            "point_label": point_label,
            "citation": citation,
            "hierarchy_path": f"Luật Kiểm thử / Điều {article_number} / Khoản {clause_number}",
            "text": text,
            "parent_text": f"Điều {article_number}. Quy định kiểm thử\n{text}",
            "start_offset": 0,
            "end_offset": text_length,
            "article_start_offset": 0,
            "article_end_offset": text_length + 30,
            "text_hash": f"hash-{chunk_id}",
            "parent_text_hash": f"parent-hash-{chunk_id}",
            "metadata": {
                "is_empty_or_repealed": False,
                "is_source_unit_repealed": False,
                "source_warnings": [],
                "caveat_references": [],
            },
            "warnings": [],
        }
    )
