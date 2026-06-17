"""Unit tests for safe Qdrant collection schema setup."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.indexing import setup_qdrant_collection
from src.indexing.qdrant_collection import (
    QdrantCollectionError,
    build_collection_plan,
    build_payload_index_specs,
    build_qdrant_client,
    ensure_collection,
)


class FakeEnumValue:
    """Small enum-like value used by fake Qdrant models."""

    def __init__(self, value: str) -> None:
        self.value = value


class FakeVectorParams:
    """Fake named dense vector parameters."""

    def __init__(self, *, size: int, distance: FakeEnumValue) -> None:
        self.size = size
        self.distance = distance


class FakeSparseVectorParams:
    """Fake sparse vector parameters."""


class FakeQdrantModels:
    """Subset of qdrant-client models used by the setup module."""

    VectorParams = FakeVectorParams
    SparseVectorParams = FakeSparseVectorParams
    Distance = FakeEnumValue
    PayloadSchemaType = FakeEnumValue


class FakeQdrantClient:
    """Async fake client limited to collection and payload-index operations."""

    def __init__(self, collection: Any | None = None) -> None:
        self.collection = collection
        self.create_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.payload_index_calls: list[dict[str, Any]] = []
        self.upsert_calls = 0

    async def collection_exists(self, collection_name: str) -> bool:
        return self.collection is not None

    async def get_collection(self, collection_name: str) -> Any:
        if self.collection is None:
            raise AssertionError("collection does not exist")
        return self.collection

    async def create_collection(self, **kwargs: Any) -> bool:
        self.create_calls.append(kwargs)
        self.collection = make_collection(
            vectors=kwargs["vectors_config"],
            sparse_vectors=kwargs["sparse_vectors_config"] or {},
        )
        return True

    async def delete_collection(self, collection_name: str) -> bool:
        self.delete_calls.append(collection_name)
        self.collection = None
        return True

    async def create_payload_index(self, **kwargs: Any) -> object:
        self.payload_index_calls.append(kwargs)
        if self.collection is None:
            raise AssertionError("collection does not exist")
        self.collection.payload_schema[kwargs["field_name"]] = kwargs["field_schema"]
        return object()

    async def upsert(self, **kwargs: Any) -> None:
        self.upsert_calls += 1
        raise AssertionError("collection setup must not upsert points")


def make_collection(
    *,
    dense_name: str = "dense",
    dimension: int = 1024,
    distance: str = "Cosine",
    sparse_names: tuple[str, ...] = (),
    payload_fields: set[str] | None = None,
    vectors: dict[str, Any] | None = None,
    sparse_vectors: dict[str, Any] | None = None,
) -> Any:
    """Build Qdrant-shaped collection metadata for fake-client tests."""
    dense_vectors = vectors or {
        dense_name: SimpleNamespace(
            size=dimension,
            distance=FakeEnumValue(distance),
        )
    }
    configured_sparse = sparse_vectors or {name: FakeSparseVectorParams() for name in sparse_names}
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=dense_vectors,
                sparse_vectors=configured_sparse,
            )
        ),
        payload_schema={field: object() for field in payload_fields or set()},
    )


@pytest.fixture(autouse=True)
def fake_qdrant_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests independent of the optional qdrant-client package."""
    monkeypatch.setattr(
        "src.indexing.qdrant_collection._load_qdrant_models",
        lambda: FakeQdrantModels,
    )


def test_missing_qdrant_dependency_has_clear_install_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client construction explains how to install the optional dependency."""

    def missing_import(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr("src.indexing.qdrant_collection.importlib.import_module", missing_import)

    with pytest.raises(QdrantCollectionError, match=r"uv sync --extra qdrant"):
        build_qdrant_client(url="http://localhost:6333", timeout_seconds=60)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"dense_dimension": 0}, "dense_dimension"),
        ({"dense_vector_name": " "}, "dense vector names"),
        (
            {
                "sparse_enabled": True,
                "sparse_vector_name": "dense",
            },
            "must differ",
        ),
    ],
)
def test_collection_plan_rejects_invalid_vector_schema(
    overrides: dict[str, Any],
    message: str,
) -> None:
    """Collection planning rejects invalid dimensions and vector names."""
    arguments: dict[str, Any] = {
        "collection_name": "vnlaw_chunks_bgem3_v1",
        "dense_vector_name": "dense",
        "dense_dimension": 1024,
    }
    arguments.update(overrides)

    with pytest.raises(QdrantCollectionError, match=message):
        build_collection_plan(**arguments)


def test_payload_index_specs_are_deterministic() -> None:
    """Legal filter indexes remain ordered and exclude long text fields."""
    first = build_payload_index_specs()
    second = build_payload_index_specs()

    assert first == second
    assert [(spec.field_name, spec.field_schema) for spec in first] == [
        ("law_id", "keyword"),
        ("chunk_kind", "keyword"),
        ("level", "keyword"),
        ("metadata.is_empty_or_repealed", "bool"),
        ("metadata.is_source_unit_repealed", "bool"),
        ("source_domain", "keyword"),
        ("article_number", "keyword"),
    ]
    assert {"text", "parent_text", "citation", "hierarchy_path"}.isdisjoint(
        spec.field_name for spec in first
    )


@pytest.mark.asyncio
async def test_missing_collection_is_created_without_upserts() -> None:
    """Missing collection creation uses the measured dimension and no points."""
    client = FakeQdrantClient()

    result = await ensure_collection(
        client,
        collection_name="vnlaw_chunks_bgem3_v1",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert result.status == "created"
    assert result.created is True
    assert result.dense_dimension == 1024
    assert result.sparse_enabled is False
    assert len(client.create_calls) == 1
    assert client.create_calls[0]["vectors_config"]["dense"].size == 1024
    assert client.create_calls[0]["sparse_vectors_config"] is None
    assert client.delete_calls == []
    assert client.upsert_calls == 0


@pytest.mark.asyncio
async def test_existing_matching_collection_returns_already_exists() -> None:
    """Matching vector schema is retained and existing payload indexes are skipped."""
    payload_fields = {spec.field_name for spec in build_payload_index_specs()}
    client = FakeQdrantClient(make_collection(payload_fields=payload_fields))

    result = await ensure_collection(
        client,
        collection_name="vnlaw_chunks_bgem3_v1",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert result.status == "already_exists"
    assert result.already_exists is True
    assert result.payload_indexes_created == []
    assert client.create_calls == []
    assert client.delete_calls == []
    assert client.payload_index_calls == []
    assert client.upsert_calls == 0


@pytest.mark.asyncio
async def test_existing_collection_adds_only_missing_payload_indexes() -> None:
    """Matching vector schema receives only absent legal payload indexes."""
    client = FakeQdrantClient(make_collection(payload_fields={"law_id"}))

    result = await ensure_collection(
        client,
        collection_name="vnlaw_chunks_bgem3_v1",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert result.status == "already_exists"
    assert "law_id" not in result.payload_indexes_created
    assert result.payload_indexes_created == [
        "chunk_kind",
        "level",
        "metadata.is_empty_or_repealed",
        "metadata.is_source_unit_repealed",
        "source_domain",
        "article_number",
    ]


@pytest.mark.asyncio
async def test_mismatched_collection_fails_without_recreate() -> None:
    """A schema mismatch cannot delete a collection by default."""
    client = FakeQdrantClient(make_collection(dimension=768))

    with pytest.raises(QdrantCollectionError, match="pass recreate=True explicitly"):
        await ensure_collection(
            client,
            collection_name="vnlaw_chunks_bgem3_v1",
            dense_vector_name="dense",
            dense_dimension=1024,
        )

    assert client.delete_calls == []
    assert client.create_calls == []
    assert client.upsert_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "collection",
    [
        make_collection(
            vectors={
                "dense": SimpleNamespace(
                    size=1024,
                    distance=FakeEnumValue("Cosine"),
                ),
                "legacy": SimpleNamespace(
                    size=1024,
                    distance=FakeEnumValue("Cosine"),
                ),
            }
        ),
        make_collection(payload_fields={"law_id"}),
    ],
)
async def test_non_matching_collection_details_require_recreate(collection: Any) -> None:
    """Extra vectors and incompatible payload indexes are schema mismatches."""
    if "law_id" in collection.payload_schema:
        collection.payload_schema["law_id"] = SimpleNamespace(data_type=FakeEnumValue("integer"))
    client = FakeQdrantClient(collection)

    with pytest.raises(QdrantCollectionError, match="does not match requested schema"):
        await ensure_collection(
            client,
            collection_name="vnlaw_chunks_bgem3_v1",
            dense_vector_name="dense",
            dense_dimension=1024,
        )

    assert client.delete_calls == []


@pytest.mark.asyncio
async def test_mismatched_collection_recreates_only_when_explicit() -> None:
    """Explicit recreation deletes and rebuilds a mismatched schema."""
    client = FakeQdrantClient(make_collection(distance="Dot"))

    result = await ensure_collection(
        client,
        collection_name="vnlaw_chunks_bgem3_v1",
        dense_vector_name="dense",
        dense_dimension=1024,
        recreate=True,
    )

    assert result.status == "recreated"
    assert result.recreated is True
    assert client.delete_calls == ["vnlaw_chunks_bgem3_v1"]
    assert len(client.create_calls) == 1
    assert client.upsert_calls == 0


@pytest.mark.asyncio
async def test_sparse_collection_uses_distinct_optional_vector() -> None:
    """Sparse setup remains opt-in and creates a distinct named vector."""
    client = FakeQdrantClient()

    result = await ensure_collection(
        client,
        collection_name="vnlaw_chunks_bgem3_v1",
        dense_vector_name="dense",
        dense_dimension=1024,
        sparse_enabled=True,
        sparse_vector_name="sparse",
    )

    assert result.sparse_enabled is True
    assert result.sparse_vector_name == "sparse"
    assert set(client.create_calls[0]["sparse_vectors_config"]) == {"sparse"}


@pytest.mark.asyncio
async def test_dry_run_cli_does_not_build_client(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run validates and prints the plan without connecting or mutating."""

    def unexpected_client(**kwargs: Any) -> Any:
        raise AssertionError("dry-run must not build a Qdrant client")

    monkeypatch.setattr(setup_qdrant_collection, "build_qdrant_client", unexpected_client)

    result = await setup_qdrant_collection.run_setup(
        [
            "--config",
            "configs/indexing/embedding_indexing.yml",
            "--dense-dimension",
            "1024",
            "--dry-run",
        ]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert '"dense_dimension": 1024' in output
    assert '"recreate": false' in output


def test_recreate_defaults_to_false() -> None:
    """Both the public plan and setup API remain non-destructive by default."""
    plan = build_collection_plan(
        collection_name="vnlaw_chunks_bgem3_v1",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert plan.recreate is False
    assert inspect.signature(ensure_collection).parameters["recreate"].default is False
