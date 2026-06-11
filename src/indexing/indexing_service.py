"""Bounded dense-vector indexing orchestration for Phase 8 Slice 8F."""

from __future__ import annotations

import asyncio
import importlib
import json
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from src.indexing.chunk_loader import build_embedding_input
from src.indexing.indexing_models import (
    DenseEmbedding,
    EmbeddingInput,
    EmbeddingTextTemplate,
    IndexingCheckpoint,
    IndexingIssue,
    IndexingIssueSeverity,
    IndexingReport,
    VectorPayload,
)
from src.indexing.payload_builder import (
    build_point_id,
    build_vector_payload,
    vector_payload_to_qdrant_payload,
)
from src.processing.legal_chunk_models import LegalChunk


class IndexingServiceError(RuntimeError):
    """Raised when indexing configuration is invalid or cannot be executed."""


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


class QdrantUpsertClient(Protocol):
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


@dataclass(frozen=True)
class PreparedChunk:
    """Chunk state prepared before embedding or Qdrant mutation."""

    chunk: LegalChunk
    embedding_input: EmbeddingInput
    payload: VectorPayload
    point_id: str


class IndexingService:
    """Coordinate deterministic preparation, dense embedding, and Qdrant upsert.

    The service assumes the target collection already exists with a matching
    named dense-vector schema. It never creates or recreates collections.
    Batch failures are recorded against every affected chunk and later batches
    continue, allowing an honest partial-success report.
    """

    def __init__(
        self,
        *,
        qdrant_client: QdrantUpsertClient | None,
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
        """Initialize a bounded indexing service with injected dependencies."""
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
        phase7_gate_status: str = "not_run",
    ) -> IndexingReport:
        """Stream chunks through deterministic preparation and bounded upserts.

        Args:
            chunks: Validated legal chunks, normally from ``iter_legal_chunks``.
            input_path: Source path recorded in the report only.
            text_template: Existing deterministic embedding text template.
            law_id: Optional exact law filter.
            limit: Optional maximum matching chunks to process.
            dry_run: Prepare payloads and point IDs without embedding or upsert.
            checkpoint_path: Optional JSON checkpoint updated after real
                indexing batches and finalized when the run ends.
            phase7_gate_status: Fresh Phase 7 gate status for report provenance.

        Returns:
            A typed indexing report. Runtime batch failures are represented in
            the report and do not silently skip affected chunks.

        Raises:
            IndexingServiceError: If arguments are invalid or real indexing is
                requested without embedding and Qdrant dependencies.
        """
        template = self._validate_run_arguments(
            input_path=input_path,
            text_template=text_template,
            law_id=law_id,
            limit=limit,
            dry_run=dry_run,
        )
        started = time.perf_counter()
        metrics = _RunMetrics()
        prepared_batch: list[PreparedChunk] = []
        processed_chunk_ids: list[str] = []
        issues: list[IndexingIssue] = []

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
            try:
                prepared = self._prepare_chunk(chunk, template=template)
            except Exception as exc:
                metrics.failed_chunk_ids.append(chunk.chunk_id)
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
                )
                processed_chunk_ids.extend(successful_ids)
                if checkpoint_path is not None:
                    self._write_checkpoint(
                        checkpoint_path,
                        processed_chunk_ids=processed_chunk_ids,
                        failed_chunk_ids=metrics.failed_chunk_ids,
                    )
                prepared_batch = []

        if prepared_batch:
            successful_ids = await self._index_batch(
                prepared_batch,
                metrics=metrics,
                issues=issues,
            )
            processed_chunk_ids.extend(successful_ids)
            if checkpoint_path is not None:
                self._write_checkpoint(
                    checkpoint_path,
                    processed_chunk_ids=processed_chunk_ids,
                    failed_chunk_ids=metrics.failed_chunk_ids,
                )

        if not dry_run and checkpoint_path is not None:
            self._write_checkpoint(
                checkpoint_path,
                processed_chunk_ids=processed_chunk_ids,
                failed_chunk_ids=metrics.failed_chunk_ids,
            )

        runtime_seconds = time.perf_counter() - started
        return self._build_report(
            input_path=input_path,
            template=template,
            law_id=law_id,
            limit=limit,
            dry_run=dry_run,
            phase7_gate_status=phase7_gate_status,
            metrics=metrics,
            issues=issues,
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
    ) -> EmbeddingTextTemplate:
        if not input_path.strip():
            raise IndexingServiceError("input_path must not be blank")
        if law_id is not None and not law_id.strip():
            raise IndexingServiceError("law_id must be null or non-blank")
        if limit is not None and limit < 0:
            raise IndexingServiceError("limit must be greater than or equal to zero")
        try:
            template = EmbeddingTextTemplate(text_template)
        except ValueError as exc:
            raise IndexingServiceError(f"unsupported text template {text_template!r}") from exc
        if not dry_run and self._embedding_model is None:
            raise IndexingServiceError("embedding_model is required for real indexing")
        if not dry_run and self._qdrant_client is None:
            raise IndexingServiceError("qdrant_client is required for real indexing")
        return template

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
        point_id = build_point_id(
            chunk.chunk_id,
            namespace=self.point_id_namespace,
        )
        return PreparedChunk(
            chunk=chunk,
            embedding_input=embedding_input,
            payload=payload,
            point_id=point_id,
        )

    async def _index_batch(
        self,
        batch: Sequence[PreparedChunk],
        *,
        metrics: _RunMetrics,
        issues: list[IndexingIssue],
    ) -> list[str]:
        chunk_ids = [item.chunk.chunk_id for item in batch]
        try:
            if self._embedding_model is None or self._qdrant_client is None:
                raise IndexingServiceError("real indexing dependencies were not configured")
            embeddings = await asyncio.to_thread(
                self._embedding_model.embed_dense,
                [item.embedding_input for item in batch],
                batch_size=self.batch_size,
            )
            self._validate_embeddings(batch, embeddings)
            metrics.embedded_count += len(embeddings)
            points = _build_qdrant_points(
                batch,
                embeddings,
                dense_vector_name=self.dense_vector_name,
            )
            result = await self._qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            _validate_upsert_result(result)
            metrics.upserted_count += len(points)
            return chunk_ids
        except Exception as exc:
            for chunk_id in chunk_ids:
                if chunk_id not in metrics.failed_chunk_ids:
                    metrics.failed_chunk_ids.append(chunk_id)
            issues.append(
                _issue(
                    code="batch_indexing_failed",
                    message=str(exc),
                    details={"chunk_ids": chunk_ids},
                )
            )
            return []

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

    def _write_checkpoint(
        self,
        path: Path | str,
        *,
        processed_chunk_ids: list[str],
        failed_chunk_ids: list[str],
    ) -> None:
        checkpoint = IndexingCheckpoint(
            indexing_run_id=self.indexing_run_id,
            collection_name=self.collection_name,
            dense_dimension=self.dense_dimension,
            processed_chunk_ids=processed_chunk_ids,
            processed_count=len(processed_chunk_ids),
            upserted_count=len(processed_chunk_ids),
            failed_chunk_ids=failed_chunk_ids,
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
        phase7_gate_status: str,
        metrics: _RunMetrics,
        issues: list[IndexingIssue],
        runtime_seconds: float,
    ) -> IndexingReport:
        failed_count = len(metrics.failed_chunk_ids)
        if dry_run:
            status = "dry_run"
        elif failed_count == 0:
            has_error = any(issue.severity == IndexingIssueSeverity.ERROR for issue in issues)
            status = (
                "partial_success"
                if has_error and metrics.upserted_count > 0
                else ("failed" if has_error else "success")
            )
        elif metrics.upserted_count > 0:
            status = "partial_success"
        else:
            status = "failed"
        throughput = metrics.upserted_count / runtime_seconds if runtime_seconds > 0 else 0.0
        payload_rate = (
            metrics.would_upsert_count / metrics.planned_count if metrics.planned_count else 1.0
        )
        return IndexingReport(
            schema_version="0.1.0",
            slice="8F",
            status=status,
            phase7_gate_status=phase7_gate_status,
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
        )


@dataclass
class _RunMetrics:
    total_seen: int = 0
    planned_count: int = 0
    would_embed_count: int = 0
    would_upsert_count: int = 0
    embedded_count: int = 0
    upserted_count: int = 0
    skipped_count: int = 0
    failed_chunk_ids: list[str] = field(default_factory=list)


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
    chunk_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> IndexingIssue:
    return IndexingIssue(
        code=code,
        severity=IndexingIssueSeverity.ERROR,
        message=message,
        chunk_id=chunk_id,
        details=details or {},
    )
