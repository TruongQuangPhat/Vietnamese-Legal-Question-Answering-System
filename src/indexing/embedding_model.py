"""Dense BGE-M3 embedding wrapper for the constrained embedding/indexing pilot.

Heavy model dependencies are imported lazily. The wrapper accepts an injected
encoder for unit tests and never connects to Qdrant or persists vectors.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from pydantic import ValidationError

from src.indexing.indexing_models import DenseEmbedding, EmbeddingInput


class EmbeddingModelError(RuntimeError):
    """Failure while loading or invoking the optional embedding model."""


class DenseEncoder(Protocol):
    """Minimal protocol implemented by the FlagEmbedding BGE-M3 encoder."""

    def encode(self, sentences: list[str], **kwargs: Any) -> object:
        """Encode text into dense vectors."""
        ...


ModelFactory = Callable[..., DenseEncoder]


class BgeM3EmbeddingModel:
    """Lazily load BGE-M3 and produce validated dense embedding contracts.

    Args:
        model_name: Hugging Face model identifier or local model path.
        model_revision: Optional pinned model revision.
        device: Requested device: ``auto``, ``cpu``, or ``cuda``.
        normalize_embeddings: Whether to L2-normalize dense vectors.
        max_length: Optional maximum model input length.
        dense_vector_name: Named dense vector identifier for later indexing.
        encoder: Optional injected encoder used by tests.
        model_factory: Optional injected factory used instead of importing
            ``FlagEmbedding.BGEM3FlagModel``.

    Raises:
        ValueError: If constructor values are blank or unsupported.
    """

    def __init__(
        self,
        *,
        model_name: str,
        model_revision: str | None = None,
        device: str = "auto",
        normalize_embeddings: bool = True,
        max_length: int | None = None,
        dense_vector_name: str = "dense",
        encoder: DenseEncoder | None = None,
        model_factory: ModelFactory | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be blank")
        if model_revision is not None and not model_revision.strip():
            raise ValueError("model_revision must be null or non-blank")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be one of: auto, cpu, cuda")
        if max_length is not None and max_length <= 0:
            raise ValueError("max_length must be positive when provided")
        if not dense_vector_name.strip():
            raise ValueError("dense_vector_name must not be blank")

        self.model_name = model_name
        self.model_revision = model_revision
        self.device_requested = device
        self.normalize_embeddings = normalize_embeddings
        self.max_length = max_length
        self.dense_vector_name = dense_vector_name
        self._encoder = encoder
        self._model_factory = model_factory
        self._device_effective: str | None = None

    @property
    def device_effective(self) -> str | None:
        """Return the resolved device after model loading, if known."""
        return self._device_effective

    def embed_dense(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        batch_size: int,
    ) -> list[DenseEmbedding]:
        """Embed inputs and return validated dense vectors in input order.

        Args:
            inputs: Typed embedding inputs.
            batch_size: Positive encoder batch size.

        Returns:
            Dense embeddings preserving input ``chunk_id`` order.

        Raises:
            EmbeddingModelError: If loading, encoding, output extraction, or
                dense-vector validation fails.
            ValueError: If ``batch_size`` is not positive.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not inputs:
            return []

        encoder = self._get_encoder()
        encode_kwargs: dict[str, object] = {
            "batch_size": batch_size,
            "return_dense": True,
            "return_sparse": False,
            "return_colbert_vecs": False,
        }
        if self.max_length is not None:
            encode_kwargs["max_length"] = self.max_length

        try:
            output = encoder.encode(
                [item.embedding_text for item in inputs],
                **encode_kwargs,
            )
        except Exception as exc:
            raise EmbeddingModelError(f"BGE-M3 dense encoding failed: {exc}") from exc

        rows = _extract_dense_rows(output, expected_count=len(inputs))
        dimensions = {len(row) for row in rows}
        if len(dimensions) != 1:
            raise EmbeddingModelError(
                f"dense output dimensions are inconsistent: {sorted(dimensions)}"
            )

        embeddings: list[DenseEmbedding] = []
        for item, row in zip(inputs, rows, strict=True):
            values = _normalize(row) if self.normalize_embeddings else row
            try:
                embeddings.append(
                    DenseEmbedding(
                        chunk_id=item.chunk_id,
                        vector_name=self.dense_vector_name,
                        values=values,
                        dimension=len(values),
                        model_name=self.model_name,
                        model_revision=self.model_revision,
                    )
                )
            except ValidationError as exc:
                raise EmbeddingModelError(
                    f"invalid dense vector for chunk {item.chunk_id!r}: {exc}"
                ) from exc
        return embeddings

    def embed_query(self, query_text: str, *, batch_size: int = 1) -> list[float]:
        """Embed one query for a bounded dense retrieval sanity check.

        Args:
            query_text: Non-blank Vietnamese query text.
            batch_size: Positive encoder batch size.

        Returns:
            One finite dense vector measured from model output.

        Raises:
            EmbeddingModelError: If loading, encoding, or vector validation
                fails.
            ValueError: If the query is blank or the batch size is invalid.
        """
        if not query_text.strip():
            raise ValueError("query_text must not be blank")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        encoder = self._get_encoder()
        encode_kwargs: dict[str, object] = {
            "batch_size": batch_size,
            "return_dense": True,
            "return_sparse": False,
            "return_colbert_vecs": False,
        }
        if self.max_length is not None:
            encode_kwargs["max_length"] = self.max_length
        try:
            output = encoder.encode([query_text], **encode_kwargs)
        except Exception as exc:
            raise EmbeddingModelError(f"BGE-M3 query encoding failed: {exc}") from exc

        rows = _extract_dense_rows(output, expected_count=1)
        values = _normalize(rows[0]) if self.normalize_embeddings else rows[0]
        if not values:
            raise EmbeddingModelError("BGE-M3 query vector is empty")
        if not all(math.isfinite(value) for value in values):
            raise EmbeddingModelError("BGE-M3 query vector values must be finite")
        return values

    def _get_encoder(self) -> DenseEncoder:
        """Return an injected encoder or lazily construct BGE-M3."""
        if self._encoder is not None:
            if self._device_effective is None:
                self._device_effective = (
                    "injected" if self.device_requested == "auto" else self.device_requested
                )
            return self._encoder

        factory = self._model_factory or _load_flag_embedding_factory()
        device = _resolve_device(self.device_requested)
        kwargs: dict[str, object] = {
            "normalize_embeddings": self.normalize_embeddings,
            "use_fp16": device == "cuda",
            "devices": [device],
        }
        if self.model_revision is not None:
            kwargs["revision"] = self.model_revision

        try:
            self._encoder = factory(self.model_name, **kwargs)
        except Exception as exc:
            raise EmbeddingModelError(
                f"failed to load BGE-M3 model {self.model_name!r} on {device}: {exc}"
            ) from exc
        self._device_effective = device
        return self._encoder


def _load_flag_embedding_factory() -> ModelFactory:
    """Import the optional FlagEmbedding BGE-M3 factory lazily."""
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError as exc:
        raise EmbeddingModelError(
            "FlagEmbedding is required for the BGE-M3 pilot. "
            "Install the project embedding extra with: uv sync --extra embedding"
        ) from exc
    return BGEM3FlagModel


def _resolve_device(requested: str) -> str:
    """Resolve ``auto`` and validate explicit CUDA availability."""
    if requested == "cpu":
        return "cpu"

    try:
        import torch
    except ImportError as exc:
        raise EmbeddingModelError(
            "PyTorch is required by FlagEmbedding but is not installed"
        ) from exc

    cuda_available = bool(torch.cuda.is_available())
    if requested == "cuda":
        if not cuda_available:
            raise EmbeddingModelError("CUDA was requested but torch.cuda.is_available() is false")
        return "cuda"
    return "cuda" if cuda_available else "cpu"


def _extract_dense_rows(output: object, *, expected_count: int) -> list[list[float]]:
    """Extract dense rows from supported FlagEmbedding output shapes."""
    dense_output = output
    if isinstance(output, Mapping):
        if "dense_vecs" not in output:
            raise EmbeddingModelError("BGE-M3 output dictionary is missing 'dense_vecs'")
        dense_output = output["dense_vecs"]

    if hasattr(dense_output, "tolist"):
        dense_output = dense_output.tolist()
    if not _is_sequence(dense_output):
        raise EmbeddingModelError("BGE-M3 dense output must be a sequence or array")

    items = list(dense_output)
    if expected_count == 1 and items and all(_is_number(value) for value in items):
        items = [items]
    if len(items) != expected_count:
        raise EmbeddingModelError(
            f"dense output count mismatch: expected {expected_count}, received {len(items)}"
        )

    rows: list[list[float]] = []
    for index, row in enumerate(items):
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not _is_sequence(row):
            raise EmbeddingModelError(f"dense vector at output index {index} is not a sequence")
        try:
            rows.append([float(value) for value in row])
        except (TypeError, ValueError) as exc:
            raise EmbeddingModelError(
                f"dense vector at output index {index} contains non-numeric values"
            ) from exc
    return rows


def _normalize(values: list[float]) -> list[float]:
    """Return an L2-normalized copy while preserving invalid values for validation."""
    if not all(math.isfinite(value) for value in values):
        return values
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return values
    return [value / norm for value in values]


def _is_sequence(value: object) -> bool:
    """Return whether a value is a non-string sequence."""
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_number(value: object) -> bool:
    """Return whether a value can safely be treated as a scalar number."""
    return isinstance(value, int | float)
