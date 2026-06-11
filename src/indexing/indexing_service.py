"""Operationally hardened dense-vector indexing for Phase 8 Slice 8G."""

from __future__ import annotations

import asyncio
import importlib
import json
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from src.indexing.chunk_loader import build_embedding_input
from src.indexing.indexing_models import (
    DenseEmbedding,
    EmbeddingInput,
    EmbeddingTextTemplate,
    IndexingCheckpoint,
    IndexingIssue,
    IndexingIssueSeverity,
    IndexingReport,
    ProcessedValidationSummary,
    VectorPayload,
)
from src.indexing.payload_builder import (
    build_point_id,
    build_vector_payload,
    vector_payload_to_qdrant_payload,
)
from src.processing.legal_chunk_models import LegalChunk


class IndexingServiceError(RuntimeError):
    """Raised when indexing configuration or resumability state is invalid."""


class DenseEmbeddingModel(Protocol):
    """Dense embedding dependency required by the indexing service."""

    model_name: str
    model_revision: str | None

    def embed_dense(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        batch_size: int,
    ) -> list[DenseEmbedding]:
        """Embed a batch while preserving input order."""
        ...


class QdrantIndexingClient(Protocol):
    """Minimal asynchronous Qdrant client surface required for indexing."""

    async def upsert(
        self,
        *,
        collection_name: str,
        points: Sequence[Any],
        wait: bool,
    ) -> Any:
        """Upsert one batch of Qdrant points."""
        ...

    async def get_collection(self, collection_name: str) -> Any:
        """Return collection metadata for count reconciliation."""
        ...


@dataclass(frozen=True)
class PreparedChunk:
    """Chunk state prepared before embedding or Qdrant mutation."""

    chunk: LegalChunk
    embedding_input: EmbeddingInput
    payload: VectorPayload
    point_id: str


@dataclass
class _RunMetrics:
    total_seen: int = 0
    planned_count: int = 0
    would_embed_count: int = 0
    would_upsert_count: int = 0
    embedded_count: int = 0
    upserted_count: int = 0
    skipped_count: int = 0
    skipped_due_to_checkpoint_count: int = 0
    retry_attempts_total: int = 0
    retried_batch_count: int = 0
    permanently_failed_batch_count: int = 0
    failed_chunk_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _CountReconciliation:
    points_before: int | None = None
    points_after: int | None = None
    indexed_vectors_after: int | None = None
    expected_min_after: int | None = None
    status: str = "not_run"


class IndexingService:
    """Coordinate resumable preparation, dense embedding, and Qdrant upsert.

    The target collection must already exist with a compatible schema.
    Deterministic validation errors are never retried. Only Qdrant upsert
    failures receive the configured bounded retry policy.
    """

    def __init__(
        self,
        *,
        qdrant_client: QdrantIndexingClient | None,
        embedding_model: DenseEmbeddingModel | None,
        collection_name: str,
        point_id_namespace: str,
        dense_vector_name: str = "dense",
        dense_dimension: int = 1024,
        batch_size: int = 4,
        payload_schema_version: str = "0.1.0",
        indexing_run_id: str | None = None,
        model_name: str | None = None,
        model_revision: str | None = None,
    ) -> None:
        """Initialize an indexing service with injected dependencies."""
        if not collection_name.strip():
            raise IndexingServiceError("collection_name must not be blank")
        if not point_id_namespace.strip():
            raise IndexingServiceError("point_id_namespace must not be blank")
        if not dense_vector_name.strip():
            raise IndexingServiceError("dense_vector_name must not be blank")
        if dense_dimension <= 0:
            raise IndexingServiceError("dense_dimension must be positive")
        if batch_size <= 0:
            raise IndexingServiceError("batch_size must be positive")
        if not payload_schema_version.strip():
            raise IndexingServiceError("payload_schema_version must not be blank")

        resolved_model_name = model_name or getattr(embedding_model, "model_name", None)
        if resolved_model_name is None or not resolved_model_name.strip():
            raise IndexingServiceError(
                "model_name must be provided when the embedding model is not loaded"
            )
        resolved_model_revision = (
            model_revision
            if model_revision is not None
            else getattr(embedding_model, "model_revision", None)
        )
        if resolved_model_revision is not None and not resolved_model_revision.strip():
            raise IndexingServiceError("model_revision must be null or non-blank")

        run_id = indexing_run_id or str(uuid.uuid4())
        if not run_id.strip():
            raise IndexingServiceError("indexing_run_id must not be blank")

        self._qdrant_client = qdrant_client
        self._embedding_model = embedding_model
        self.collection_name = collection_name
        self.point_id_namespace = point_id_namespace
        self.dense_vector_name = dense_vector_name
        self.dense_dimension = dense_dimension
        self.batch_size = batch_size
        self.payload_schema_version = payload_schema_version
        self.indexing_run_id = run_id
        self.model_name = resolved_model_name
        self.model_revision = resolved_model_revision

    async def index_chunks(
        self,
        chunks: Iterable[LegalChunk],
        *,
        input_path: str,
        text_template: EmbeddingTextTemplate | str = EmbeddingTextTemplate.TEXT_ONLY,
        law_id: str | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        checkpoint_path: Path | str | None = None,
        resume_checkpoint: IndexingCheckpoint | None = None,
        processed_validation: ProcessedValidationSummary | None = None,
        max_retries: int = 0,
        retry_backoff_seconds: float = 2.0,
        reconcile_counts: bool = False,
        device: str | None = None,
        allow_full_corpus: bool = False,
    ) -> IndexingReport:
        """Stream chunks through resumable bounded embedding and upsert.

        Resume uses the checkpoint's original ``indexing_run_id`` and skips
        only successfully processed chunk IDs. Failed checkpoint IDs remain
        eligible for another attempt.
        """
        template = self._validate_run_arguments(
            input_path=input_path,
            text_template=text_template,
            law_id=law_id,
            limit=limit,
            dry_run=dry_run,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            reconcile_counts=reconcile_counts,
        )
        validation = processed_validation or ProcessedValidationSummary()
        started_at = _utc_now()
        started = time.perf_counter()
        metrics = _RunMetrics()
        issues: list[IndexingIssue] = []
        prepared_batch: list[PreparedChunk] = []

        processed_chunk_ids: list[str] = []
        processed_chunk_id_set: set[str] = set()
        checkpoint_failed_ids: set[str] = set()
        checkpoint_started_at = started_at
        resumed_from_run_id: str | None = None

        if resume_checkpoint is not None:
            self._validate_checkpoint_compatibility(
                resume_checkpoint,
                input_path=input_path,
                template=template,
                law_id=law_id,
            )
            self.indexing_run_id = resume_checkpoint.indexing_run_id
            resumed_from_run_id = resume_checkpoint.indexing_run_id
            processed_chunk_ids = list(dict.fromkeys(resume_checkpoint.processed_chunk_ids))
            processed_chunk_id_set = set(processed_chunk_ids)
            checkpoint_failed_ids = set(resume_checkpoint.failed_chunk_ids)
            checkpoint_started_at = resume_checkpoint.started_at or started_at

        count_before: int | None = None
        if reconcile_counts and not dry_run:
            count_before = await self._read_points_count(issues, stage="before")

        iterator = iter(chunks)
        while limit is None or metrics.planned_count < limit:
            try:
                chunk = next(iterator)
            except StopIteration:
                break
            except Exception as exc:
                issues.append(
                    _issue(
                        code="chunk_stream_failed",
                        message=f"chunk stream failed: {exc}",
                    )
                )
                break

            metrics.total_seen += 1
            if law_id is not None and chunk.law_id != law_id:
                metrics.skipped_count += 1
                continue

            metrics.planned_count += 1
            if chunk.chunk_id in processed_chunk_id_set:
                metrics.skipped_due_to_checkpoint_count += 1
                continue

            try:
                prepared = self._prepare_chunk(chunk, template=template)
            except Exception as exc:
                _append_unique(metrics.failed_chunk_ids, chunk.chunk_id)
                checkpoint_failed_ids.add(chunk.chunk_id)
                issues.append(
                    _issue(
                        code="chunk_preparation_failed",
                        message=str(exc),
                        chunk_id=chunk.chunk_id,
                    )
                )
                continue

            metrics.would_embed_count += 1
            metrics.would_upsert_count += 1
            if dry_run:
                continue

            prepared_batch.append(prepared)
            if len(prepared_batch) >= self.batch_size:
                successful_ids = await self._index_batch(
                    prepared_batch,
                    metrics=metrics,
                    issues=issues,
                    max_retries=max_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
                _record_batch_outcome(
                    prepared_batch,
                    successful_ids=successful_ids,
                    processed_chunk_ids=processed_chunk_ids,
                    processed_chunk_id_set=processed_chunk_id_set,
                    checkpoint_failed_ids=checkpoint_failed_ids,
                )
                if checkpoint_path is not None:
                    self._write_checkpoint(
                        checkpoint_path,
                        input_path=input_path,
                        template=template,
                        law_id=law_id,
                        processed_chunk_ids=processed_chunk_ids,
                        failed_chunk_ids=sorted(checkpoint_failed_ids),
                        started_at=checkpoint_started_at,
                    )
                prepared_batch = []

        if prepared_batch:
            successful_ids = await self._index_batch(
                prepared_batch,
                metrics=metrics,
                issues=issues,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
            )
            _record_batch_outcome(
                prepared_batch,
                successful_ids=successful_ids,
                processed_chunk_ids=processed_chunk_ids,
                processed_chunk_id_set=processed_chunk_id_set,
                checkpoint_failed_ids=checkpoint_failed_ids,
            )

        if not dry_run and checkpoint_path is not None:
            self._write_checkpoint(
                checkpoint_path,
                input_path=input_path,
                template=template,
                law_id=law_id,
                processed_chunk_ids=processed_chunk_ids,
                failed_chunk_ids=sorted(checkpoint_failed_ids),
                started_at=checkpoint_started_at,
            )

        reconciliation = _CountReconciliation()
        if reconcile_counts and not dry_run:
            reconciliation = await self._reconcile_counts(
                points_before=count_before,
                known_persisted_count=len(processed_chunk_id_set),
                issues=issues,
            )

        finished_at = _utc_now()
        runtime_seconds = time.perf_counter() - started
        return self._build_report(
            input_path=input_path,
            template=template,
            law_id=law_id,
            limit=limit,
            dry_run=dry_run,
            checkpoint_path=checkpoint_path,
            resume_checkpoint=resume_checkpoint,
            resumed_from_run_id=resumed_from_run_id,
            processed_validation=validation,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            device=device,
            allow_full_corpus=allow_full_corpus,
            metrics=metrics,
            issues=issues,
            reconciliation=reconciliation,
            started_at=started_at,
            finished_at=finished_at,
            runtime_seconds=runtime_seconds,
        )

    def _validate_run_arguments(
        self,
        *,
        input_path: str,
        text_template: EmbeddingTextTemplate | str,
        law_id: str | None,
        limit: int | None,
        dry_run: bool,
        max_retries: int,
        retry_backoff_seconds: float,
        reconcile_counts: bool,
    ) -> EmbeddingTextTemplate:
        if not input_path.strip():
            raise IndexingServiceError("input_path must not be blank")
        if law_id is not None and not law_id.strip():
            raise IndexingServiceError("law_id must be null or non-blank")
        if limit is not None and limit < 0:
            raise IndexingServiceError("limit must be greater than or equal to zero")
        if max_retries < 0:
            raise IndexingServiceError("max_retries must be greater than or equal to zero")
        if retry_backoff_seconds < 0:
            raise IndexingServiceError(
                "retry_backoff_seconds must be greater than or equal to zero"
            )
        try:
            template = EmbeddingTextTemplate(text_template)
        except ValueError as exc:
            raise IndexingServiceError(f"unsupported text template {text_template!r}") from exc
        if not dry_run and self._embedding_model is None:
            raise IndexingServiceError("embedding_model is required for real indexing")
        if not dry_run and self._qdrant_client is None:
            raise IndexingServiceError("qdrant_client is required for real indexing")
        if reconcile_counts and self._qdrant_client is None:
            raise IndexingServiceError("qdrant_client is required for count reconciliation")
        return template

    def _validate_checkpoint_compatibility(
        self,
        checkpoint: IndexingCheckpoint,
        *,
        input_path: str,
        template: EmbeddingTextTemplate,
        law_id: str | None,
    ) -> None:
        expected: dict[str, object] = {
            "collection_name": self.collection_name,
            "dense_vector_name": self.dense_vector_name,
            "dense_dimension": self.dense_dimension,
            "embedding_model": self.model_name,
            "embedding_revision": self.model_revision,
            "text_template": template,
            "input_path": input_path,
            "law_id_filter": law_id,
            "payload_schema_version": self.payload_schema_version,
        }
        mismatches = [
            f"{field}: checkpoint={getattr(checkpoint, field)!r}, requested={value!r}"
            for field, value in expected.items()
            if getattr(checkpoint, field) != value
        ]
        if mismatches:
            raise IndexingServiceError(
                "checkpoint is incompatible with the requested indexing run: "
                + "; ".join(mismatches)
            )

    def _prepare_chunk(
        self,
        chunk: LegalChunk,
        *,
        template: EmbeddingTextTemplate,
    ) -> PreparedChunk:
        embedding_input = build_embedding_input(chunk, text_template=template)
        payload = build_vector_payload(
            chunk,
            embedding_model=self.model_name,
            embedding_revision=self.model_revision,
            indexing_run_id=self.indexing_run_id,
            payload_schema_version=self.payload_schema_version,
        )
        return PreparedChunk(
            chunk=chunk,
            embedding_input=embedding_input,
            payload=payload,
            point_id=build_point_id(
                chunk.chunk_id,
                namespace=self.point_id_namespace,
            ),
        )

    async def _index_batch(
        self,
        batch: Sequence[PreparedChunk],
        *,
        metrics: _RunMetrics,
        issues: list[IndexingIssue],
        max_retries: int,
        retry_backoff_seconds: float,
    ) -> list[str]:
        chunk_ids = [item.chunk.chunk_id for item in batch]
        if self._embedding_model is None or self._qdrant_client is None:
            raise IndexingServiceError("real indexing dependencies were not configured")

        try:
            embeddings = await asyncio.to_thread(
                self._embedding_model.embed_dense,
                [item.embedding_input for item in batch],
                batch_size=self.batch_size,
            )
            self._validate_embeddings(batch, embeddings)
            points = _build_qdrant_points(
                batch,
                embeddings,
                dense_vector_name=self.dense_vector_name,
            )
        except Exception as exc:
            self._record_permanent_batch_failure(
                chunk_ids,
                metrics=metrics,
                issues=issues,
                message=str(exc),
                code="batch_validation_failed",
            )
            return []

        metrics.embedded_count += len(embeddings)
        retried = False
        for attempt in range(max_retries + 1):
            try:
                result = await self._qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                    wait=True,
                )
                _validate_upsert_result(result)
                metrics.upserted_count += len(points)
                if retried:
                    metrics.retried_batch_count += 1
                return chunk_ids
            except Exception as exc:
                if attempt >= max_retries:
                    if retried:
                        metrics.retried_batch_count += 1
                    self._record_permanent_batch_failure(
                        chunk_ids,
                        metrics=metrics,
                        issues=issues,
                        message=str(exc),
                        code="qdrant_upsert_failed",
                    )
                    return []
                retried = True
                metrics.retry_attempts_total += 1
                issues.append(
                    _issue(
                        code="qdrant_upsert_retry",
                        severity=IndexingIssueSeverity.WARNING,
                        message=f"Qdrant upsert failed; retrying: {exc}",
                        details={
                            "chunk_ids": chunk_ids,
                            "retry_attempt": attempt + 1,
                            "max_retries": max_retries,
                        },
                    )
                )
                if retry_backoff_seconds > 0:
                    await asyncio.sleep(retry_backoff_seconds * (attempt + 1))
        return []

    def _record_permanent_batch_failure(
        self,
        chunk_ids: list[str],
        *,
        metrics: _RunMetrics,
        issues: list[IndexingIssue],
        message: str,
        code: str,
    ) -> None:
        metrics.permanently_failed_batch_count += 1
        for chunk_id in chunk_ids:
            _append_unique(metrics.failed_chunk_ids, chunk_id)
        issues.append(
            _issue(
                code=code,
                message=message,
                details={"chunk_ids": chunk_ids},
            )
        )

    def _validate_embeddings(
        self,
        batch: Sequence[PreparedChunk],
        embeddings: Sequence[DenseEmbedding],
    ) -> None:
        if len(embeddings) != len(batch):
            raise IndexingServiceError(
                f"dense vector count mismatch: expected {len(batch)}, received {len(embeddings)}"
            )
        expected_ids = [item.chunk.chunk_id for item in batch]
        actual_ids = [embedding.chunk_id for embedding in embeddings]
        if actual_ids != expected_ids:
            raise IndexingServiceError(
                f"dense vector chunk order mismatch: expected {expected_ids!r}, "
                f"received {actual_ids!r}"
            )
        for embedding in embeddings:
            if embedding.vector_name != self.dense_vector_name:
                raise IndexingServiceError(
                    f"dense vector name mismatch for {embedding.chunk_id!r}: "
                    f"{embedding.vector_name!r}"
                )
            if embedding.dimension != self.dense_dimension:
                raise IndexingServiceError(
                    f"dense dimension mismatch for {embedding.chunk_id!r}: "
                    f"expected {self.dense_dimension}, received {embedding.dimension}"
                )

    async def _read_points_count(
        self,
        issues: list[IndexingIssue],
        *,
        stage: str,
    ) -> int | None:
        if self._qdrant_client is None:
            return None
        try:
            collection = await self._qdrant_client.get_collection(self.collection_name)
            return _optional_non_negative_int(getattr(collection, "points_count", None))
        except Exception as exc:
            issues.append(
                _issue(
                    code="count_reconciliation_read_failed",
                    severity=IndexingIssueSeverity.WARNING,
                    message=f"unable to read Qdrant collection count {stage} indexing: {exc}",
                )
            )
            return None

    async def _reconcile_counts(
        self,
        *,
        points_before: int | None,
        known_persisted_count: int,
        issues: list[IndexingIssue],
    ) -> _CountReconciliation:
        if self._qdrant_client is None:
            return _CountReconciliation(status="warning")
        try:
            collection = await self._qdrant_client.get_collection(self.collection_name)
            points_after = _optional_non_negative_int(getattr(collection, "points_count", None))
            indexed_vectors = _optional_non_negative_int(
                getattr(collection, "indexed_vectors_count", None)
            )
        except Exception as exc:
            issues.append(
                _issue(
                    code="count_reconciliation_read_failed",
                    severity=IndexingIssueSeverity.WARNING,
                    message=f"unable to read Qdrant collection count after indexing: {exc}",
                )
            )
            return _CountReconciliation(points_before=points_before, status="warning")

        expected_min = max(points_before or 0, known_persisted_count)
        status = "pass" if points_after is not None and points_after >= expected_min else "warning"
        if status == "warning":
            issues.append(
                _issue(
                    code="count_reconciliation_warning",
                    severity=IndexingIssueSeverity.WARNING,
                    message=(
                        f"Qdrant points_count {points_after!r} is below conservative "
                        f"expected minimum {expected_min}"
                    ),
                )
            )
        return _CountReconciliation(
            points_before=points_before,
            points_after=points_after,
            indexed_vectors_after=indexed_vectors,
            expected_min_after=expected_min,
            status=status,
        )

    def _write_checkpoint(
        self,
        path: Path | str,
        *,
        input_path: str,
        template: EmbeddingTextTemplate,
        law_id: str | None,
        processed_chunk_ids: list[str],
        failed_chunk_ids: list[str],
        started_at: str,
    ) -> None:
        checkpoint = IndexingCheckpoint(
            indexing_run_id=self.indexing_run_id,
            collection_name=self.collection_name,
            dense_vector_name=self.dense_vector_name,
            dense_dimension=self.dense_dimension,
            embedding_model=self.model_name,
            embedding_revision=self.model_revision,
            text_template=template,
            input_path=input_path,
            law_id_filter=law_id,
            payload_schema_version=self.payload_schema_version,
            processed_chunk_ids=processed_chunk_ids,
            processed_count=len(processed_chunk_ids),
            upserted_count=len(processed_chunk_ids),
            failed_chunk_ids=failed_chunk_ids,
            started_at=started_at,
            updated_at=_utc_now(),
        )
        _write_json_atomic(Path(path), checkpoint.model_dump(mode="json"))

    def _build_report(
        self,
        *,
        input_path: str,
        template: EmbeddingTextTemplate,
        law_id: str | None,
        limit: int | None,
        dry_run: bool,
        checkpoint_path: Path | str | None,
        resume_checkpoint: IndexingCheckpoint | None,
        resumed_from_run_id: str | None,
        processed_validation: ProcessedValidationSummary,
        max_retries: int,
        retry_backoff_seconds: float,
        device: str | None,
        allow_full_corpus: bool,
        metrics: _RunMetrics,
        issues: list[IndexingIssue],
        reconciliation: _CountReconciliation,
        started_at: str,
        finished_at: str,
        runtime_seconds: float,
    ) -> IndexingReport:
        failed_count = len(metrics.failed_chunk_ids)
        has_error = any(issue.severity == IndexingIssueSeverity.ERROR for issue in issues)
        if dry_run:
            status = "dry_run"
        elif failed_count > 0 or has_error:
            status = "partial_success" if metrics.upserted_count > 0 else "failed"
        else:
            status = "success"
        throughput = metrics.upserted_count / runtime_seconds if runtime_seconds > 0 else 0.0
        payload_rate = (
            metrics.would_upsert_count / metrics.planned_count if metrics.planned_count else 1.0
        )
        return IndexingReport(
            schema_version="0.1.0",
            slice="8G",
            status=status,
            processed_validation_status=processed_validation.status,
            processed_validation_report_path=processed_validation.report_path,
            processed_validation_errors_total=processed_validation.errors_total,
            processed_validation_invalid_chunks=processed_validation.invalid_chunks,
            processed_validation_warnings_total=processed_validation.warnings_total,
            processed_validation_embedding_ready=processed_validation.embedding_ready,
            processed_validation_payload_ready_rate=processed_validation.payload_ready_rate,
            input_chunks_path=input_path,
            input_path=input_path,
            input_chunk_count=metrics.total_seen,
            expected_chunk_count=metrics.planned_count,
            model_name=self.model_name,
            model_revision=self.model_revision,
            dense_vector_name=self.dense_vector_name,
            dense_dimension=self.dense_dimension,
            sparse_enabled=False,
            collection_name=self.collection_name,
            indexed_points=metrics.upserted_count,
            failed_chunks=failed_count,
            issues=issues,
            payload_completeness_rate=payload_rate,
            readiness_for_phase9=False,
            text_template=template,
            law_id_filter=law_id,
            limit=limit,
            batch_size=self.batch_size,
            dry_run=dry_run,
            indexing_run_id=self.indexing_run_id,
            total_seen=metrics.total_seen,
            planned_count=metrics.planned_count,
            would_embed_count=metrics.would_embed_count,
            would_upsert_count=metrics.would_upsert_count,
            embedded_count=metrics.embedded_count,
            upserted_count=metrics.upserted_count,
            failed_count=failed_count,
            skipped_count=metrics.skipped_count,
            failed_chunk_ids=metrics.failed_chunk_ids,
            runtime_seconds=runtime_seconds,
            throughput_chunks_per_second=throughput,
            device=device,
            allow_full_corpus=allow_full_corpus,
            resume=resume_checkpoint is not None,
            checkpoint_path=str(checkpoint_path) if checkpoint_path is not None else None,
            checkpoint_processed_count=(
                resume_checkpoint.processed_count if resume_checkpoint is not None else 0
            ),
            skipped_due_to_checkpoint_count=metrics.skipped_due_to_checkpoint_count,
            resumed_from_indexing_run_id=resumed_from_run_id,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            retry_attempts_total=metrics.retry_attempts_total,
            retried_batch_count=metrics.retried_batch_count,
            permanently_failed_batch_count=metrics.permanently_failed_batch_count,
            started_at=started_at,
            finished_at=finished_at,
            qdrant_points_count_before=reconciliation.points_before,
            qdrant_points_count_after=reconciliation.points_after,
            qdrant_indexed_vectors_count_after=reconciliation.indexed_vectors_after,
            expected_min_points_after=reconciliation.expected_min_after,
            count_reconciliation_status=reconciliation.status,
        )


def load_indexing_checkpoint(path: Path | str) -> IndexingCheckpoint:
    """Load a compatible 8G checkpoint from UTF-8 JSON."""
    checkpoint_path = Path(path)
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        return IndexingCheckpoint.model_validate(payload)
    except OSError as exc:
        raise IndexingServiceError(f"unable to read checkpoint {checkpoint_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IndexingServiceError(
            f"checkpoint {checkpoint_path} is invalid JSON: {exc.msg}"
        ) from exc
    except ValidationError as exc:
        raise IndexingServiceError(
            f"checkpoint {checkpoint_path} is incompatible with Slice 8G: {exc}"
        ) from exc


def _record_batch_outcome(
    batch: Sequence[PreparedChunk],
    *,
    successful_ids: list[str],
    processed_chunk_ids: list[str],
    processed_chunk_id_set: set[str],
    checkpoint_failed_ids: set[str],
) -> None:
    successful_set = set(successful_ids)
    for item in batch:
        chunk_id = item.chunk.chunk_id
        if chunk_id in successful_set:
            if chunk_id not in processed_chunk_id_set:
                processed_chunk_ids.append(chunk_id)
                processed_chunk_id_set.add(chunk_id)
            checkpoint_failed_ids.discard(chunk_id)
        else:
            checkpoint_failed_ids.add(chunk_id)


def _build_qdrant_points(
    batch: Sequence[PreparedChunk],
    embeddings: Sequence[DenseEmbedding],
    *,
    dense_vector_name: str,
) -> list[Any]:
    models = _load_qdrant_models()
    return [
        models.PointStruct(
            id=prepared.point_id,
            vector={dense_vector_name: embedding.values},
            payload=vector_payload_to_qdrant_payload(prepared.payload),
        )
        for prepared, embedding in zip(batch, embeddings, strict=True)
    ]


def _load_qdrant_models() -> Any:
    try:
        module = importlib.import_module("qdrant_client")
    except ImportError as exc:
        raise IndexingServiceError(
            "qdrant-client is required for real indexing; install it with `uv sync --extra qdrant`"
        ) from exc
    return module.models


def _validate_upsert_result(result: Any) -> None:
    status = getattr(result, "status", None)
    if status is None:
        return
    value = str(getattr(status, "value", status))
    if value not in {"completed", "acknowledged"}:
        raise IndexingServiceError(f"Qdrant upsert returned non-success status {value!r}")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _issue(
    *,
    code: str,
    message: str,
    severity: IndexingIssueSeverity = IndexingIssueSeverity.ERROR,
    chunk_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> IndexingIssue:
    return IndexingIssue(
        code=code,
        severity=severity,
        message=message,
        chunk_id=chunk_id,
        details=details or {},
    )


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    return parsed if parsed >= 0 else None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
