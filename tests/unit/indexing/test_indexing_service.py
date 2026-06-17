"""Unit tests for bounded Phase 8 indexing orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.indexing.index_qdrant_chunks import (
    load_processed_validation_report,
    validate_cli_arguments,
)
from src.indexing.indexing_models import (
    DenseEmbedding,
    EmbeddingInput,
    IndexingCheckpoint,
    IndexingReport,
)
from src.indexing.indexing_service import (
    IndexingService,
    IndexingServiceError,
    load_indexing_checkpoint,
)
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

    def __init__(
        self,
        *,
        fail_upsert_times: int = 0,
        collection_counts: list[tuple[int, int]] | None = None,
    ) -> None:
        self.fail_upsert_times = fail_upsert_times
        self.collection_counts = collection_counts or [(0, 0)]
        self.upsert_calls: list[dict[str, Any]] = []
        self.get_collection_calls = 0

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
        if len(self.upsert_calls) <= self.fail_upsert_times:
            raise RuntimeError("fake Qdrant failure")
        return SimpleNamespace(status=SimpleNamespace(value="completed"))

    async def get_collection(self, collection_name: str) -> Any:
        index = min(self.get_collection_calls, len(self.collection_counts) - 1)
        self.get_collection_calls += 1
        points_count, indexed_vectors_count = self.collection_counts[index]
        return SimpleNamespace(
            points_count=points_count,
            indexed_vectors_count=indexed_vectors_count,
        )


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
    client = FakeQdrantClient(fail_upsert_times=1)

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
    assert checkpoint["checkpoint_type"] == "indexing_checkpoint"
    assert checkpoint["run_type"] == "development_indexing"
    assert checkpoint["pipeline_stage"] == "embedding_indexing"
    assert checkpoint["dense_vector_name"] == "dense"
    assert checkpoint["embedding_model"] == "BAAI/bge-m3"
    assert checkpoint["text_template"] == "text_only"
    assert checkpoint["input_path"] == "chunks.jsonl"
    assert checkpoint["processed_chunk_ids"] == ["chunk-1"]
    assert checkpoint["upserted_count"] == 1
    assert not checkpoint_path.with_name(f".{checkpoint_path.name}.tmp").exists()


@pytest.mark.asyncio
async def test_official_checkpoint_uses_only_operational_metadata(tmp_path: Path) -> None:
    """Official checkpoint serialization excludes development milestone labels."""
    checkpoint_path = tmp_path / "checkpoint.json"

    await _service(
        model=FakeEmbeddingModel(),
        client=FakeQdrantClient(),
        indexing_run_id="official-run",
    ).index_chunks(
        [_chunk(chunk_id="chunk-1")],
        input_path="data/processed/legal_chunks.jsonl",
        run_type="official_full_indexing",
        pipeline_stage="embedding_indexing",
        checkpoint_path=checkpoint_path,
    )

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    serialized = json.dumps(checkpoint)
    assert checkpoint["checkpoint_type"] == "indexing_checkpoint"
    assert checkpoint["run_type"] == "official_full_indexing"
    assert checkpoint["pipeline_stage"] == "embedding_indexing"
    assert "phase" not in checkpoint
    assert "slice" not in checkpoint
    assert all(label not in serialized for label in ("8F", "8G", "8H"))


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
            resume=False,
            max_retries=0,
            retry_backoff_seconds=0,
        )


@pytest.mark.parametrize(
    ("output_path", "checkpoint_path"),
    [
        (
            Path("artifacts/reports/indexing/20260611_bgem3_v1_full/indexing_report_1000.json"),
            None,
        ),
        (
            Path("/tmp/report.json"),
            Path("artifacts/reports/indexing/20260611_bgem3_v1_full/checkpoint_1000.json"),
        ),
    ],
)
def test_cli_allows_official_indexing_run_artifacts(
    output_path: Path,
    checkpoint_path: Path | None,
) -> None:
    """Reports and checkpoints may live in one named official run directory."""
    validate_cli_arguments(
        output_path=output_path,
        checkpoint_path=checkpoint_path,
        limit=1000,
        batch_size=4,
        dry_run=False,
        allow_full_corpus=False,
        resume=False,
        max_retries=0,
        retry_backoff_seconds=0,
    )


@pytest.mark.parametrize(
    "path",
    [
        Path("artifacts/reports/random.json"),
        Path("artifacts/reports/indexing/report.json"),
        Path("artifacts/reports/chunking/indexing_report.json"),
        Path("artifacts/reports/evaluation/indexing_report.json"),
        Path("artifacts/reports/indexing/20260611_bgem3_v1_full/nested/indexing_report.json"),
    ],
)
def test_cli_rejects_unrelated_report_artifact_paths(path: Path) -> None:
    """The indexing allowlist does not open other report trees or layouts."""
    with pytest.raises(ValueError, match="protected"):
        validate_cli_arguments(
            output_path=path,
            checkpoint_path=None,
            limit=3,
            batch_size=2,
            dry_run=False,
            allow_full_corpus=False,
            resume=False,
            max_retries=0,
            retry_backoff_seconds=0,
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
            resume=False,
            max_retries=0,
            retry_backoff_seconds=0,
        )


def _checkpoint(**overrides: object) -> IndexingCheckpoint:
    """Build a compatible resumable checkpoint."""
    payload: dict[str, object] = {
        "indexing_run_id": "run-resume",
        "collection_name": "vnlaw_chunks_bgem3_v1_dev",
        "dense_vector_name": "dense",
        "dense_dimension": 1024,
        "embedding_model": "BAAI/bge-m3",
        "embedding_revision": None,
        "text_template": "text_only",
        "input_path": "chunks.jsonl",
        "law_id_filter": None,
        "payload_schema_version": "0.1.0",
        "processed_chunk_ids": ["chunk-1"],
        "processed_count": 1,
        "upserted_count": 1,
        "failed_chunk_ids": [],
    }
    payload.update(overrides)
    return IndexingCheckpoint.model_validate(payload)


@pytest.mark.asyncio
async def test_resume_skips_processed_chunks_and_reuses_run_id() -> None:
    """Resume skips successful IDs and preserves the original indexing run ID."""
    model = FakeEmbeddingModel()
    client = FakeQdrantClient()

    report = await _service(model=model, client=client).index_chunks(
        [_chunk(chunk_id="chunk-1"), _chunk(chunk_id="chunk-2")],
        input_path="chunks.jsonl",
        limit=2,
        resume_checkpoint=_checkpoint(),
    )

    assert report.resume is True
    assert report.indexing_run_id == "run-resume"
    assert report.resumed_from_indexing_run_id == "run-resume"
    assert report.checkpoint_processed_count == 1
    assert report.skipped_due_to_checkpoint_count == 1
    assert model.calls == [["chunk-2"]]
    assert client.upsert_calls[0]["points"][0].payload["chunk_id"] == "chunk-2"

    standalone_client = FakeQdrantClient()
    await _service(
        model=FakeEmbeddingModel(),
        client=standalone_client,
        indexing_run_id="different-run",
    ).index_chunks([_chunk(chunk_id="chunk-2")], input_path="chunks.jsonl")
    assert (
        client.upsert_calls[0]["points"][0].id == standalone_client.upsert_calls[0]["points"][0].id
    )


@pytest.mark.asyncio
async def test_resume_does_not_skip_failed_checkpoint_ids() -> None:
    """Failed checkpoint IDs remain eligible for another attempt."""
    model = FakeEmbeddingModel()

    report = await _service(
        model=model,
        client=FakeQdrantClient(),
    ).index_chunks(
        [_chunk(chunk_id="chunk-1")],
        input_path="chunks.jsonl",
        resume_checkpoint=_checkpoint(
            processed_chunk_ids=[],
            processed_count=0,
            upserted_count=0,
            failed_chunk_ids=["chunk-1"],
        ),
    )

    assert report.status == "success"
    assert report.skipped_due_to_checkpoint_count == 0
    assert model.calls == [["chunk-1"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("collection_name", "other"),
        ("dense_vector_name", "other"),
        ("dense_dimension", 768),
        ("embedding_model", "other/model"),
        ("text_template", "citation_plus_text"),
        ("input_path", "other.jsonl"),
        ("law_id_filter", "LAW_2"),
        ("payload_schema_version", "0.2.0"),
    ],
)
async def test_resume_rejects_incompatible_checkpoint(field: str, value: object) -> None:
    """Compatibility mismatches fail before embedding or upsert."""
    checkpoint = _checkpoint(**{field: value})

    with pytest.raises(IndexingServiceError, match=field):
        await _service(
            model=FakeEmbeddingModel(),
            client=FakeQdrantClient(),
        ).index_chunks(
            [_chunk()],
            input_path="chunks.jsonl",
            resume_checkpoint=checkpoint,
        )


def test_checkpoint_loader_accepts_legacy_phase_and_slice(tmp_path: Path) -> None:
    """Complete legacy checkpoints remain resumable after metadata cleanup."""
    path = tmp_path / "checkpoint.json"
    payload = _checkpoint().model_dump(mode="json")
    payload.pop("checkpoint_type")
    payload.pop("run_type")
    payload.pop("pipeline_stage")
    payload.update({"phase": "8", "slice": "8G"})
    path.write_text(json.dumps(payload), encoding="utf-8")

    checkpoint = load_indexing_checkpoint(path)

    assert checkpoint.indexing_run_id == "run-resume"
    assert checkpoint.checkpoint_type == "indexing_checkpoint"
    assert checkpoint.run_type == "development_indexing"
    assert checkpoint.pipeline_stage == "embedding_indexing"
    assert "phase" not in checkpoint.model_dump()
    assert "slice" not in checkpoint.model_dump()


def test_checkpoint_loader_rejects_legacy_incomplete_schema(tmp_path: Path) -> None:
    """Legacy checkpoints still require every resume compatibility field."""
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "phase": "8",
                "slice": "8F",
                "indexing_run_id": "old-run",
                "collection_name": "collection",
                "dense_dimension": 1024,
                "processed_chunk_ids": [],
                "processed_count": 0,
                "upserted_count": 0,
                "failed_chunk_ids": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IndexingServiceError, match="incompatible with indexing resume"):
        load_indexing_checkpoint(path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"processed_count": 2}, "processed_count"),
        ({"upserted_count": 2}, "upserted_count"),
        ({"failed_chunk_ids": ["chunk-1"]}, "disjoint"),
        ({"processed_chunk_ids": ["chunk-1", "chunk-1"], "processed_count": 2}, "duplicates"),
    ],
)
def test_checkpoint_rejects_inconsistent_progress(
    overrides: dict[str, object],
    message: str,
) -> None:
    """Resume state must describe one unambiguous set of persisted points."""
    with pytest.raises(ValueError, match=message):
        _checkpoint(**overrides)


@pytest.mark.asyncio
async def test_transient_qdrant_failure_succeeds_after_retry() -> None:
    """Only the Qdrant upsert is retried after deterministic preparation."""
    client = FakeQdrantClient(fail_upsert_times=1)
    model = FakeEmbeddingModel()

    report = await _service(model=model, client=client).index_chunks(
        [_chunk()],
        input_path="chunks.jsonl",
        max_retries=1,
        retry_backoff_seconds=0,
    )

    assert report.status == "success"
    assert report.retry_attempts_total == 1
    assert report.retried_batch_count == 1
    assert report.permanently_failed_batch_count == 0
    assert len(client.upsert_calls) == 2
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_permanent_qdrant_failure_after_retries_records_ids() -> None:
    """Retry exhaustion records the batch and every affected chunk."""
    client = FakeQdrantClient(fail_upsert_times=3)

    report = await _service(
        model=FakeEmbeddingModel(),
        client=client,
    ).index_chunks(
        [_chunk(chunk_id="chunk-1")],
        input_path="chunks.jsonl",
        max_retries=2,
        retry_backoff_seconds=0,
    )

    assert report.status == "failed"
    assert report.retry_attempts_total == 2
    assert report.retried_batch_count == 1
    assert report.permanently_failed_batch_count == 1
    assert report.failed_chunk_ids == ["chunk-1"]
    assert len(client.upsert_calls) == 3


@pytest.mark.asyncio
async def test_validation_error_is_not_retried() -> None:
    """A deterministic vector mismatch never enters the Qdrant retry loop."""
    client = FakeQdrantClient()

    report = await _service(
        model=FakeEmbeddingModel(dimension=3),
        client=client,
    ).index_chunks(
        [_chunk()],
        input_path="chunks.jsonl",
        max_retries=3,
        retry_backoff_seconds=0,
    )

    assert report.retry_attempts_total == 0
    assert report.permanently_failed_batch_count == 1
    assert client.upsert_calls == []


def _write_processed_validation_report(
    path: Path,
    **overrides: object,
) -> None:
    """Write a minimal processed JSONL validation report."""
    payload: dict[str, object] = {
        "status": "pass_with_warnings",
        "input_path": "chunks.jsonl",
        "errors_total": 0,
        "invalid_chunks": 0,
        "warnings_total": 8206,
        "embedding_readiness": {
            "embedding_ready": True,
            "payload_ready_rate": 1.0,
            "warning_count": 8206,
        },
    }
    for key, value in overrides.items():
        if key in {"embedding_ready", "payload_ready_rate"}:
            embedding = dict(payload["embedding_readiness"])
            embedding[key] = value
            payload["embedding_readiness"] = embedding
        else:
            payload[key] = value
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_valid_processed_validation_report_is_accepted(tmp_path: Path) -> None:
    """Accepted warnings remain visible without blocking indexing."""
    path = tmp_path / "validation.json"
    _write_processed_validation_report(path)

    summary = load_processed_validation_report(
        path,
        expected_input_path=Path("chunks.jsonl"),
    )

    assert summary.status == "pass_with_warnings"
    assert summary.warnings_total == 8206
    assert summary.embedding_ready is True
    assert summary.payload_ready_rate == 1.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"errors_total": 1}, "errors_total"),
        ({"invalid_chunks": 1}, "invalid_chunks"),
        ({"embedding_ready": False}, "embedding_ready"),
        ({"payload_ready_rate": 0.99}, "payload_ready_rate"),
    ],
)
def test_invalid_processed_validation_report_fails(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    """Processed validation blockers fail before indexing dependencies load."""
    path = tmp_path / "validation.json"
    _write_processed_validation_report(path, **overrides)

    with pytest.raises(ValueError, match=message):
        load_processed_validation_report(
            path,
            expected_input_path=Path("chunks.jsonl"),
        )


@pytest.mark.asyncio
async def test_no_processed_validation_report_records_not_run() -> None:
    """Absence of an ingested report never implies readiness."""
    report = await _service().index_chunks(
        [_chunk()],
        input_path="chunks.jsonl",
        dry_run=True,
    )

    assert report.processed_validation_status == "not_run"
    assert report.processed_validation_embedding_ready is False


def test_report_contract_has_no_ambiguous_phase7_fields() -> None:
    """Operational report fields use processed-validation-specific naming."""
    assert not any(name.startswith("phase7_") for name in IndexingReport.model_fields)


@pytest.mark.asyncio
async def test_official_indexing_report_uses_only_operational_metadata() -> None:
    """Official reports contain operational labels without development slices."""
    report = await _service().index_chunks(
        [_chunk()],
        input_path="data/processed/legal_chunks.jsonl",
        report_type="indexing_report",
        run_type="official_full_indexing",
        pipeline_stage="embedding_indexing",
        dry_run=True,
    )

    payload = report.model_dump(mode="json")
    serialized = json.dumps(payload)
    assert payload["report_type"] == "indexing_report"
    assert payload["run_type"] == "official_full_indexing"
    assert payload["pipeline_stage"] == "embedding_indexing"
    assert ("readiness_for_" + "phase" + "9") not in payload
    assert "phase" not in payload
    assert "slice" not in payload
    disallowed_labels = ("Phase", "Slice", "8F", "8G", "8H", "phase" + "9")
    assert all(label not in serialized for label in disallowed_labels)


@pytest.mark.asyncio
async def test_count_reconciliation_accepts_tiny_unindexed_vector_count() -> None:
    """A tiny collection can pass while indexed_vectors_count remains zero."""
    client = FakeQdrantClient(collection_counts=[(3, 0), (4, 0)])

    report = await _service(
        model=FakeEmbeddingModel(),
        client=client,
    ).index_chunks(
        [_chunk()],
        input_path="chunks.jsonl",
        reconcile_counts=True,
    )

    assert report.qdrant_points_count_before == 3
    assert report.qdrant_points_count_after == 4
    assert report.qdrant_indexed_vectors_count_after == 0
    assert report.expected_min_points_after == 3
    assert report.count_reconciliation_status == "pass"


def test_cli_resume_requires_existing_checkpoint(tmp_path: Path) -> None:
    """Resume is explicit and cannot start without a real checkpoint file."""
    with pytest.raises(ValueError, match="does not exist"):
        validate_cli_arguments(
            output_path=Path("/tmp/report.json"),
            checkpoint_path=tmp_path / "missing.json",
            limit=3,
            batch_size=2,
            dry_run=False,
            allow_full_corpus=False,
            resume=True,
            max_retries=0,
            retry_backoff_seconds=0,
        )
