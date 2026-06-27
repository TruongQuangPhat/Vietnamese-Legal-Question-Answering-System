"""Deterministic vector payload mapping for embedding/indexing payload mapping.

This module maps validated legal chunks to typed payloads and deterministic
point identifiers. It does not generate vectors, import Qdrant, connect to a
database, or mutate source chunks.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.indexing.indexing_models import VectorPayload
from src.processing.legal_chunk_models import LegalChunk


def build_vector_payload(
    chunk: LegalChunk,
    *,
    embedding_model: str,
    embedding_revision: str | None,
    indexing_run_id: str,
    payload_schema_version: str = "0.1.0",
) -> VectorPayload:
    """Build a traceability-preserving payload from one validated legal chunk.

    Args:
        chunk: Canonical parent-child chunking legal chunk. The object and its nested fields
            are not modified.
        embedding_model: Model identifier associated with the future vector.
        embedding_revision: Optional pinned model revision.
        indexing_run_id: Identifier of the future indexing run.
        payload_schema_version: Payload contract version.

    Returns:
        Typed payload with legal text, hierarchy, source, hashes, metadata,
        warnings, and embedding/indexing provenance.

    Raises:
        ValueError: If required provenance values are blank.

    Legal assumptions:
        Temporal, status, and domain enrichment is not inferred from citation,
        law name, URL, or any other chunk field. Unknown values remain null or
        empty according to the embedding/indexing payload policy.
    """
    _require_non_blank(embedding_model, field_name="embedding_model")
    _require_non_blank(indexing_run_id, field_name="indexing_run_id")
    _require_non_blank(payload_schema_version, field_name="payload_schema_version")
    if embedding_revision is not None:
        _require_non_blank(embedding_revision, field_name="embedding_revision")

    return VectorPayload(
        schema_version=payload_schema_version,
        chunk_id=chunk.chunk_id,
        law_id=chunk.law_id,
        law_name=chunk.law_name,
        level=chunk.level,
        chunk_kind=chunk.chunk_kind,
        article_number=chunk.article_number,
        article_title=chunk.article_title,
        clause_number=chunk.clause_number,
        point_label=chunk.point_label,
        citation=chunk.citation,
        hierarchy_path=chunk.hierarchy_path,
        source_node_id=chunk.source_node_id,
        parent_article_node_id=chunk.parent_article_node_id,
        parent_chunk_id=chunk.parent_chunk_id,
        text=chunk.text,
        parent_text=chunk.parent_text,
        text_hash=chunk.text_hash,
        parent_text_hash=chunk.parent_text_hash,
        source_url=chunk.source_url,
        source_domain=chunk.source_domain,
        source_type=chunk.source_type,
        source_file=chunk.source_file,
        metadata=chunk.metadata.model_copy(deep=True),
        warnings=[warning.model_copy(deep=True) for warning in chunk.warnings],
        embedding_model=embedding_model,
        embedding_revision=embedding_revision,
        indexing_run_id=indexing_run_id,
        effective_date=None,
        expiry_date=None,
        status=None,
        domain_tags=[],
    )


def build_point_id(chunk_id: str, *, namespace: str) -> str:
    """Return a deterministic UUIDv5 string for a legal chunk.

    Args:
        chunk_id: Original deterministic legal chunk identifier.
        namespace: Stable project namespace from indexing configuration.

    Returns:
        UUIDv5 string suitable for a future Qdrant point identifier.

    Raises:
        ValueError: If ``chunk_id`` or ``namespace`` is blank.
    """
    _require_non_blank(chunk_id, field_name="chunk_id")
    _require_non_blank(namespace, field_name="namespace")
    namespace_uuid = uuid.uuid5(uuid.NAMESPACE_URL, namespace)
    return str(uuid.uuid5(namespace_uuid, chunk_id))


def vector_payload_to_qdrant_payload(payload: VectorPayload) -> dict[str, Any]:
    """Serialize a vector payload to a deterministic JSON-compatible mapping.

    Null temporal/status values are intentionally retained to implement
    ``store_null_do_not_infer``. Vector values are absent by construction.

    Args:
        payload: Typed payload to serialize.

    Returns:
        Plain dictionary with nested metadata and warnings serialized in JSON
        mode and all nullable enrichment fields preserved.
    """
    return payload.model_dump(mode="json", exclude_none=False)


def _require_non_blank(value: str, *, field_name: str) -> None:
    """Raise when a required builder argument is empty or whitespace-only."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
