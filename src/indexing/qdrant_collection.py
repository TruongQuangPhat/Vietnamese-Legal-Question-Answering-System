"""Safe Qdrant collection schema setup for Phase 8 Slice 8E.

This module validates or creates collection metadata only. It does not embed
text, build point payloads, upsert vectors, read the legal corpus, or perform
retrieval.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import ValidationError

from src.indexing.indexing_models import (
    CollectionSchemaPlan,
    CollectionSetupResult,
    PayloadIndexSpec,
)


class QdrantCollectionError(RuntimeError):
    """Raised when Qdrant collection planning or setup cannot complete safely."""


class QdrantCollectionClient(Protocol):
    """Minimal async Qdrant client surface used by collection setup."""

    async def collection_exists(self, collection_name: str) -> bool:
        """Return whether a collection exists."""
        ...

    async def get_collection(self, collection_name: str) -> Any:
        """Return collection metadata."""
        ...

    async def create_collection(self, **kwargs: Any) -> bool:
        """Create a collection from vector configuration."""
        ...

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete an existing collection."""
        ...

    async def create_payload_index(self, **kwargs: Any) -> Any:
        """Create one payload field index."""
        ...


def build_qdrant_client(*, url: str, timeout_seconds: float) -> QdrantCollectionClient:
    """Build an async Qdrant client without connecting to the server.

    Args:
        url: Qdrant HTTP endpoint.
        timeout_seconds: Positive request timeout.

    Returns:
        An ``AsyncQdrantClient`` compatible with the setup protocol.

    Raises:
        QdrantCollectionError: If arguments are invalid or the optional
            ``qdrant-client`` dependency is unavailable.
    """
    if not url.strip():
        raise QdrantCollectionError("Qdrant URL must not be blank")
    if timeout_seconds <= 0:
        raise QdrantCollectionError("Qdrant timeout must be positive")

    try:
        module = importlib.import_module("qdrant_client")
    except ImportError as exc:
        raise QdrantCollectionError(
            "qdrant-client is required for collection setup; "
            "install it with `uv sync --extra qdrant`"
        ) from exc
    return module.AsyncQdrantClient(url=url, timeout=timeout_seconds)


def build_payload_index_specs() -> list[PayloadIndexSpec]:
    """Return deterministic payload indexes for common legal metadata filters."""
    return [
        PayloadIndexSpec(field_name="law_id", field_schema="keyword"),
        PayloadIndexSpec(field_name="chunk_kind", field_schema="keyword"),
        PayloadIndexSpec(field_name="level", field_schema="keyword"),
        PayloadIndexSpec(
            field_name="metadata.is_empty_or_repealed",
            field_schema="bool",
        ),
        PayloadIndexSpec(
            field_name="metadata.is_source_unit_repealed",
            field_schema="bool",
        ),
        PayloadIndexSpec(field_name="source_domain", field_schema="keyword"),
        PayloadIndexSpec(field_name="article_number", field_schema="keyword"),
    ]


def build_collection_plan(
    *,
    collection_name: str,
    dense_vector_name: str,
    dense_dimension: int,
    distance: str = "Cosine",
    sparse_enabled: bool = False,
    sparse_vector_name: str = "sparse",
    recreate: bool = False,
    payload_indexes: Sequence[PayloadIndexSpec] | None = None,
) -> CollectionSchemaPlan:
    """Build and validate a non-executing collection schema plan.

    Args:
        collection_name: Qdrant collection name.
        dense_vector_name: Named dense vector key.
        dense_dimension: Positive dimension measured from model output.
        distance: Qdrant dense-vector distance metric.
        sparse_enabled: Whether to include an optional named sparse vector.
        sparse_vector_name: Sparse vector key when enabled.
        recreate: Whether a mismatched existing collection may be replaced.
        payload_indexes: Optional explicit payload index definitions.

    Returns:
        A validated collection schema plan.

    Raises:
        QdrantCollectionError: If any schema value is invalid.
    """
    try:
        return CollectionSchemaPlan(
            collection_name=collection_name,
            dense_vector_name=dense_vector_name,
            dense_dimension=dense_dimension,
            distance=distance,
            sparse_enabled=sparse_enabled,
            sparse_vector_name=sparse_vector_name if sparse_enabled else None,
            recreate=recreate,
            payload_indexes=list(payload_indexes or build_payload_index_specs()),
        )
    except ValidationError as exc:
        raise QdrantCollectionError(f"invalid Qdrant collection plan: {exc}") from exc


async def ensure_collection(
    client: QdrantCollectionClient,
    *,
    collection_name: str,
    dense_vector_name: str,
    dense_dimension: int,
    distance: str = "Cosine",
    sparse_enabled: bool = False,
    sparse_vector_name: str = "sparse",
    recreate: bool = False,
    payload_indexes: Sequence[PayloadIndexSpec] | None = None,
) -> CollectionSetupResult:
    """Create or safely validate a Qdrant collection schema.

    Existing matching collections are retained. Existing mismatched
    collections fail unless ``recreate`` is explicitly true. This function
    creates collection metadata and payload indexes only; it never upserts
    points.

    Args:
        client: Injected async Qdrant-compatible client.
        collection_name: Qdrant collection name.
        dense_vector_name: Named dense vector key.
        dense_dimension: Positive dimension measured from model output.
        distance: Qdrant dense-vector distance metric.
        sparse_enabled: Whether to configure an optional sparse vector.
        sparse_vector_name: Sparse vector key when enabled.
        recreate: Explicit permission to replace a mismatched collection.
        payload_indexes: Optional explicit payload index definitions.

    Returns:
        Typed collection setup result.

    Raises:
        QdrantCollectionError: If validation, server communication, or safe
            schema matching fails.
    """
    plan = build_collection_plan(
        collection_name=collection_name,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
        distance=distance,
        sparse_enabled=sparse_enabled,
        sparse_vector_name=sparse_vector_name,
        recreate=recreate,
        payload_indexes=payload_indexes,
    )

    try:
        exists = await client.collection_exists(plan.collection_name)
        recreated = False
        already_exists = False
        existing_payload_fields: set[str] = set()

        if exists:
            collection = await client.get_collection(plan.collection_name)
            mismatches = _find_schema_mismatches(collection, plan)
            if mismatches and not plan.recreate:
                mismatch_text = "; ".join(mismatches)
                raise QdrantCollectionError(
                    f"existing collection {plan.collection_name!r} does not match "
                    f"requested schema: {mismatch_text}; pass recreate=True explicitly "
                    "to replace it"
                )
            if mismatches:
                deleted = await client.delete_collection(plan.collection_name)
                if not deleted:
                    raise QdrantCollectionError(
                        f"Qdrant did not confirm deletion of {plan.collection_name!r}"
                    )
                await _create_collection(client, plan)
                recreated = True
            else:
                already_exists = True
                existing_payload_fields = _extract_payload_fields(collection)
        else:
            await _create_collection(client, plan)

        payload_indexes_created = await _create_missing_payload_indexes(
            client,
            plan,
            existing_payload_fields=existing_payload_fields,
        )
    except QdrantCollectionError:
        raise
    except Exception as exc:
        raise QdrantCollectionError(
            f"Qdrant collection setup failed for {plan.collection_name!r}: {exc}"
        ) from exc

    status = "recreated" if recreated else "already_exists" if already_exists else "created"
    return CollectionSetupResult(
        collection_name=plan.collection_name,
        created=not recreated and not already_exists,
        recreated=recreated,
        already_exists=already_exists,
        dense_vector_name=plan.dense_vector_name,
        dense_dimension=plan.dense_dimension,
        distance=plan.distance,
        sparse_enabled=plan.sparse_enabled,
        sparse_vector_name=plan.sparse_vector_name,
        payload_indexes_requested=plan.payload_indexes,
        payload_indexes_created=payload_indexes_created,
        status=status,
    )


async def _create_collection(
    client: QdrantCollectionClient,
    plan: CollectionSchemaPlan,
) -> None:
    qdrant_models = _load_qdrant_models()
    vectors_config = {
        plan.dense_vector_name: qdrant_models.VectorParams(
            size=plan.dense_dimension,
            distance=qdrant_models.Distance(plan.distance),
        )
    }
    sparse_vectors_config = (
        {plan.sparse_vector_name: qdrant_models.SparseVectorParams()}
        if plan.sparse_enabled and plan.sparse_vector_name is not None
        else None
    )
    created = await client.create_collection(
        collection_name=plan.collection_name,
        vectors_config=vectors_config,
        sparse_vectors_config=sparse_vectors_config,
    )
    if not created:
        raise QdrantCollectionError(f"Qdrant did not confirm creation of {plan.collection_name!r}")


async def _create_missing_payload_indexes(
    client: QdrantCollectionClient,
    plan: CollectionSchemaPlan,
    *,
    existing_payload_fields: set[str],
) -> list[str]:
    missing = [
        spec for spec in plan.payload_indexes if spec.field_name not in existing_payload_fields
    ]
    if not missing:
        return []

    qdrant_models = _load_qdrant_models()
    created: list[str] = []
    for spec in missing:
        await client.create_payload_index(
            collection_name=plan.collection_name,
            field_name=spec.field_name,
            field_schema=qdrant_models.PayloadSchemaType(spec.field_schema),
            wait=True,
        )
        created.append(spec.field_name)
    return created


def _load_qdrant_models() -> Any:
    try:
        module = importlib.import_module("qdrant_client")
    except ImportError as exc:
        raise QdrantCollectionError(
            "qdrant-client is required for collection setup; "
            "install it with `uv sync --extra qdrant`"
        ) from exc
    return module.models


def _find_schema_mismatches(
    collection: Any,
    plan: CollectionSchemaPlan,
) -> list[str]:
    params = collection.config.params
    vectors = params.vectors
    sparse_vectors = params.sparse_vectors or {}
    mismatches: list[str] = []

    if not isinstance(vectors, Mapping) or plan.dense_vector_name not in vectors:
        mismatches.append(f"missing named dense vector {plan.dense_vector_name!r}")
    else:
        actual_dense_names = set(vectors)
        expected_dense_names = {plan.dense_vector_name}
        if actual_dense_names != expected_dense_names:
            mismatches.append(
                f"dense vector names are {sorted(actual_dense_names)!r}, "
                f"expected {sorted(expected_dense_names)!r}"
            )
        dense = vectors[plan.dense_vector_name]
        if dense.size != plan.dense_dimension:
            mismatches.append(f"dense dimension is {dense.size}, expected {plan.dense_dimension}")
        actual_distance = _enum_value(dense.distance)
        if actual_distance != plan.distance:
            mismatches.append(f"dense distance is {actual_distance!r}, expected {plan.distance!r}")

    actual_sparse_names = set(sparse_vectors)
    expected_sparse_names = (
        {plan.sparse_vector_name}
        if plan.sparse_enabled and plan.sparse_vector_name is not None
        else set()
    )
    if actual_sparse_names != expected_sparse_names:
        mismatches.append(
            f"sparse vector names are {sorted(actual_sparse_names)!r}, "
            f"expected {sorted(expected_sparse_names)!r}"
        )

    payload_schema = getattr(collection, "payload_schema", None) or {}
    for spec in plan.payload_indexes:
        existing = payload_schema.get(spec.field_name)
        if existing is None:
            continue
        existing_type = getattr(existing, "data_type", None)
        if existing_type is not None and _enum_value(existing_type) != spec.field_schema:
            mismatches.append(
                f"payload index {spec.field_name!r} is {_enum_value(existing_type)!r}, "
                f"expected {spec.field_schema!r}"
            )
    return mismatches


def _extract_payload_fields(collection: Any) -> set[str]:
    payload_schema = getattr(collection, "payload_schema", None) or {}
    return set(payload_schema)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))
