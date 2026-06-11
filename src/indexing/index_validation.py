"""Read-only Qdrant index validation for Phase 8 Slice 8H."""

from __future__ import annotations

import asyncio
import importlib
import math
import re
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from src.indexing.indexing_models import (
    CollectionValidationResult,
    FilterValidationResult,
    IndexingIssue,
    IndexingIssueSeverity,
    IndexValidationReport,
    PayloadFilterCheck,
    PayloadFilterCheckResult,
    PointValidationResult,
    RetrievalHitSummary,
    RetrievalSanityQuery,
    RetrievalSanityQueryResult,
    RetrievalSanityResult,
    SampledPointSummary,
)
from src.indexing.qdrant_collection import build_payload_index_specs

DEFAULT_REQUIRED_PAYLOAD_FIELDS = (
    "schema_version",
    "chunk_id",
    "law_id",
    "law_name",
    "level",
    "chunk_kind",
    "citation",
    "hierarchy_path",
    "source_node_id",
    "text",
    "parent_text",
    "text_hash",
    "parent_text_hash",
    "source_url",
    "source_domain",
    "source_type",
    "source_file",
    "metadata",
    "warnings",
    "embedding_model",
    "indexing_run_id",
    "effective_date",
    "expiry_date",
    "status",
    "domain_tags",
)


class IndexValidationError(RuntimeError):
    """Raised when read-only Qdrant validation cannot be executed."""


class IndexValidationClient(Protocol):
    """Minimal asynchronous Qdrant surface used by Slice 8H."""

    async def get_collection(self, collection_name: str) -> Any:
        """Return collection schema and count metadata."""
        ...

    async def scroll(self, **kwargs: Any) -> tuple[list[Any], Any]:
        """Read a bounded point sample."""
        ...

    async def count(self, **kwargs: Any) -> Any:
        """Count points matching one payload filter."""
        ...

    async def query_points(self, **kwargs: Any) -> Any:
        """Run one bounded named-vector query."""
        ...


class QueryEmbeddingModel(Protocol):
    """Query-only dense embedding surface needed for sanity checks."""

    def embed_query(self, query_text: str, *, batch_size: int = 1) -> list[float]:
        """Embed one query into a finite dense vector."""
        ...


async def validate_collection_schema(
    client: IndexValidationClient,
    *,
    collection_name: str,
    dense_vector_name: str,
    dense_dimension: int,
    expected_distance: str = "Cosine",
    expected_min_points: int | None = None,
) -> CollectionValidationResult:
    """Validate collection status, named vector schema, counts, and payload indexes.

    Args:
        client: Injected read-only Qdrant-compatible client.
        collection_name: Existing collection to inspect.
        dense_vector_name: Required named dense-vector key.
        dense_dimension: Required measured dense-vector dimension.
        expected_distance: Required Qdrant distance metric.
        expected_min_points: Optional conservative minimum point count.

    Returns:
        Typed schema validation result.

    Raises:
        IndexValidationError: If arguments are invalid or collection metadata
            cannot be read.
    """
    _validate_common_arguments(
        collection_name=collection_name,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
    )
    if not expected_distance.strip():
        raise IndexValidationError("expected_distance must not be blank")
    if expected_min_points is not None and expected_min_points < 0:
        raise IndexValidationError("expected_min_points must be non-negative")

    try:
        collection = await client.get_collection(collection_name)
    except Exception as exc:
        raise IndexValidationError(
            f"unable to read Qdrant collection {collection_name!r}: {exc}"
        ) from exc

    issues: list[IndexingIssue] = []
    status_value = _enum_value(getattr(collection, "status", None))
    status_normalized = status_value.casefold() if status_value else ""
    if status_normalized not in {"green", "yellow", "grey", "gray"}:
        issues.append(
            _issue(
                code="collection_status_unacceptable",
                message=f"collection status is {status_value!r}",
            )
        )
    elif status_normalized != "green":
        issues.append(
            _issue(
                code="collection_status_not_green",
                severity=IndexingIssueSeverity.WARNING,
                message=f"collection status is {status_value!r}, not green",
            )
        )

    vectors = _collection_vectors(collection)
    dense = vectors.get(dense_vector_name) if isinstance(vectors, Mapping) else None
    actual_dimension = getattr(dense, "size", None)
    actual_distance = _enum_value(getattr(dense, "distance", None))
    if dense is None:
        issues.append(
            _issue(
                code="dense_vector_missing",
                message=f"named dense vector {dense_vector_name!r} is missing",
            )
        )
    else:
        if actual_dimension != dense_dimension:
            issues.append(
                _issue(
                    code="dense_dimension_mismatch",
                    message=(
                        f"dense dimension is {actual_dimension!r}, expected {dense_dimension}"
                    ),
                )
            )
        if actual_distance.casefold() != expected_distance.casefold():
            issues.append(
                _issue(
                    code="dense_distance_mismatch",
                    message=(
                        f"dense distance is {actual_distance!r}, expected {expected_distance!r}"
                    ),
                )
            )

    points_count = _optional_non_negative_int(getattr(collection, "points_count", None))
    indexed_vectors_count = _optional_non_negative_int(
        getattr(collection, "indexed_vectors_count", None)
    )
    if points_count is None:
        issues.append(
            _issue(
                code="points_count_missing",
                message="collection metadata does not expose points_count",
            )
        )
    elif expected_min_points is not None and points_count < expected_min_points:
        issues.append(
            _issue(
                code="points_count_below_expected",
                message=(
                    f"points_count is {points_count}, expected at least {expected_min_points}"
                ),
            )
        )
    if indexed_vectors_count == 0 and (points_count or 0) > 0:
        issues.append(
            _issue(
                code="indexed_vectors_count_zero",
                severity=IndexingIssueSeverity.INFO,
                message=(
                    "indexed_vectors_count is zero; tiny collections may remain below "
                    "Qdrant's vector-indexing threshold"
                ),
            )
        )

    expected_indexes = [spec.field_name for spec in build_payload_index_specs()]
    payload_schema = getattr(collection, "payload_schema", None) or {}
    present_indexes = [name for name in expected_indexes if name in payload_schema]
    missing_indexes = [name for name in expected_indexes if name not in payload_schema]
    for field_name in missing_indexes:
        issues.append(
            _issue(
                code="payload_index_missing",
                message=f"required payload index {field_name!r} is missing",
                details={"field_name": field_name},
            )
        )

    return CollectionValidationResult(
        status=_status_from_issues(issues),
        collection_status=status_value or None,
        points_count=points_count,
        indexed_vectors_count=indexed_vectors_count,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
        distance=expected_distance,
        payload_indexes_present=present_indexes,
        payload_indexes_missing=missing_indexes,
        issues=issues,
    )


async def validate_sampled_points(
    client: IndexValidationClient,
    *,
    collection_name: str,
    dense_vector_name: str,
    dense_dimension: int,
    sample_limit: int = 10,
    require_payload_fields: Sequence[str] | None = None,
    check_vectors: bool = True,
) -> PointValidationResult:
    """Validate payload completeness and optional dense vectors on a point sample."""
    _validate_common_arguments(
        collection_name=collection_name,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
    )
    if sample_limit <= 0:
        raise IndexValidationError("sample_limit must be positive")
    required_fields = tuple(require_payload_fields or DEFAULT_REQUIRED_PAYLOAD_FIELDS)
    if any(not field.strip() for field in required_fields):
        raise IndexValidationError("required payload fields must not be blank")

    try:
        records, _ = await client.scroll(
            collection_name=collection_name,
            limit=sample_limit,
            with_payload=True,
            with_vectors=[dense_vector_name] if check_vectors else False,
        )
    except Exception as exc:
        raise IndexValidationError(f"unable to sample Qdrant points: {exc}") from exc

    points: list[SampledPointSummary] = []
    aggregate_issues: list[IndexingIssue] = []
    if not records:
        aggregate_issues.append(
            _issue(code="point_sample_empty", message="Qdrant returned no sampled points")
        )

    for record in records:
        summary = _validate_point(
            record,
            dense_vector_name=dense_vector_name,
            dense_dimension=dense_dimension,
            required_fields=required_fields,
            check_vectors=check_vectors,
        )
        points.append(summary)
        aggregate_issues.extend(summary.issues)

    payload_issues = [
        issue
        for issue in aggregate_issues
        if issue.code.startswith("payload_") or issue.code == "point_sample_empty"
    ]
    vector_issues = [issue for issue in aggregate_issues if issue.code.startswith("vector_")]
    payload_status = _status_from_issues(payload_issues)
    vector_status = _status_from_issues(vector_issues) if check_vectors else "not_run"
    overall_status = _combine_statuses(payload_status, vector_status)
    return PointValidationResult(
        status=overall_status,
        payload_status=payload_status,
        vector_status=vector_status,
        sampled_point_count=len(points),
        points=points,
        issues=aggregate_issues,
    )


async def validate_payload_filters(
    client: IndexValidationClient,
    *,
    collection_name: str,
    filters: Sequence[PayloadFilterCheck],
    sample_limit: int = 3,
) -> FilterValidationResult:
    """Validate exact-match payload filters without mutating Qdrant."""
    if not collection_name.strip():
        raise IndexValidationError("collection_name must not be blank")
    if sample_limit <= 0:
        raise IndexValidationError("sample_limit must be positive")
    models = _load_qdrant_models()
    results: list[PayloadFilterCheckResult] = []
    aggregate_issues: list[IndexingIssue] = []

    for check in filters:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key=check.field_name,
                    match=models.MatchValue(value=check.match_value),
                )
            ]
        )
        try:
            count_result = await client.count(
                collection_name=collection_name,
                count_filter=query_filter,
                exact=True,
            )
            records, _ = await client.scroll(
                collection_name=collection_name,
                scroll_filter=query_filter,
                limit=sample_limit,
                with_payload=False,
                with_vectors=False,
            )
        except Exception as exc:
            issue = _issue(
                code="payload_filter_failed",
                message=f"payload filter {check.name!r} failed: {exc}",
                details={"field_name": check.field_name},
            )
            result = PayloadFilterCheckResult(
                name=check.name,
                field_name=check.field_name,
                match_value=check.match_value,
                status="failed",
                issues=[issue],
            )
            results.append(result)
            aggregate_issues.append(issue)
            continue

        returned_count = _optional_non_negative_int(getattr(count_result, "count", None))
        if returned_count is None:
            issue = _issue(
                code="payload_filter_count_missing",
                message=f"payload filter {check.name!r} did not return a count",
            )
            status = "failed"
            check_issues = [issue]
        elif returned_count == 0:
            issue = _issue(
                code="payload_filter_no_matches",
                severity=IndexingIssueSeverity.WARNING,
                message=f"payload filter {check.name!r} returned no points",
            )
            status = "warning"
            check_issues = [issue]
        else:
            status = "pass"
            check_issues = []
        aggregate_issues.extend(check_issues)
        results.append(
            PayloadFilterCheckResult(
                name=check.name,
                field_name=check.field_name,
                match_value=check.match_value,
                returned_count=returned_count or 0,
                status=status,
                sample_point_ids=[str(record.id) for record in records],
                issues=check_issues,
            )
        )

    return FilterValidationResult(
        status=_combine_statuses(*(result.status for result in results)),
        checks=results,
        issues=aggregate_issues,
    )


async def run_retrieval_sanity_checks(
    client: IndexValidationClient,
    embedding_model: QueryEmbeddingModel,
    *,
    collection_name: str,
    dense_vector_name: str,
    dense_dimension: int,
    queries: Sequence[RetrievalSanityQuery],
    top_k: int = 3,
) -> RetrievalSanityResult:
    """Run bounded query embedding and named-vector search sanity checks."""
    _validate_common_arguments(
        collection_name=collection_name,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
    )
    if top_k <= 0:
        raise IndexValidationError("top_k must be positive")

    query_results: list[RetrievalSanityQueryResult] = []
    aggregate_issues: list[IndexingIssue] = []
    for query in queries:
        try:
            vector = await asyncio.to_thread(
                embedding_model.embed_query,
                query.query_text,
                batch_size=1,
            )
            if len(vector) != dense_dimension:
                raise IndexValidationError(
                    f"query vector dimension is {len(vector)}, expected {dense_dimension}"
                )
            if not vector or not all(math.isfinite(value) for value in vector):
                raise IndexValidationError("query vector must be non-empty and finite")
            response = await client.query_points(
                collection_name=collection_name,
                query=vector,
                using=dense_vector_name,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
            hits = [_summarize_hit(point) for point in getattr(response, "points", [])]
        except Exception as exc:
            issue = _issue(
                code="retrieval_sanity_failed",
                message=f"retrieval sanity query failed: {exc}",
                details={"query_text": query.query_text},
            )
            aggregate_issues.append(issue)
            query_results.append(
                RetrievalSanityQueryResult(
                    query_text=query.query_text,
                    top_k=top_k,
                    expected_hint_terms=query.expected_hint_terms,
                    status="failed",
                    issues=[issue],
                )
            )
            continue

        matched = _expected_hints_match(query.expected_hint_terms, hits)
        query_issues: list[IndexingIssue] = []
        if not hits:
            query_issues.append(
                _issue(
                    code="retrieval_no_results",
                    message="dense retrieval returned no points",
                    details={"query_text": query.query_text},
                )
            )
            status = "failed"
        elif not matched:
            query_issues.append(
                _issue(
                    code="retrieval_expected_hint_missing",
                    severity=IndexingIssueSeverity.WARNING,
                    message="expected hint terms were not all found in the top results",
                    details={"expected_hint_terms": query.expected_hint_terms},
                )
            )
            status = "warning"
        else:
            status = "pass"
        aggregate_issues.extend(query_issues)
        query_results.append(
            RetrievalSanityQueryResult(
                query_text=query.query_text,
                top_k=top_k,
                returned_count=len(hits),
                query_vector_dimension=len(vector),
                expected_hint_terms=query.expected_hint_terms,
                expected_hints_matched=matched,
                status=status,
                results=hits,
                issues=query_issues,
            )
        )

    return RetrievalSanityResult(
        status=_combine_statuses(*(result.status for result in query_results)),
        queries_run=len(query_results),
        query_results=query_results,
        issues=aggregate_issues,
    )


async def validate_index(
    client: IndexValidationClient,
    *,
    report_type: str = "index_validation_report",
    run_type: str = "development_index_validation",
    pipeline_stage: str = "index_validation",
    collection_name: str,
    dense_vector_name: str,
    dense_dimension: int,
    expected_distance: str,
    expected_min_points: int | None,
    sample_limit: int,
    filters: Sequence[PayloadFilterCheck],
    queries: Sequence[RetrievalSanityQuery],
    top_k: int,
    check_vectors: bool,
    embedding_model: QueryEmbeddingModel | None,
) -> IndexValidationReport:
    """Run all configured Slice 8H read-only validations and build one report."""
    started_at = _utc_now()
    started = time.perf_counter()
    collection = await validate_collection_schema(
        client,
        collection_name=collection_name,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
        expected_distance=expected_distance,
        expected_min_points=expected_min_points,
    )
    sampled_points = await validate_sampled_points(
        client,
        collection_name=collection_name,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
        sample_limit=sample_limit,
        check_vectors=check_vectors,
    )
    filter_result = await validate_payload_filters(
        client,
        collection_name=collection_name,
        filters=filters,
    )
    if embedding_model is None:
        retrieval = RetrievalSanityResult(status="not_run")
    else:
        retrieval = await run_retrieval_sanity_checks(
            client,
            embedding_model,
            collection_name=collection_name,
            dense_vector_name=dense_vector_name,
            dense_dimension=dense_dimension,
            queries=queries,
            top_k=top_k,
        )

    component_status = _combine_statuses(
        collection.status,
        sampled_points.status,
        filter_result.status,
        retrieval.status,
    )
    report_status = {
        "pass": "success",
        "warning": "warning",
        "failed": "failed",
    }[component_status]
    finished_at = _utc_now()
    issues = [
        *collection.issues,
        *sampled_points.issues,
        *filter_result.issues,
        *retrieval.issues,
    ]
    return IndexValidationReport(
        report_type=report_type,
        run_type=run_type,
        pipeline_stage=pipeline_stage,
        status=report_status,
        collection_name=collection_name,
        dense_vector_name=dense_vector_name,
        dense_dimension=dense_dimension,
        expected_distance=expected_distance,
        points_count=collection.points_count,
        indexed_vectors_count=collection.indexed_vectors_count,
        collection_schema_status=collection.status,
        sampled_point_count=sampled_points.sampled_point_count,
        payload_validation_status=sampled_points.payload_status,
        vector_validation_status=sampled_points.vector_status,
        filter_validation_status=filter_result.status,
        retrieval_sanity_status=retrieval.status,
        queries_run=retrieval.queries_run,
        collection=collection,
        sampled_points=sampled_points,
        filters=filter_result,
        retrieval=retrieval,
        issues=issues,
        started_at=started_at,
        finished_at=finished_at,
        runtime_seconds=time.perf_counter() - started,
    )


def _validate_point(
    record: Any,
    *,
    dense_vector_name: str,
    dense_dimension: int,
    required_fields: Sequence[str],
    check_vectors: bool,
) -> SampledPointSummary:
    point_id = str(record.id)
    payload = getattr(record, "payload", None)
    issues: list[IndexingIssue] = []
    missing_fields: list[str] = []
    if not isinstance(payload, Mapping):
        missing_fields = list(required_fields)
        issues.append(
            _issue(
                code="payload_not_object",
                message="point payload is not object-like",
                details={"point_id": point_id},
            )
        )
        payload = {}
    else:
        missing_fields = [field for field in required_fields if field not in payload]
        for field in missing_fields:
            issues.append(
                _issue(
                    code="payload_field_missing",
                    message=f"required payload field {field!r} is missing",
                    details={"point_id": point_id, "field_name": field},
                )
            )

    for field_name in ("chunk_id", "law_id", "text", "citation"):
        value = payload.get(field_name)
        if field_name in payload and (not isinstance(value, str) or not value.strip()):
            issues.append(
                _issue(
                    code="payload_required_value_invalid",
                    message=f"payload field {field_name!r} must be a non-blank string",
                    details={"point_id": point_id, "field_name": field_name},
                )
            )
    if "parent_text" in payload and not isinstance(payload.get("parent_text"), str):
        issues.append(
            _issue(
                code="payload_parent_text_invalid",
                message="payload field 'parent_text' must be present as a string",
                details={"point_id": point_id},
            )
        )
    if "metadata" in payload and not isinstance(payload.get("metadata"), Mapping):
        issues.append(
            _issue(
                code="payload_metadata_invalid",
                message="payload field 'metadata' must be object-like",
                details={"point_id": point_id},
            )
        )
    if "warnings" in payload and not isinstance(payload.get("warnings"), list):
        issues.append(
            _issue(
                code="payload_warnings_invalid",
                message="payload field 'warnings' must be list-like",
                details={"point_id": point_id},
            )
        )
    if "domain_tags" in payload and not isinstance(payload.get("domain_tags"), list):
        issues.append(
            _issue(
                code="payload_domain_tags_invalid",
                message="payload field 'domain_tags' must be list-like",
                details={"point_id": point_id},
            )
        )

    vector_present: bool | None = None
    vector_dimension: int | None = None
    vector_finite: bool | None = None
    if check_vectors:
        vector = getattr(record, "vector", None)
        dense_values = vector.get(dense_vector_name) if isinstance(vector, Mapping) else None
        vector_present = dense_values is not None
        if dense_values is None:
            issues.append(
                _issue(
                    code="vector_dense_missing",
                    message=f"named vector {dense_vector_name!r} is missing",
                    details={"point_id": point_id},
                )
            )
        else:
            try:
                values = [float(value) for value in dense_values]
            except (TypeError, ValueError):
                values = []
                issues.append(
                    _issue(
                        code="vector_values_invalid",
                        message="dense vector contains non-numeric values",
                        details={"point_id": point_id},
                    )
                )
            vector_dimension = len(values)
            vector_finite = bool(values) and all(math.isfinite(value) for value in values)
            if vector_dimension != dense_dimension:
                issues.append(
                    _issue(
                        code="vector_dimension_mismatch",
                        message=(
                            f"dense vector dimension is {vector_dimension}, "
                            f"expected {dense_dimension}"
                        ),
                        details={"point_id": point_id},
                    )
                )
            if not vector_finite:
                issues.append(
                    _issue(
                        code="vector_values_non_finite",
                        message="dense vector is empty or contains NaN/Infinity",
                        details={"point_id": point_id},
                    )
                )

    payload_complete = not any(issue.code.startswith("payload_") for issue in issues)
    return SampledPointSummary(
        point_id=point_id,
        chunk_id=payload.get("chunk_id") if isinstance(payload.get("chunk_id"), str) else None,
        payload_complete=payload_complete,
        vector_present=vector_present,
        vector_dimension=vector_dimension,
        vector_finite=vector_finite,
        missing_payload_fields=missing_fields,
        issues=issues,
    )


def _summarize_hit(point: Any) -> RetrievalHitSummary:
    payload = getattr(point, "payload", None)
    payload = payload if isinstance(payload, Mapping) else {}
    text = payload.get("text")
    preview = None
    if isinstance(text, str):
        preview = text if len(text) <= 240 else text[:237] + "..."
    return RetrievalHitSummary(
        point_id=str(point.id),
        score=float(getattr(point, "score", 0.0)),
        chunk_id=_optional_string(payload.get("chunk_id")),
        citation=_optional_string(payload.get("citation")),
        law_id=_optional_string(payload.get("law_id")),
        level=_optional_string(payload.get("level")),
        chunk_kind=_optional_string(payload.get("chunk_kind")),
        text_preview=preview,
    )


def _expected_hints_match(
    expected_terms: Sequence[str],
    hits: Sequence[RetrievalHitSummary],
) -> bool:
    if not expected_terms:
        return True
    searchable = _normalize_hint_text(
        " ".join(
            value for hit in hits for value in (hit.citation, hit.text_preview) if value is not None
        )
    )
    return all(_normalize_hint_text(term) in searchable for term in expected_terms)


def _normalize_hint_text(value: str) -> str:
    """Normalize case, punctuation, and whitespace for non-brittle hint matching."""
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _collection_vectors(collection: Any) -> Any:
    config = getattr(collection, "config", None)
    params = getattr(config, "params", None)
    return getattr(params, "vectors", {})


def _load_qdrant_models() -> Any:
    try:
        module = importlib.import_module("qdrant_client")
    except ImportError as exc:
        raise IndexValidationError(
            "qdrant-client is required for index validation; "
            "install it with `uv sync --extra qdrant`"
        ) from exc
    return module.models


def _validate_common_arguments(
    *,
    collection_name: str,
    dense_vector_name: str,
    dense_dimension: int,
) -> None:
    if not collection_name.strip():
        raise IndexValidationError("collection_name must not be blank")
    if not dense_vector_name.strip():
        raise IndexValidationError("dense_vector_name must not be blank")
    if dense_dimension <= 0:
        raise IndexValidationError("dense_dimension must be positive")


def _status_from_issues(issues: Sequence[IndexingIssue]) -> str:
    if any(issue.severity == IndexingIssueSeverity.ERROR for issue in issues):
        return "failed"
    if any(issue.severity == IndexingIssueSeverity.WARNING for issue in issues):
        return "warning"
    return "pass"


def _combine_statuses(*statuses: str) -> str:
    relevant = [status for status in statuses if status != "not_run"]
    if any(status == "failed" for status in relevant):
        return "failed"
    if any(status == "warning" for status in relevant):
        return "warning"
    return "pass"


def _issue(
    *,
    code: str,
    message: str,
    severity: IndexingIssueSeverity = IndexingIssueSeverity.ERROR,
    details: dict[str, Any] | None = None,
) -> IndexingIssue:
    return IndexingIssue(
        code=code,
        severity=severity,
        message=message,
        details=details or {},
    )


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    return parsed if parsed >= 0 else None


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
