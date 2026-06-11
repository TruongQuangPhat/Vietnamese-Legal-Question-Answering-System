"""Unit tests for read-only Phase 8 index validation."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import validate_qdrant_index
from scripts.validate_qdrant_index import validate_cli_arguments
from src.indexing.embedding_model import BgeM3EmbeddingModel
from src.indexing.index_validation import (
    DEFAULT_REQUIRED_PAYLOAD_FIELDS,
    run_retrieval_sanity_checks,
    validate_collection_schema,
    validate_index,
    validate_payload_filters,
    validate_sampled_points,
)
from src.indexing.indexing_models import PayloadFilterCheck, RetrievalSanityQuery
from src.indexing.qdrant_collection import build_payload_index_specs


class FakeEnum:
    """Enum-shaped value used by fake Qdrant metadata."""

    def __init__(self, value: str) -> None:
        self.value = value


class FakeMatchValue:
    """Qdrant-shaped exact match."""

    def __init__(self, *, value: Any) -> None:
        self.value = value


class FakeFieldCondition:
    """Qdrant-shaped payload field condition."""

    def __init__(self, *, key: str, match: FakeMatchValue) -> None:
        self.key = key
        self.match = match


class FakeFilter:
    """Qdrant-shaped conjunction filter."""

    def __init__(self, *, must: list[FakeFieldCondition]) -> None:
        self.must = must


class FakeQdrantModels:
    """Subset of Qdrant models needed to build read-only filters."""

    Filter = FakeFilter
    FieldCondition = FakeFieldCondition
    MatchValue = FakeMatchValue


class FakeEmbeddingModel:
    """Query embedder fake with configurable output dimension."""

    def __init__(self, *, dimension: int = 1024) -> None:
        self.dimension = dimension
        self.calls: list[str] = []

    def embed_query(self, query_text: str, *, batch_size: int = 1) -> list[float]:
        self.calls.append(query_text)
        return [1.0 / math.sqrt(self.dimension)] * self.dimension


class FakeEncoder:
    """BGE-M3 encoder fake used to validate the query-only wrapper path."""

    def encode(self, sentences: list[str], **kwargs: Any) -> dict[str, list[list[float]]]:
        return {"dense_vecs": [[3.0, 4.0] for _ in sentences]}


class FakeQdrantClient:
    """Read-only Qdrant fake with mutation traps."""

    def __init__(
        self,
        *,
        collection: Any | None = None,
        points: list[Any] | None = None,
        query_points: list[Any] | None = None,
    ) -> None:
        self.collection = collection or make_collection()
        self.points = points or [make_point()]
        self.query_results = query_points or self.points
        self.filters_seen: list[FakeFilter] = []
        self.query_calls: list[dict[str, Any]] = []
        self.mutation_calls: list[str] = []

    async def get_collection(self, collection_name: str) -> Any:
        return self.collection

    async def scroll(self, **kwargs: Any) -> tuple[list[Any], None]:
        records = self.points
        query_filter = kwargs.get("scroll_filter")
        if query_filter is not None:
            self.filters_seen.append(query_filter)
            records = [point for point in records if _matches(point.payload, query_filter.must[0])]
        return records[: kwargs.get("limit", 10)], None

    async def count(self, **kwargs: Any) -> Any:
        query_filter = kwargs["count_filter"]
        self.filters_seen.append(query_filter)
        count = sum(_matches(point.payload, query_filter.must[0]) for point in self.points)
        return SimpleNamespace(count=count)

    async def query_points(self, **kwargs: Any) -> Any:
        self.query_calls.append(kwargs)
        return SimpleNamespace(points=self.query_results[: kwargs["limit"]])

    async def close(self) -> None:
        """Mirror the real async client close method."""

    async def upsert(self, **kwargs: Any) -> None:
        self.mutation_calls.append("upsert")
        raise AssertionError("index validation must not upsert")

    async def delete(self, **kwargs: Any) -> None:
        self.mutation_calls.append("delete")
        raise AssertionError("index validation must not delete")

    async def delete_collection(self, **kwargs: Any) -> None:
        self.mutation_calls.append("delete_collection")
        raise AssertionError("index validation must not recreate")


def make_collection(
    *,
    dense_name: str = "dense",
    dimension: int = 1024,
    distance: str = "Cosine",
    status: str = "green",
    points_count: int = 10,
    indexed_vectors_count: int = 0,
    payload_fields: set[str] | None = None,
) -> Any:
    """Build Qdrant-shaped collection metadata."""
    fields = payload_fields
    if fields is None:
        fields = {spec.field_name for spec in build_payload_index_specs()}
    return SimpleNamespace(
        status=FakeEnum(status),
        points_count=points_count,
        indexed_vectors_count=indexed_vectors_count,
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={
                    dense_name: SimpleNamespace(
                        size=dimension,
                        distance=FakeEnum(distance),
                    )
                }
            )
        ),
        payload_schema={field: object() for field in fields},
    )


def make_payload(**overrides: Any) -> dict[str, Any]:
    """Build a complete traceability payload with nullable temporal fields."""
    payload: dict[str, Any] = {
        "schema_version": "0.1.0",
        "chunk_id": "chunk-1",
        "law_id": "BLDS_2015",
        "law_name": "Bộ luật Dân sự 2015",
        "level": "clause",
        "chunk_kind": "clause_level",
        "citation": "Khoản 1 Điều 1 Bộ luật Dân sự 2015",
        "hierarchy_path": "Bộ luật Dân sự 2015 / Điều 1 / Khoản 1",
        "source_node_id": "source-1",
        "text": "Phạm vi điều chỉnh của Bộ luật Dân sự.",
        "parent_text": "Điều 1. Phạm vi điều chỉnh",
        "text_hash": "text-hash",
        "parent_text_hash": "parent-hash",
        "source_url": "https://thuvienphapluat.vn/example",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "source_file": "data/interim/BLDS_2015/hierarchy.json",
        "metadata": {
            "is_empty_or_repealed": False,
            "is_source_unit_repealed": False,
        },
        "warnings": [],
        "embedding_model": "BAAI/bge-m3",
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
    vector: list[float] | None = None,
    score: float = 0.95,
) -> Any:
    """Build a Qdrant-shaped stored or scored point."""
    dense = vector if vector is not None else [1.0] * 1024
    return SimpleNamespace(
        id=point_id,
        payload=payload or make_payload(),
        vector={"dense": dense},
        score=score,
    )


def _matches(payload: dict[str, Any], condition: FakeFieldCondition) -> bool:
    value: Any = payload
    for part in condition.key.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return value == condition.match.value


@pytest.fixture(autouse=True)
def fake_qdrant_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent of the optional qdrant-client dependency."""
    monkeypatch.setattr(
        "src.indexing.index_validation._load_qdrant_models",
        lambda: FakeQdrantModels,
    )


@pytest.mark.asyncio
async def test_valid_collection_schema_passes_with_zero_indexed_vectors() -> None:
    """Tiny collections pass even when Qdrant has not built a vector index."""
    result = await validate_collection_schema(
        FakeQdrantClient(),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
        expected_min_points=10,
    )

    assert result.status == "pass"
    assert result.points_count == 10
    assert result.indexed_vectors_count == 0
    assert any(issue.code == "indexed_vectors_count_zero" for issue in result.issues)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("collection", "issue_code"),
    [
        (make_collection(dense_name="other"), "dense_vector_missing"),
        (make_collection(dimension=768), "dense_dimension_mismatch"),
        (make_collection(distance="Dot"), "dense_distance_mismatch"),
        (make_collection(payload_fields={"law_id"}), "payload_index_missing"),
    ],
)
async def test_collection_schema_mismatches_fail(
    collection: Any,
    issue_code: str,
) -> None:
    """Missing or incompatible schema elements are hard validation failures."""
    result = await validate_collection_schema(
        FakeQdrantClient(collection=collection),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert result.status == "failed"
    assert any(issue.code == issue_code for issue in result.issues)


@pytest.mark.asyncio
async def test_complete_payload_and_vector_pass() -> None:
    """Complete legal payloads and finite 1024-dimensional vectors pass."""
    result = await validate_sampled_points(
        FakeQdrantClient(),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert result.status == "pass"
    assert result.payload_status == "pass"
    assert result.vector_status == "pass"
    assert result.points[0].missing_payload_fields == []
    assert result.points[0].vector_dimension == 1024
    assert result.points[0].vector_finite is True
    assert set(DEFAULT_REQUIRED_PAYLOAD_FIELDS).issubset(make_payload())


@pytest.mark.asyncio
@pytest.mark.parametrize("field_name", ["chunk_id", "text", "parent_text"])
async def test_missing_required_payload_field_fails(field_name: str) -> None:
    """Missing legal traceability fields fail sampled payload validation."""
    payload = make_payload()
    payload.pop(field_name)

    result = await validate_sampled_points(
        FakeQdrantClient(points=[make_point(payload=payload)]),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert result.payload_status == "failed"
    assert field_name in result.points[0].missing_payload_fields


@pytest.mark.asyncio
async def test_nullable_temporal_fields_and_empty_domain_tags_pass() -> None:
    """Unknown temporal metadata remains null and domain tags may be empty."""
    result = await validate_sampled_points(
        FakeQdrantClient(points=[make_point(payload=make_payload())]),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
        check_vectors=False,
    )

    assert result.payload_status == "pass"
    assert result.vector_status == "not_run"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vector",
    [
        [1.0] * 3,
        [float("nan")] + [1.0] * 1023,
        [float("inf")] + [1.0] * 1023,
    ],
)
async def test_invalid_dense_vectors_fail(vector: list[float]) -> None:
    """Wrong dimensions and non-finite values fail vector validation."""
    result = await validate_sampled_points(
        FakeQdrantClient(points=[make_point(vector=vector)]),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
    )

    assert result.vector_status == "failed"


@pytest.mark.asyncio
async def test_payload_filters_include_nested_bool_and_return_results() -> None:
    """Exact filters support nested metadata booleans and sample point IDs."""
    client = FakeQdrantClient()
    checks = [
        PayloadFilterCheck(name="law", field_name="law_id", match_value="BLDS_2015"),
        PayloadFilterCheck(
            name="not_empty",
            field_name="metadata.is_empty_or_repealed",
            match_value=False,
        ),
    ]

    result = await validate_payload_filters(
        client,
        collection_name="dev",
        filters=checks,
    )

    assert result.status == "pass"
    assert all(check.returned_count == 1 for check in result.checks)
    assert result.checks[0].sample_point_ids == ["point-1"]
    assert any(
        condition.key == "metadata.is_empty_or_repealed"
        for query_filter in client.filters_seen
        for condition in query_filter.must
    )


@pytest.mark.asyncio
async def test_payload_filter_without_results_warns() -> None:
    """A valid filter with no dev-collection match is a warning, not mutation."""
    result = await validate_payload_filters(
        FakeQdrantClient(),
        collection_name="dev",
        filters=[PayloadFilterCheck(name="missing", field_name="law_id", match_value="OTHER")],
    )

    assert result.status == "warning"
    assert result.checks[0].returned_count == 0


@pytest.mark.asyncio
async def test_retrieval_sanity_summarizes_results_without_vectors() -> None:
    """Dense sanity search records legal summaries and excludes vector values."""
    model = FakeEmbeddingModel()
    client = FakeQdrantClient()

    result = await run_retrieval_sanity_checks(
        client,
        model,
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
        queries=[
            RetrievalSanityQuery(
                query_text="Phạm vi điều chỉnh là gì?",
                expected_hint_terms=["Điều 1", "Phạm vi điều chỉnh"],
            )
        ],
        top_k=3,
    )

    assert result.status == "pass"
    assert model.calls == ["Phạm vi điều chỉnh là gì?"]
    assert client.query_calls[0]["using"] == "dense"
    assert client.query_calls[0]["with_vectors"] is False
    assert result.query_results[0].query_vector_dimension == 1024
    assert "vector" not in result.query_results[0].results[0].model_dump()


def test_bge_wrapper_embeds_query_without_chunk_contract() -> None:
    """The real wrapper exposes a normalized query-only embedding path."""
    model = BgeM3EmbeddingModel(
        model_name="BAAI/bge-m3",
        device="cpu",
        encoder=FakeEncoder(),
    )

    vector = model.embed_query("Phạm vi điều chỉnh là gì?")

    assert vector == pytest.approx([0.6, 0.8])


@pytest.mark.asyncio
async def test_retrieval_dimension_mismatch_fails_without_search() -> None:
    """Invalid query-vector dimensions fail before Qdrant search."""
    client = FakeQdrantClient()

    result = await run_retrieval_sanity_checks(
        client,
        FakeEmbeddingModel(dimension=3),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
        queries=[RetrievalSanityQuery(query_text="test")],
    )

    assert result.status == "failed"
    assert client.query_calls == []


@pytest.mark.asyncio
async def test_missing_expected_hint_is_warning_not_brittle_failure() -> None:
    """Unexpected ranking content warns without asserting an exact top result."""
    result = await run_retrieval_sanity_checks(
        FakeQdrantClient(),
        FakeEmbeddingModel(),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
        queries=[
            RetrievalSanityQuery(
                query_text="test",
                expected_hint_terms=["không tồn tại"],
            )
        ],
    )

    assert result.status == "warning"
    assert result.query_results[0].expected_hints_matched is False


@pytest.mark.asyncio
async def test_expected_hint_matching_ignores_citation_punctuation() -> None:
    """Citation commas do not turn a correct top result into a warning."""
    payload = make_payload(
        citation="Bộ luật Dân sự 2015, Khoản 2, Điều 2",
        text="Quyền dân sự chỉ có thể bị hạn chế theo quy định của luật.",
    )

    result = await run_retrieval_sanity_checks(
        FakeQdrantClient(query_points=[make_point(payload=payload)]),
        FakeEmbeddingModel(),
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
        queries=[
            RetrievalSanityQuery(
                query_text="Quyền dân sự bị hạn chế khi nào?",
                expected_hint_terms=["Khoản 2 Điều 2", "hạn chế"],
            )
        ],
    )

    assert result.status == "pass"
    assert result.query_results[0].expected_hints_matched is True


@pytest.mark.asyncio
async def test_aggregate_skip_retrieval_does_not_embed_or_mutate() -> None:
    """Skipping retrieval performs only collection, scroll, and count reads."""
    client = FakeQdrantClient()

    report = await validate_index(
        client,
        collection_name="dev",
        dense_vector_name="dense",
        dense_dimension=1024,
        expected_distance="Cosine",
        expected_min_points=1,
        sample_limit=1,
        filters=[PayloadFilterCheck(name="law", field_name="law_id", match_value="BLDS_2015")],
        queries=[],
        top_k=3,
        check_vectors=True,
        embedding_model=None,
    )

    assert report.status == "success"
    assert report.retrieval_sanity_status == "not_run"
    assert client.query_calls == []
    assert client.mutation_calls == []


def test_cli_rejects_protected_output() -> None:
    """Validation reports cannot be written under protected paths."""
    with pytest.raises(ValueError, match="protected"):
        validate_cli_arguments(
            output_path=Path("artifacts/reports/index_validation.json"),
            dense_dimension=1024,
            expected_min_points=1,
            sample_limit=10,
            top_k=3,
        )


@pytest.mark.asyncio
async def test_cli_skip_retrieval_does_not_construct_embedding_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI skip flag avoids BGE-M3 construction and all mutations."""
    client = FakeQdrantClient()

    def unexpected_model(**kwargs: Any) -> None:
        raise AssertionError("embedding model must not be constructed")

    monkeypatch.setattr(validate_qdrant_index, "build_qdrant_client", lambda **kwargs: client)
    monkeypatch.setattr(validate_qdrant_index, "BgeM3EmbeddingModel", unexpected_model)
    output = tmp_path / "report.json"

    exit_code = await validate_qdrant_index.run_validation(
        [
            "--config",
            "configs/indexing/embedding_indexing.yml",
            "--collection-name",
            "dev",
            "--expected-min-points",
            "1",
            "--sample-limit",
            "1",
            "--skip-retrieval-sanity",
            "--output",
            str(output),
            "--quiet",
        ]
    )

    assert exit_code == 0
    assert output.is_file()
    assert client.query_calls == []
    assert client.mutation_calls == []
