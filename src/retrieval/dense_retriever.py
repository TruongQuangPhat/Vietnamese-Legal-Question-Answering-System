"""Read-only dense retrieval over the embedding/indexing Qdrant collection."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import ValidationError

from src.retrieval.filters import RetrievalFilterError, build_qdrant_filter
from src.retrieval.models import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DENSE_DIMENSION,
    DEFAULT_DENSE_VECTOR_NAME,
    DEFAULT_TOP_K,
    RetrievalFilters,
    RetrievalIssue,
    RetrievalIssueSeverity,
    RetrievalQuery,
    RetrievalResult,
    RetrievedChunk,
)
from src.retrieval.timing import emit_retrieval_timing, safe_exception_class

CRITICAL_PAYLOAD_FIELDS = ("chunk_id", "law_id", "citation", "text")


class DenseRetrieverError(RuntimeError):
    """Raised when dense retrieval cannot safely complete.

    Attributes:
        failure_stage: Sanitized machine-readable failure stage.
        warning_code: Sanitized API warning code suitable for client responses.
        cause_class: Sanitized root exception class, when known.
    """

    failure_stage = "dense_retriever_error"
    warning_code = "dense_retriever_error"

    def __init__(
        self,
        message: str,
        *,
        failure_stage: str | None = None,
        warning_code: str | None = None,
        cause_class: str | None = None,
    ) -> None:
        self.failure_stage = failure_stage or self.failure_stage
        self.warning_code = warning_code or self.warning_code
        self.cause_class = cause_class
        super().__init__(message)


class EmbeddingModelLoadTimeoutError(DenseRetrieverError, TimeoutError):
    """Raised when embedding model initialization exceeds its timeout."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            "embedding model load timed out",
            failure_stage="embedding_model_load_timeout",
            warning_code="embedding_model_load_timeout",
            cause_class="TimeoutError",
        )


class EmbeddingModelLoadError(DenseRetrieverError):
    """Raised when embedding model initialization fails before query encoding."""

    def __init__(self, *, cause_class: str) -> None:
        super().__init__(
            "embedding model load failed",
            failure_stage="embedding_model_load_error",
            warning_code="embedding_model_load_error",
            cause_class=cause_class,
        )


class QueryEmbeddingTimeoutError(DenseRetrieverError, TimeoutError):
    """Raised when query embedding exceeds its timeout."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            "query embedding timed out",
            failure_stage="query_embedding_timeout",
            warning_code="query_embedding_timeout",
            cause_class="TimeoutError",
        )


class QueryEmbeddingError(DenseRetrieverError):
    """Raised when query embedding fails after model loading."""

    def __init__(self, *, cause_class: str) -> None:
        super().__init__(
            "query embedding failed",
            failure_stage="query_embedding_error",
            warning_code="query_embedding_error",
            cause_class=cause_class,
        )


class QdrantRetrievalTimeoutError(DenseRetrieverError, TimeoutError):
    """Raised when the Qdrant search call exceeds its timeout."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            "Qdrant dense retrieval timed out",
            failure_stage="qdrant_retrieval_timeout",
            warning_code="qdrant_retrieval_timeout",
            cause_class="TimeoutError",
        )


class QdrantRetrievalError(DenseRetrieverError):
    """Raised when Qdrant search fails after the call has started."""

    def __init__(self, *, cause_class: str) -> None:
        super().__init__(
            "Qdrant dense retrieval failed",
            failure_stage="qdrant_retrieval_error",
            warning_code="qdrant_retrieval_error",
            cause_class=cause_class,
        )


class QueryEmbeddingModel(Protocol):
    """Query-only embedding dependency used by dense retrieval."""

    def embed_query(self, query_text: str, *, batch_size: int = 1) -> list[float]:
        """Embed one query into the same dense vector space as indexed chunks."""
        ...


class QdrantRetrievalClient(Protocol):
    """Minimal read-only Qdrant surface used by dense retrieval baseline retrieval."""

    async def query_points(self, **kwargs: Any) -> Any:
        """Run a named-vector dense search."""
        ...


class DenseRetriever:
    """Embed Vietnamese queries and run read-only dense search in Qdrant.

    Args:
        qdrant_client: Injected async Qdrant-compatible client.
        embedding_model: Injected query embedding model, usually the existing
            BGE-M3 wrapper from ``src.indexing.embedding_model``.
        collection_name: Default collection to query.
        dense_vector_name: Named dense vector configured in Qdrant.
        expected_vector_dim: Required query vector dimension.
        default_top_k: Default number of results.
        embedding_batch_size: Query embedding batch size.

    Retrieval assumptions:
        dense retrieval baseline uses dense search only over the already indexed ``text`` vector.
        It does not mutate Qdrant, generate answers, rerank, or perform
        time-aware legal validity filtering.
    """

    def __init__(
        self,
        *,
        qdrant_client: QdrantRetrievalClient,
        embedding_model: QueryEmbeddingModel,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        dense_vector_name: str = DEFAULT_DENSE_VECTOR_NAME,
        expected_vector_dim: int = DEFAULT_DENSE_DIMENSION,
        default_top_k: int = DEFAULT_TOP_K,
        embedding_batch_size: int = 1,
        query_embedding_timeout_seconds: float | None = None,
        qdrant_timeout_seconds: float | None = None,
    ) -> None:
        if not collection_name.strip():
            raise DenseRetrieverError("collection_name must not be blank")
        if not dense_vector_name.strip():
            raise DenseRetrieverError("dense_vector_name must not be blank")
        if expected_vector_dim <= 0:
            raise DenseRetrieverError("expected_vector_dim must be positive")
        if default_top_k <= 0:
            raise DenseRetrieverError("default_top_k must be positive")
        if embedding_batch_size <= 0:
            raise DenseRetrieverError("embedding_batch_size must be positive")
        if query_embedding_timeout_seconds is not None and query_embedding_timeout_seconds <= 0:
            raise DenseRetrieverError("query_embedding_timeout_seconds must be positive")
        if qdrant_timeout_seconds is not None and qdrant_timeout_seconds <= 0:
            raise DenseRetrieverError("qdrant_timeout_seconds must be positive")

        self._qdrant_client = qdrant_client
        self._embedding_model = embedding_model
        self.collection_name = collection_name
        self.dense_vector_name = dense_vector_name
        self.expected_vector_dim = expected_vector_dim
        self.default_top_k = default_top_k
        self.embedding_batch_size = embedding_batch_size
        self.query_embedding_timeout_seconds = query_embedding_timeout_seconds
        self.qdrant_timeout_seconds = qdrant_timeout_seconds

    async def retrieve(
        self,
        query: RetrievalQuery | str,
        *,
        top_k: int | None = None,
        collection_name: str | None = None,
        filters: RetrievalFilters | None = None,
    ) -> RetrievalResult:
        """Run one dense retrieval request and return typed legal evidence.

        Args:
            query: Query text or a prevalidated retrieval query.
            top_k: Optional top-k override for string queries.
            collection_name: Optional collection override for string queries.
            filters: Optional filters for string queries.

        Returns:
            Typed retrieval result with ranked payload-backed chunks.

        Raises:
            DenseRetrieverError: If embedding, vector validation, filter
                construction, Qdrant search, or result mapping fails.
        """
        retrieval_query = self._coerce_query(
            query,
            top_k=top_k,
            collection_name=collection_name,
            filters=filters,
        )
        started = time.perf_counter()
        emit_retrieval_timing(
            stage="dense_retriever_started",
            top_k=retrieval_query.top_k,
        )
        vector = await self._embed_query(retrieval_query.query)
        self._validate_query_vector(vector)

        try:
            query_filter = build_qdrant_filter(retrieval_query.filters)
        except RetrievalFilterError as exc:
            raise DenseRetrieverError(str(exc)) from exc

        search_kwargs: dict[str, Any] = {
            "collection_name": retrieval_query.collection_name,
            "query": vector,
            "using": self.dense_vector_name,
            "limit": retrieval_query.top_k,
            "with_payload": True,
            "with_vectors": False,
        }
        if query_filter is not None:
            search_kwargs["query_filter"] = query_filter

        try:
            qdrant_started = time.perf_counter()
            emit_retrieval_timing(
                stage="qdrant_retrieval_started",
                top_k=retrieval_query.top_k,
                timeout_seconds=self.qdrant_timeout_seconds,
            )
            qdrant_call = self._qdrant_client.query_points(**search_kwargs)
            if self.qdrant_timeout_seconds is None:
                response = await qdrant_call
            else:
                response = await asyncio.wait_for(
                    qdrant_call,
                    timeout=self.qdrant_timeout_seconds,
                )
        except TimeoutError as exc:
            emit_retrieval_timing(
                stage="qdrant_retrieval_timeout",
                stage_started_at=qdrant_started,
                exception_class="TimeoutError",
                timeout_seconds=self.qdrant_timeout_seconds,
                top_k=retrieval_query.top_k,
            )
            raise QdrantRetrievalTimeoutError(
                timeout_seconds=self.qdrant_timeout_seconds or 0.0
            ) from exc
        except Exception as exc:
            emit_retrieval_timing(
                stage="dense_retriever_failed",
                stage_started_at=qdrant_started,
                exception_class=safe_exception_class(exc),
                timeout_seconds=self.qdrant_timeout_seconds,
                top_k=retrieval_query.top_k,
            )
            raise QdrantRetrievalError(cause_class=safe_exception_class(exc)) from exc
        emit_retrieval_timing(
            stage="qdrant_retrieval_completed",
            stage_started_at=qdrant_started,
            top_k=retrieval_query.top_k,
        )

        points = getattr(response, "points", None)
        if points is None:
            raise DenseRetrieverError("Qdrant response does not expose points")
        if not isinstance(points, Sequence):
            raise DenseRetrieverError("Qdrant response points must be a sequence")

        result_issues: list[RetrievalIssue] = []
        chunks: list[RetrievedChunk] = []
        for rank, point in enumerate(points, start=1):
            chunk = _map_qdrant_point(point, rank=rank)
            chunks.append(chunk)
            result_issues.extend(chunk.issues)

        result = RetrievalResult(
            query=retrieval_query.query,
            collection_name=retrieval_query.collection_name,
            vector_name=self.dense_vector_name,
            top_k=retrieval_query.top_k,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            query_vector_dimension=len(vector),
            filters=retrieval_query.filters,
            results=chunks,
            issues=result_issues,
        )
        emit_retrieval_timing(
            stage="dense_retriever_completed",
            stage_started_at=started,
            top_k=retrieval_query.top_k,
        )
        return result

    def _coerce_query(
        self,
        query: RetrievalQuery | str,
        *,
        top_k: int | None,
        collection_name: str | None,
        filters: RetrievalFilters | None,
    ) -> RetrievalQuery:
        if isinstance(query, RetrievalQuery):
            if top_k is not None or collection_name is not None or filters is not None:
                raise DenseRetrieverError(
                    "top_k, collection_name, and filters overrides require a string query"
                )
            return query
        try:
            return RetrievalQuery(
                query=query,
                top_k=top_k or self.default_top_k,
                collection_name=collection_name or self.collection_name,
                filters=filters or RetrievalFilters(),
            )
        except ValidationError as exc:
            raise DenseRetrieverError(f"invalid retrieval query: {exc}") from exc

    async def _embed_query(self, query_text: str) -> list[float]:
        await self._load_embedding_model_if_supported()
        try:
            started = time.perf_counter()
            emit_retrieval_timing(
                stage="query_embedding_started",
                timeout_seconds=self.query_embedding_timeout_seconds,
            )
            embedding_call = asyncio.to_thread(
                self._embedding_model.embed_query,
                query_text,
                batch_size=self.embedding_batch_size,
            )
            if self.query_embedding_timeout_seconds is None:
                vector = await embedding_call
            else:
                vector = await asyncio.wait_for(
                    embedding_call,
                    timeout=self.query_embedding_timeout_seconds,
                )
        except TimeoutError as exc:
            emit_retrieval_timing(
                stage="query_embedding_timeout",
                stage_started_at=started,
                exception_class="TimeoutError",
                timeout_seconds=self.query_embedding_timeout_seconds,
            )
            raise QueryEmbeddingTimeoutError(
                timeout_seconds=self.query_embedding_timeout_seconds or 0.0
            ) from exc
        except Exception as exc:
            emit_retrieval_timing(
                stage="dense_retriever_failed",
                stage_started_at=started,
                exception_class=safe_exception_class(exc),
                timeout_seconds=self.query_embedding_timeout_seconds,
            )
            raise QueryEmbeddingError(cause_class=safe_exception_class(exc)) from exc
        emit_retrieval_timing(stage="query_embedding_completed", stage_started_at=started)
        return vector

    async def _load_embedding_model_if_supported(self) -> None:
        is_loaded = getattr(self._embedding_model, "is_loaded", None)
        ensure_loaded = getattr(self._embedding_model, "ensure_loaded", None)
        if ensure_loaded is None or not callable(ensure_loaded):
            return
        if isinstance(is_loaded, bool) and is_loaded:
            return
        started = time.perf_counter()
        emit_retrieval_timing(
            stage="embedding_model_load_started",
            timeout_seconds=self.query_embedding_timeout_seconds,
        )
        try:
            load_call = asyncio.to_thread(ensure_loaded)
            if self.query_embedding_timeout_seconds is None:
                await load_call
            else:
                await asyncio.wait_for(
                    load_call,
                    timeout=self.query_embedding_timeout_seconds,
                )
        except TimeoutError as exc:
            emit_retrieval_timing(
                stage="embedding_model_load_timeout",
                stage_started_at=started,
                exception_class="TimeoutError",
                timeout_seconds=self.query_embedding_timeout_seconds,
            )
            raise EmbeddingModelLoadTimeoutError(
                timeout_seconds=self.query_embedding_timeout_seconds or 0.0
            ) from exc
        except Exception as exc:
            emit_retrieval_timing(
                stage="dense_retriever_failed",
                stage_started_at=started,
                exception_class=safe_exception_class(exc),
                timeout_seconds=self.query_embedding_timeout_seconds,
            )
            raise EmbeddingModelLoadError(cause_class=safe_exception_class(exc)) from exc
        emit_retrieval_timing(stage="embedding_model_load_completed", stage_started_at=started)

    async def warmup_embedding(self) -> None:
        """Load the embedding model and run one fixed non-sensitive embedding."""
        await self._load_embedding_model_if_supported()
        vector = await self._embed_query("legal qa warmup")
        self._validate_query_vector(vector)

    def _validate_query_vector(self, vector: Sequence[Any]) -> None:
        if not vector:
            raise DenseRetrieverError("query vector must be non-empty")
        if len(vector) != self.expected_vector_dim:
            raise DenseRetrieverError(
                f"query vector dimension is {len(vector)}, expected {self.expected_vector_dim}"
            )
        if not all(isinstance(value, int | float) for value in vector):
            raise DenseRetrieverError("query vector values must be numeric")
        if not all(math.isfinite(float(value)) for value in vector):
            raise DenseRetrieverError("query vector values must be finite")


def _map_qdrant_point(point: Any, *, rank: int) -> RetrievedChunk:
    point_id = _optional_string(getattr(point, "id", None))
    score = _score_from_point(point, rank=rank)
    payload = getattr(point, "payload", None)
    issues: list[RetrievalIssue] = []

    if not isinstance(payload, Mapping):
        issues.append(
            _issue(
                code="payload_missing",
                message="Qdrant result did not include an object payload",
                rank=rank,
                details={"point_id": point_id},
            )
        )
        payload = {}

    metadata = _mapping_field(payload, "metadata", issues, rank=rank, point_id=point_id)
    warnings = _warnings_field(payload, issues, rank=rank, point_id=point_id)
    domain_tags = _string_list_field(payload, "domain_tags")
    chunk_id = _optional_string(payload.get("chunk_id")) or point_id
    for field_name in CRITICAL_PAYLOAD_FIELDS:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                _issue(
                    code="critical_payload_field_missing",
                    message=f"critical payload field {field_name!r} is missing or invalid",
                    rank=rank,
                    chunk_id=chunk_id,
                    details={"field_name": field_name, "point_id": point_id},
                )
            )

    try:
        return RetrievedChunk(
            rank=rank,
            score=score,
            point_id=point_id,
            chunk_id=chunk_id,
            law_id=_optional_string(payload.get("law_id")),
            law_name=_optional_string(payload.get("law_name")),
            level=_optional_string(payload.get("level")),
            chunk_kind=_optional_string(payload.get("chunk_kind")),
            article_number=_optional_string(payload.get("article_number")),
            article_title=_optional_string(payload.get("article_title")),
            clause_number=_optional_string(payload.get("clause_number")),
            point_label=_optional_string(payload.get("point_label")),
            citation=_optional_string(payload.get("citation")),
            hierarchy_path=_optional_string(payload.get("hierarchy_path")),
            source_node_id=_optional_string(payload.get("source_node_id")),
            parent_article_node_id=_optional_string(payload.get("parent_article_node_id")),
            parent_chunk_id=_optional_string(payload.get("parent_chunk_id")),
            text=_optional_string(payload.get("text")),
            parent_text=_optional_string(payload.get("parent_text")),
            text_hash=_optional_string(payload.get("text_hash")),
            parent_text_hash=_optional_string(payload.get("parent_text_hash")),
            source_url=_optional_string(payload.get("source_url")),
            source_domain=_optional_string(payload.get("source_domain")),
            source_type=_optional_string(payload.get("source_type")),
            source_file=_optional_string(payload.get("source_file")),
            metadata=metadata,
            warnings=warnings,
            is_empty_or_repealed=_optional_bool(metadata.get("is_empty_or_repealed")),
            is_source_unit_repealed=_optional_bool(metadata.get("is_source_unit_repealed")),
            embedding_model=_optional_string(payload.get("embedding_model")),
            embedding_revision=_optional_string(payload.get("embedding_revision")),
            indexing_run_id=_optional_string(payload.get("indexing_run_id")),
            payload_schema_version=_optional_string(payload.get("schema_version")),
            effective_date=_optional_string(payload.get("effective_date")),
            expiry_date=_optional_string(payload.get("expiry_date")),
            status=_optional_string(payload.get("status")),
            domain_tags=domain_tags,
            issues=issues,
        )
    except ValidationError as exc:
        raise DenseRetrieverError(f"invalid retrieved chunk at rank {rank}: {exc}") from exc


def _score_from_point(point: Any, *, rank: int) -> float:
    raw_score = getattr(point, "score", None)
    if not isinstance(raw_score, int | float) or not math.isfinite(float(raw_score)):
        raise DenseRetrieverError(f"Qdrant result at rank {rank} has invalid score")
    return float(raw_score)


def _mapping_field(
    payload: Mapping[str, Any],
    field_name: str,
    issues: list[RetrievalIssue],
    *,
    rank: int,
    point_id: str | None,
) -> dict[str, Any]:
    value = payload.get(field_name)
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    issues.append(
        _issue(
            code="payload_metadata_invalid",
            message=f"payload field {field_name!r} is not an object",
            rank=rank,
            details={"point_id": point_id},
        )
    )
    return {}


def _warnings_field(
    payload: Mapping[str, Any],
    issues: list[RetrievalIssue],
    *,
    rank: int,
    point_id: str | None,
) -> list[dict[str, Any]]:
    value = payload.get("warnings")
    if value is None:
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    issues.append(
        _issue(
            code="payload_warnings_invalid",
            message="payload field 'warnings' is not a list",
            rank=rank,
            details={"point_id": point_id},
        )
    )
    return []


def _string_list_field(payload: Mapping[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _issue(
    *,
    code: str,
    message: str,
    rank: int,
    chunk_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> RetrievalIssue:
    return RetrievalIssue(
        code=code,
        severity=RetrievalIssueSeverity.ERROR,
        message=message,
        rank=rank,
        chunk_id=chunk_id,
        details=details or {},
    )
