"""Unit tests for bounded Phase 8 indexing orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.index_qdrant_chunks import validate_cli_arguments
from src.indexing.indexing_models import DenseEmbedding, EmbeddingInput
from src.indexing.indexing_service import IndexingService, IndexingServiceError
from src.processing.legal_chunk_models import LegalChunk


def _chunk(
    *,
    chunk_id: str = "chunk-1",
    law_id: str = "LAW_1",
    text: str = "1.",
) -> LegalChunk:
    """Build a minimal validated legal chunk."""
    text_length = len(text)
    return LegalChunk.model_validate(
        {
            "schema_version": "1.0",
            "chunker_version": "v0.1.0",
            "chunk_id": chunk_id,
            "law_id": law_id,
            "law_name": "Luật Thử nghiệm 2026",
            "source_url": "https://thuvienphapluat.vn/example",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "source_file": "data/interim/LAW_1/hierarchy.json",
            "level": "clause",
            "chunk_kind": "clause_level",
            "source_node_id": f"{chunk_id}__source",
            "parent_article_node_id": "LAW_1__article_1",
            "parent_chunk_id": "LAW_1__article_1__parent",
            "article_number": "1",
            "article_title": "Phạm vi điều chỉnh",
            "clause_number": "1",
            "point_label": None,
            "citation": "Luật Thử nghiệm 2026, khoản 1 Điều 1",
            "hierarchy_path": "Luật Thử nghiệm 2026 / Điều 1 / Khoản 1",
            "text": text,
            "parent_text": f"Điều 1. Phạm vi điều chỉnh\n{text}",
            "start_offset": 30,
            "end_offset": 30 + text_length,
            "article_start_offset": 0,
            "article_end_offset": 30 + text_length,
            "text_hash": f"hash-{chunk_id}",
            "parent_text_hash": "parent-hash",
            "metadata": {
                "is_empty_or_repealed": False,
                "is_source_unit_repealed": False,
                "source_warnings": [],
                "caveat_references": [],
            },
            "warnings": [],
        }
    )


class FakeEmbeddingModel:
    """Configurable dense model fake."""

    model_name = "BAAI/bge-m3"
    model_revision = None

    def __init__(
        self,
        *,
        dimension: int = 1024,
        count_offset: int = 0,
        fail_on_call: int | None = None,
    ) -> None:
        self.dimension = dimension
        self.count_offset = count_offset
        self.fail_on_call = fail_on_call
        self.calls: list[list[str]] = []

    def embed_dense(
        self,
        inputs: list[EmbeddingInput],
        *,
        batch_size: int,
    ) -> list[DenseEmbedding]:
        self.calls.append([item.chunk_id for item in inputs])
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("fake embedding failure")
        output_count = max(0, len(inputs) + self.count_offset)
        return [
            DenseEmbedding(
                chunk_id=inputs[index % len(inputs)].chunk_id,
                vector_name="dense",
                values=[1.0] * self.dimension,
                dimension=self.dimension,
                model_name=self.model_name,
            )
            for index in range(output_count)
        ]


class FakePointStruct:
    """Qdrant-shaped point used without the optional dependency."""

    def __init__(self, *, id: str, vector: dict[str, list[float]], payload: dict[str, Any]):
        self.id = id
        self.vector = vector
        self.payload = payload


class FakeQdrantClient:
    """Async Qdrant fake that captures upsert batches."""

    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.fail_on_call = fail_on_call
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
        if self.fail_on_call == len(self.upsert_calls):
            raise RuntimeError("fake Qdrant failure")
        return SimpleNamespace(status=SimpleNamespace(value="completed"))


@pytest.fixture(autouse=True)
def fake_qdrant_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep service tests independent of qdrant-client."""
    monkeypatch.setattr(
        "src.indexing.indexing_service._load_qdrant_models",
        lambda: SimpleNamespace(PointStruct=FakePointStruct),
    )


def _service(
    *,
    model: FakeEmbeddingModel | None = None,
    client: FakeQdrantClient | None = None,
    batch_size: int = 2,
    indexing_run_id: str = "run-8f-test",
) -> IndexingService:
    """Build a service with stable test configuration."""
    return IndexingService(
        qdrant_client=client,
        embedding_model=model,
        collection_name="vnlaw_chunks_bgem3_v1_dev",
        point_id_namespace="vnlaw-qa-legal-chunks",
        dense_vector_name="dense",
        dense_dimension=1024,
        batch_size=batch_size,
        indexing_run_id=indexing_run_id,
        model_name="BAAI/bge-m3",
    )


@pytest.mark.asyncio
async def test_dry_run_does_not_embed_or_upsert() -> None:
    """Dry-run performs deterministic planning without heavy dependencies."""
    model = FakeEmbeddingModel()
    client = FakeQdrantClient()

    report = await _service(model=model, client=client).index_chunks(
        [_chunk(chunk_id="chunk-1"), _chunk(chunk_id="chunk-2")],
        input_path="chunks.jsonl",
        dry_run=True,
    )

    assert report.status == "dry_run"
    assert report.planned_count == 2
    assert report.would_embed_count == 2
    assert report.would_upsert_count == 2
    assert report.embedded_count == 0
    assert report.upserted_count == 0
    assert model.calls == []
    assert client.upsert_calls == []


@pytest.mark.asyncio
async def test_real_indexing_embeds_and_upserts_named_vectors() -> None:
    """Real batches preserve order and use the configured named dense vector."""
    model = FakeEmbeddingModel()
    client = FakeQdrantClient()

    report = await _service(model=model, client=client).index_chunks(
        [_chunk(chunk_id="chunk-1"), _chunk(chunk_id="chunk-2")],
        input_path="chunks.jsonl",
    )

    assert report.status == "success"
    assert report.embedded_count == 2
    assert report.upserted_count == 2
    assert model.calls == [["chunk-1", "chunk-2"]]
    points = client.upsert_calls[0]["points"]
    assert [point.payload["chunk_id"] for point in points] == ["chunk-1", "chunk-2"]
    assert all(set(point.vector) == {"dense"} for point in points)
    assert all(len(point.vector["dense"]) == 1024 for point in points)


@pytest.mark.parametrize("batch_size", [0, -1])
def test_batch_size_must_be_positive(batch_size: int) -> None:
    """Invalid batch sizes fail before any model or Qdrant work."""
    with pytest.raises(IndexingServiceError, match="batch_size must be positive"):
        _service(batch_size=batch_size)


@pytest.mark.asyncio
async def test_dimension_mismatch_fails_batch_and_reports_chunk_ids() -> None:
    """A model dimension mismatch cannot reach Qdrant."""
    client = FakeQdrantClient()

    report = await _service(
        model=FakeEmbeddingModel(dimension=3),
        client=client,
    ).index_chunks([_chunk()], input_path="chunks.jsonl")

    assert report.status == "failed"
    assert report.failed_chunk_ids == ["chunk-1"]
    assert "dense dimension mismatch" in report.issues[0].message
    assert client.upsert_calls == []


@pytest.mark.asyncio
async def test_vector_count_mismatch_fails_batch() -> None:
    """A missing embedding row is reported for the complete affected batch."""
    report = await _service(
        model=FakeEmbeddingModel(count_offset=-1),
        client=FakeQdrantClient(),
    ).index_chunks(
        [_chunk(chunk_id="chunk-1"), _chunk(chunk_id="chunk-2")],
        input_path="chunks.jsonl",
    )

    assert report.status == "failed"
    assert report.failed_chunk_ids == ["chunk-1", "chunk-2"]
    assert "dense vector count mismatch" in report.issues[0].message


@pytest.mark.asyncio
async def test_duplicate_text_uses_distinct_deterministic_point_ids() -> None:
    """Duplicate legal text remains separate through deterministic chunk IDs."""
    client = FakeQdrantClient()
    chunks = [
        _chunk(chunk_id="chunk-1", text="Nội dung giống nhau"),
        _chunk(chunk_id="chunk-2", text="Nội dung giống nhau"),
    ]

    first = await _service(
        model=FakeEmbeddingModel(),
        client=client,
    ).index_chunks(chunks, input_path="chunks.jsonl")
    first_ids = [point.id for point in client.upsert_calls[0]["points"]]

    second_client = FakeQdrantClient()
    second = await _service(
        model=FakeEmbeddingModel(),
        client=second_client,
        indexing_run_id="run-8f-rerun",
    ).index_chunks(chunks, input_path="chunks.jsonl")
    second_ids = [point.id for point in second_client.upsert_calls[0]["points"]]

    assert first.status == second.status == "success"
    assert first_ids[0] != first_ids[1]
    assert first_ids == second_ids


@pytest.mark.asyncio
async def test_short_chunk_is_not_dropped() -> None:
    """A one-character legal chunk reaches the payload and vector batch."""
    client = FakeQdrantClient()

    report = await _service(
        model=FakeEmbeddingModel(),
        client=client,
    ).index_chunks([_chunk(text="a")], input_path="chunks.jsonl")

    assert report.upserted_count == 1
    assert client.upsert_calls[0]["points"][0].payload["text"] == "a"


@pytest.mark.asyncio
async def test_failed_batch_records_ids_and_continues() -> None:
    """A failed first upsert can produce an honest partial-success result."""
    client = FakeQdrantClient(fail_on_call=1)

    report = await _service(
        model=FakeEmbeddingModel(),
        client=client,
        batch_size=1,
    ).index_chunks(
        [_chunk(chunk_id="chunk-1"), _chunk(chunk_id="chunk-2")],
        input_path="chunks.jsonl",
    )

    assert report.status == "partial_success"
    assert report.failed_chunk_ids == ["chunk-1"]
    assert report.embedded_count == 2
    assert report.upserted_count == 1
    assert len(client.upsert_calls) == 2


@pytest.mark.asyncio
async def test_limit_and_law_filter_apply_before_batching() -> None:
    """Limit counts matching chunks while filtered records remain visible."""
    model = FakeEmbeddingModel()

    report = await _service(
        model=model,
        client=FakeQdrantClient(),
    ).index_chunks(
        [
            _chunk(chunk_id="chunk-1", law_id="LAW_1"),
            _chunk(chunk_id="chunk-2", law_id="LAW_2"),
            _chunk(chunk_id="chunk-3", law_id="LAW_2"),
        ],
        input_path="chunks.jsonl",
        law_id="LAW_2",
        limit=1,
    )

    assert report.total_seen == 2
    assert report.skipped_count == 1
    assert report.planned_count == 1
    assert model.calls == [["chunk-2"]]


@pytest.mark.asyncio
async def test_checkpoint_written_after_successful_batch(tmp_path: Path) -> None:
    """Checkpoint captures deterministic progress after successful upsert."""
    checkpoint_path = tmp_path / "checkpoint.json"

    await _service(
        model=FakeEmbeddingModel(),
        client=FakeQdrantClient(),
    ).index_chunks(
        [_chunk(chunk_id="chunk-1")],
        input_path="chunks.jsonl",
        checkpoint_path=checkpoint_path,
    )

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["indexing_run_id"] == "run-8f-test"
    assert checkpoint["processed_chunk_ids"] == ["chunk-1"]
    assert checkpoint["upserted_count"] == 1


@pytest.mark.asyncio
async def test_checkpoint_records_final_failed_batch(tmp_path: Path) -> None:
    """A failed final batch remains visible in the enabled checkpoint."""
    checkpoint_path = tmp_path / "checkpoint.json"

    await _service(
        model=FakeEmbeddingModel(dimension=3),
        client=FakeQdrantClient(),
    ).index_chunks(
        [_chunk(chunk_id="chunk-1")],
        input_path="chunks.jsonl",
        checkpoint_path=checkpoint_path,
    )

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["processed_chunk_ids"] == []
    assert checkpoint["upserted_count"] == 0
    assert checkpoint["failed_chunk_ids"] == ["chunk-1"]


@pytest.mark.parametrize("kind", ["output", "checkpoint"])
def test_cli_rejects_protected_paths(kind: str) -> None:
    """Reports and checkpoints cannot be written under protected trees."""
    output = Path("/tmp/report.json")
    checkpoint = None
    if kind == "output":
        output = Path("artifacts/reports/indexing/report.json")
    else:
        checkpoint = Path("data/processed/checkpoint.json")

    with pytest.raises(ValueError, match="protected"):
        validate_cli_arguments(
            output_path=output,
            checkpoint_path=checkpoint,
            limit=3,
            batch_size=2,
            dry_run=False,
            allow_full_corpus=False,
        )


def test_cli_requires_limit_for_real_indexing() -> None:
    """Unbounded real indexing requires an explicit operational override."""
    with pytest.raises(ValueError, match="requires --limit"):
        validate_cli_arguments(
            output_path=Path("/tmp/report.json"),
            checkpoint_path=None,
            limit=None,
            batch_size=2,
            dry_run=False,
            allow_full_corpus=False,
        )
