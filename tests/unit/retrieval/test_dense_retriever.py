"""Unit tests for the dense retrieval baseline dense retriever."""

from __future__ import annotations

import asyncio
import math
import time
from types import SimpleNamespace
from typing import Any

import pytest

from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.models import RetrievalFilters, RetrievalQuery


class FakeMatchValue:
    """Qdrant-shaped exact match."""

    def __init__(self, *, value: Any) -> None:
        self.value = value


class FakeFieldCondition:
    """Qdrant-shaped field condition."""

    def __init__(self, *, key: str, match: FakeMatchValue) -> None:
        self.key = key
        self.match = match


class FakeFilter:
    """Qdrant-shaped filter."""

    def __init__(self, *, must: list[FakeFieldCondition]) -> None:
        self.must = must


class FakeQdrantModels:
    """Subset of Qdrant models needed for retrieval filter tests."""

    Filter = FakeFilter
    FieldCondition = FakeFieldCondition
    MatchValue = FakeMatchValue


class FakeEmbedder:
    """Query embedder fake with configurable vector output."""

    def __init__(
        self,
        vector: list[float] | None = None,
        *,
        fail: bool = False,
        delay_seconds: float = 0.0,
    ) -> None:
        self.vector = vector if vector is not None else [1.0, 0.0, 0.0]
        self.fail = fail
        self.delay_seconds = delay_seconds
        self.calls: list[tuple[str, int]] = []

    def embed_query(self, query_text: str, *, batch_size: int = 1) -> list[float]:
        self.calls.append((query_text, batch_size))
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return self.vector


class FakeQdrantClient:
    """Read-only Qdrant fake with mutation traps."""

    def __init__(
        self,
        *,
        points: list[Any] | None = None,
        fail_query: bool = False,
        delay_seconds: float = 0.0,
    ) -> None:
        self.points = points if points is not None else [make_point()]
        self.fail_query = fail_query
        self.delay_seconds = delay_seconds
        self.query_calls: list[dict[str, Any]] = []
        self.mutation_calls: list[str] = []

    async def query_points(self, **kwargs: Any) -> Any:
        self.query_calls.append(kwargs)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.fail_query:
            raise RuntimeError("qdrant unavailable")
        return SimpleNamespace(points=self.points[: kwargs["limit"]])

    async def upsert(self, **kwargs: Any) -> None:
        self.mutation_calls.append("upsert")
        raise AssertionError("retrieval must not upsert")

    async def delete(self, **kwargs: Any) -> None:
        self.mutation_calls.append("delete")
        raise AssertionError("retrieval must not delete")

    async def update(self, **kwargs: Any) -> None:
        self.mutation_calls.append("update")
        raise AssertionError("retrieval must not update")

    async def delete_collection(self, **kwargs: Any) -> None:
        self.mutation_calls.append("delete_collection")
        raise AssertionError("retrieval must not delete collections")


@pytest.fixture(autouse=True)
def fake_qdrant_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep filter construction independent from qdrant-client."""
    monkeypatch.setattr("src.retrieval.filters._load_qdrant_models", lambda: FakeQdrantModels)


def make_payload(**overrides: Any) -> dict[str, Any]:
    """Build a representative embedding/indexing Qdrant payload."""
    payload: dict[str, Any] = {
        "schema_version": "0.1.0",
        "chunk_id": "chunk-1",
        "law_id": "BLDS_2015",
        "law_name": "Bộ luật Dân sự 2015",
        "level": "clause",
        "chunk_kind": "clause_level",
        "article_number": "1",
        "article_title": "Phạm vi điều chỉnh",
        "clause_number": "1",
        "point_label": None,
        "citation": "Bộ luật Dân sự 2015, Điều 1, Khoản 1",
        "hierarchy_path": "Bộ luật Dân sự 2015 / Điều 1 / Khoản 1",
        "source_node_id": "source-1",
        "parent_article_node_id": "article-1",
        "parent_chunk_id": "article-1__parent",
        "text": "Bộ luật này quy định địa vị pháp lý...",
        "parent_text": "Điều 1. Phạm vi điều chỉnh\nBộ luật này quy định...",
        "text_hash": "text-hash",
        "parent_text_hash": "parent-hash",
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
        "indexing_run_id": "run-1",
        "effective_date": None,
        "expiry_date": None,
        "status": None,
        "domain_tags": [],
    }
    payload.update(overrides)
    return payload


def make_point(
    *,
    point_id: str = "point-1",
    payload: dict[str, Any] | None = None,
    score: float = 0.91,
) -> Any:
    """Build a Qdrant-shaped scored point."""
    return SimpleNamespace(id=point_id, payload=payload or make_payload(), score=score)


def make_retriever(
    *,
    embedder: FakeEmbedder | None = None,
    client: FakeQdrantClient | None = None,
    query_embedding_timeout_seconds: float | None = None,
    qdrant_timeout_seconds: float | None = None,
) -> DenseRetriever:
    """Build a retriever using small fake vectors."""
    return DenseRetriever(
        qdrant_client=client or FakeQdrantClient(),
        embedding_model=embedder or FakeEmbedder(),
        collection_name="dev",
        dense_vector_name="dense",
        expected_vector_dim=3,
        default_top_k=2,
        embedding_batch_size=1,
        query_embedding_timeout_seconds=query_embedding_timeout_seconds,
        qdrant_timeout_seconds=qdrant_timeout_seconds,
    )


@pytest.mark.asyncio
async def test_dense_retriever_calls_qdrant_with_named_vector_and_no_vectors() -> None:
    """Dense retrieval uses named vector search and never requests stored vectors."""
    client = FakeQdrantClient()
    embedder = FakeEmbedder()
    retriever = make_retriever(embedder=embedder, client=client)

    result = await retriever.retrieve(
        "Phạm vi điều chỉnh của Bộ luật Dân sự là gì?",
        filters=RetrievalFilters(law_id="BLDS_2015"),
    )

    assert embedder.calls == [("Phạm vi điều chỉnh của Bộ luật Dân sự là gì?", 1)]
    assert result.results[0].chunk_id == "chunk-1"
    assert result.results[0].citation == "Bộ luật Dân sự 2015, Điều 1, Khoản 1"
    assert client.query_calls[0]["collection_name"] == "dev"
    assert client.query_calls[0]["query"] == [1.0, 0.0, 0.0]
    assert client.query_calls[0]["using"] == "dense"
    assert client.query_calls[0]["with_payload"] is True
    assert client.query_calls[0]["with_vectors"] is False
    assert client.query_calls[0]["limit"] == 2
    assert client.query_calls[0]["query_filter"].must[0].key == "law_id"
    assert client.mutation_calls == []


@pytest.mark.asyncio
async def test_retrieval_query_object_is_supported() -> None:
    """Prevalidated RetrievalQuery objects can be passed directly."""
    client = FakeQdrantClient()
    retriever = make_retriever(client=client)

    result = await retriever.retrieve(RetrievalQuery(query="test", top_k=1, collection_name="dev"))

    assert result.top_k == 1
    assert len(result.results) == 1


@pytest.mark.asyncio
async def test_empty_query_rejected_before_embedding() -> None:
    """Empty queries fail before expensive work."""
    embedder = FakeEmbedder()
    client = FakeQdrantClient()
    retriever = make_retriever(embedder=embedder, client=client)

    with pytest.raises(DenseRetrieverError, match="invalid retrieval query"):
        await retriever.retrieve(" ")


@pytest.mark.asyncio
async def test_query_embedding_timeout_fails_fast() -> None:
    retriever = make_retriever(
        embedder=FakeEmbedder(delay_seconds=0.05),
        query_embedding_timeout_seconds=0.001,
    )

    with pytest.raises(DenseRetrieverError, match="query embedding timed out"):
        await retriever.retrieve("Câu hỏi hợp lệ?")


@pytest.mark.asyncio
async def test_qdrant_timeout_fails_fast() -> None:
    retriever = make_retriever(
        client=FakeQdrantClient(delay_seconds=0.05),
        qdrant_timeout_seconds=0.001,
    )

    with pytest.raises(DenseRetrieverError, match="Qdrant dense retrieval timed out"):
        await retriever.retrieve("Câu hỏi hợp lệ?")


@pytest.mark.asyncio
async def test_vector_dimension_mismatch_rejected_before_qdrant() -> None:
    """Wrong query vector dimensions do not reach Qdrant."""
    client = FakeQdrantClient()
    retriever = make_retriever(embedder=FakeEmbedder([1.0, 0.0]), client=client)

    with pytest.raises(DenseRetrieverError, match="dimension"):
        await retriever.retrieve("test")

    assert client.query_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("vector", [[float("nan"), 0.0, 0.0], [math.inf, 0.0, 0.0]])
async def test_non_finite_vector_rejected_before_qdrant(vector: list[float]) -> None:
    """NaN and infinite vectors are rejected before search."""
    client = FakeQdrantClient()
    retriever = make_retriever(embedder=FakeEmbedder(vector), client=client)

    with pytest.raises(DenseRetrieverError, match="finite"):
        await retriever.retrieve("test")

    assert client.query_calls == []


@pytest.mark.asyncio
async def test_non_numeric_vector_rejected_before_qdrant() -> None:
    """Non-numeric vector values are rejected before search."""
    client = FakeQdrantClient()
    retriever = make_retriever(embedder=FakeEmbedder([1.0, "bad", 0.0]), client=client)

    with pytest.raises(DenseRetrieverError, match="numeric"):
        await retriever.retrieve("test")

    assert client.query_calls == []


@pytest.mark.asyncio
async def test_embedding_failure_is_reported() -> None:
    """Embedding failures become retrieval errors."""
    retriever = make_retriever(embedder=FakeEmbedder(fail=True))

    with pytest.raises(DenseRetrieverError, match="query embedding failed"):
        await retriever.retrieve("test")


@pytest.mark.asyncio
async def test_qdrant_failure_is_reported() -> None:
    """Qdrant failures become retrieval errors."""
    retriever = make_retriever(client=FakeQdrantClient(fail_query=True))

    with pytest.raises(DenseRetrieverError, match="Qdrant dense retrieval failed"):
        await retriever.retrieve("test")


@pytest.mark.asyncio
async def test_missing_optional_payload_fields_are_tolerated() -> None:
    """Optional metadata gaps do not discard otherwise valid retrieval hits."""
    payload = make_payload(parent_text=None, article_number=None, warnings=None)
    result = await make_retriever(
        client=FakeQdrantClient(points=[make_point(payload=payload)])
    ).retrieve("test")

    chunk = result.results[0]
    assert chunk.parent_text is None
    assert chunk.article_number is None
    assert chunk.warnings == []
    assert chunk.issues == []


@pytest.mark.asyncio
async def test_missing_critical_payload_field_is_recorded() -> None:
    """Missing critical fields are visible as typed issues."""
    payload = make_payload()
    payload.pop("citation")
    result = await make_retriever(
        client=FakeQdrantClient(points=[make_point(payload=payload)])
    ).retrieve("test")

    chunk = result.results[0]
    assert chunk.citation is None
    assert any(issue.code == "critical_payload_field_missing" for issue in chunk.issues)
    assert result.issues == chunk.issues


@pytest.mark.asyncio
async def test_missing_payload_is_recorded_without_crashing_result_mapping() -> None:
    """A point without object payload produces a typed issue."""
    point = make_point(payload=None)
    point.payload = None
    result = await make_retriever(client=FakeQdrantClient(points=[point])).retrieve("test")

    chunk = result.results[0]
    assert chunk.chunk_id == "point-1"
    assert any(issue.code == "payload_missing" for issue in chunk.issues)


@pytest.mark.asyncio
async def test_invalid_score_fails_mapping() -> None:
    """Scores must be finite numeric values."""
    retriever = make_retriever(client=FakeQdrantClient(points=[make_point(score=float("nan"))]))

    with pytest.raises(DenseRetrieverError, match="invalid score"):
        await retriever.retrieve("test")
