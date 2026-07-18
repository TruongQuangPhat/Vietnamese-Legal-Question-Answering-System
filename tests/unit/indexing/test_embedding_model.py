"""Unit tests for the BGE-M3 wrapper and constrained pilot helpers."""

from __future__ import annotations

import builtins
import math
import time
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from scripts.indexing import pilot_bge_m3_embeddings
from src.indexing.embedding_model import (
    BgeM3EmbeddingModel,
    EmbeddingModelError,
    _load_flag_embedding_factory,
    clear_embedding_model_cache,
    inspect_embedding_model_path,
)
from src.indexing.indexing_models import DenseEmbedding, EmbeddingInput


class FakeEncoder:
    """Small fake implementing the FlagEmbedding encode surface."""

    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def encode(self, sentences: list[str], **kwargs: Any) -> object:
        """Record the request and return configured output."""
        self.calls.append((sentences, kwargs))
        return self.output


class RecordingFactory:
    """Fake factory recording model construction parameters."""

    def __init__(self, encoder: FakeEncoder) -> None:
        self.encoder = encoder
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, model_name: str, **kwargs: Any) -> FakeEncoder:
        """Record construction and return the configured encoder."""
        self.calls.append((model_name, kwargs))
        return self.encoder


class SlowRecordingFactory(RecordingFactory):
    """Fake factory that makes concurrent loading observable."""

    def __init__(self, encoder: FakeEncoder, *, delay_seconds: float) -> None:
        super().__init__(encoder)
        self.delay_seconds = delay_seconds

    def __call__(self, model_name: str, **kwargs: Any) -> FakeEncoder:
        """Delay construction while recording exactly one expected call."""
        time.sleep(self.delay_seconds)
        return super().__call__(model_name, **kwargs)


@pytest.fixture(autouse=True)
def clear_model_cache() -> Iterator[None]:
    """Keep process-global embedding cache isolated between tests."""
    clear_embedding_model_cache()
    yield
    clear_embedding_model_cache()


def _input(chunk_id: str, text: str = "Nội dung pháp luật") -> EmbeddingInput:
    """Build a valid embedding input."""
    return EmbeddingInput(
        chunk_id=chunk_id,
        law_id="LAW_1",
        chunk_kind="clause_level",
        level="clause",
        embedding_text=text,
        text_hash="text-hash",
        parent_text_hash="parent-hash",
        citation="Luật Thử nghiệm, khoản 1 Điều 1",
        hierarchy_path="Luật Thử nghiệm / Điều 1 / Khoản 1",
    )


class TestBgeM3EmbeddingModel:
    """Dense wrapper behavior with injected fake model output."""

    def test_maps_dictionary_dense_output(self) -> None:
        encoder = FakeEncoder({"dense_vecs": [[3.0, 4.0], [0.0, 2.0]]})
        model = BgeM3EmbeddingModel(model_name="BAAI/bge-m3", encoder=encoder)

        embeddings = model.embed_dense([_input("chunk-1"), _input("chunk-2")], batch_size=2)

        assert [item.chunk_id for item in embeddings] == ["chunk-1", "chunk-2"]
        assert all(item.dimension == 2 for item in embeddings)
        assert embeddings[0].values == pytest.approx([0.6, 0.8])
        assert embeddings[1].values == pytest.approx([0.0, 1.0])
        assert encoder.calls[0][0] == ["Nội dung pháp luật", "Nội dung pháp luật"]
        assert encoder.calls[0][1]["return_sparse"] is False
        assert encoder.calls[0][1]["return_colbert_vecs"] is False

    def test_handles_raw_single_vector_output(self) -> None:
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            normalize_embeddings=False,
            encoder=FakeEncoder([1.0, 2.0, 3.0]),
        )

        embeddings = model.embed_dense([_input("chunk-1")], batch_size=1)

        assert embeddings[0].values == [1.0, 2.0, 3.0]
        assert embeddings[0].dimension == 3

    def test_preserves_chunk_id_order(self) -> None:
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            encoder=FakeEncoder([[1.0], [2.0], [3.0]]),
        )
        inputs = [_input("chunk-3"), _input("chunk-1"), _input("chunk-2")]

        embeddings = model.embed_dense(inputs, batch_size=3)

        assert [item.chunk_id for item in embeddings] == ["chunk-3", "chunk-1", "chunk-2"]

    def test_cpu_factory_configuration(self) -> None:
        factory = RecordingFactory(FakeEncoder([[1.0, 0.0]]))
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            model_revision="revision-1",
            device="cpu",
            model_factory=factory,
        )

        model.embed_dense([_input("chunk-1")], batch_size=1)

        assert model.device_effective == "cpu"
        assert factory.calls == [
            (
                "BAAI/bge-m3",
                {
                    "normalize_embeddings": True,
                    "use_fp16": False,
                    "devices": ["cpu"],
                    "revision": "revision-1",
                },
            )
        ]

    def test_local_model_path_is_passed_to_factory_without_revision(
        self,
        tmp_path: Path,
    ) -> None:
        _write_minimal_model_files(tmp_path)
        factory = RecordingFactory(FakeEncoder([[1.0, 0.0]]))
        model = BgeM3EmbeddingModel(
            model_name=str(tmp_path),
            model_revision="revision-ignored-for-local-path",
            device="cpu",
            model_factory=factory,
            require_local_files=True,
        )

        model.ensure_loaded()

        assert factory.calls == [
            (
                str(tmp_path),
                {
                    "normalize_embeddings": True,
                    "use_fp16": False,
                    "devices": ["cpu"],
                },
            )
        ]
        assert model.is_loaded is True
        assert model.model_cache_key.startswith("bge-m3:")

    def test_same_local_model_configuration_shares_process_cache(
        self,
        tmp_path: Path,
    ) -> None:
        _write_minimal_model_files(tmp_path)
        factory = RecordingFactory(FakeEncoder([[1.0, 0.0]]))
        first = BgeM3EmbeddingModel(
            model_name=str(tmp_path),
            device="cpu",
            model_factory=factory,
            require_local_files=True,
        )
        second = BgeM3EmbeddingModel(
            model_name=str(tmp_path),
            device="cpu",
            model_factory=factory,
            require_local_files=True,
        )

        first.ensure_loaded()
        second.ensure_loaded()

        assert len(factory.calls) == 1
        assert first.is_loaded is True
        assert second.is_loaded is True
        assert first.model_cache_key == second.model_cache_key

    def test_concurrent_model_load_waits_on_same_cache_entry(
        self,
        tmp_path: Path,
    ) -> None:
        _write_minimal_model_files(tmp_path)
        factory = SlowRecordingFactory(FakeEncoder([[1.0, 0.0]]), delay_seconds=0.02)
        model = BgeM3EmbeddingModel(
            model_name=str(tmp_path),
            device="cpu",
            model_factory=factory,
            require_local_files=True,
        )
        errors: list[BaseException] = []

        def load_model() -> None:
            try:
                model.ensure_loaded()
            except BaseException as exc:
                errors.append(exc)

        threads = [Thread(target=load_model) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert len(factory.calls) == 1
        assert model.is_loaded is True

    def test_required_local_model_path_fails_before_factory_call(
        self,
        tmp_path: Path,
    ) -> None:
        factory = RecordingFactory(FakeEncoder([[1.0, 0.0]]))
        model = BgeM3EmbeddingModel(
            model_name=str(tmp_path / "missing-model"),
            device="cpu",
            model_factory=factory,
            require_local_files=True,
        )

        with pytest.raises(EmbeddingModelError, match="local BGE-M3 model path"):
            model.ensure_loaded()

        assert factory.calls == []

    def test_inspect_embedding_model_path_reports_required_files(
        self,
        tmp_path: Path,
    ) -> None:
        missing_status = inspect_embedding_model_path(tmp_path / "missing")
        assert missing_status.configured is True
        assert missing_status.exists is False
        assert missing_status.required_files_present is False

        _write_minimal_model_files(tmp_path)
        ready_status = inspect_embedding_model_path(tmp_path)

        assert ready_status.configured is True
        assert ready_status.exists is True
        assert ready_status.required_files_present is True

    def test_rejects_output_count_mismatch(self) -> None:
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            encoder=FakeEncoder([[1.0, 2.0]]),
        )

        with pytest.raises(EmbeddingModelError, match="output count mismatch"):
            model.embed_dense([_input("chunk-1"), _input("chunk-2")], batch_size=2)

    def test_rejects_empty_vector(self) -> None:
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            encoder=FakeEncoder([[]]),
        )

        with pytest.raises(EmbeddingModelError, match="invalid dense vector"):
            model.embed_dense([_input("chunk-1")], batch_size=1)

    def test_rejects_inconsistent_dimensions(self) -> None:
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            encoder=FakeEncoder([[1.0, 2.0], [3.0]]),
        )

        with pytest.raises(EmbeddingModelError, match="dimensions are inconsistent"):
            model.embed_dense([_input("chunk-1"), _input("chunk-2")], batch_size=2)

    @pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite_vector(self, invalid_value: float) -> None:
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            encoder=FakeEncoder([[1.0, invalid_value]]),
        )

        with pytest.raises(EmbeddingModelError, match="invalid dense vector"):
            model.embed_dense([_input("chunk-1")], batch_size=1)

    def test_missing_dense_vecs_key_fails(self) -> None:
        model = BgeM3EmbeddingModel(
            model_name="BAAI/bge-m3",
            encoder=FakeEncoder({"lexical_weights": []}),
        )

        with pytest.raises(EmbeddingModelError, match="missing 'dense_vecs'"):
            model.embed_dense([_input("chunk-1")], batch_size=1)

    def test_missing_optional_dependency_has_clear_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "FlagEmbedding":
                raise ImportError("not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(EmbeddingModelError, match="uv sync --extra embedding"):
            _load_flag_embedding_factory()


class TestPilotHelpers:
    """Fast pilot safety and diagnostics helper tests."""

    def test_rejects_protected_output_path(self) -> None:
        protected = Path("artifacts/reports/indexing/pilot.json")

        with pytest.raises(ValueError, match="refusing protected"):
            pilot_bge_m3_embeddings.validate_pilot_arguments(
                output_path=protected,
                limit=10,
                batch_size=2,
                allow_protected_output=False,
                allow_large_pilot=False,
            )

    @pytest.mark.parametrize("limit", [0, -1, 1001])
    def test_rejects_unsafe_pilot_limit(self, limit: int) -> None:
        with pytest.raises(ValueError, match="pilot limit"):
            pilot_bge_m3_embeddings.validate_pilot_arguments(
                output_path=Path("/tmp/pilot.json"),
                limit=limit,
                batch_size=2,
                allow_protected_output=False,
                allow_large_pilot=False,
            )

    def test_vector_diagnostics(self) -> None:
        embeddings = [
            DenseEmbedding(
                chunk_id="chunk-1",
                values=[1.0, 0.0],
                dimension=2,
                model_name="BAAI/bge-m3",
            ),
            DenseEmbedding(
                chunk_id="chunk-2",
                values=[0.0, 2.0],
                dimension=2,
                model_name="BAAI/bge-m3",
            ),
        ]

        diagnostics = pilot_bge_m3_embeddings.compute_vector_diagnostics(embeddings)

        assert diagnostics["dense_dimension"] == 2
        assert diagnostics["dimensions_observed"] == [2]
        assert diagnostics["vector_count"] == 2
        assert diagnostics["dimension_mismatch_count"] == 0
        assert diagnostics["nan_vector_count"] == 0
        assert diagnostics["inf_vector_count"] == 0
        assert diagnostics["norm_min"] == 1.0
        assert diagnostics["norm_max"] == 2.0
        assert diagnostics["norm_mean"] == 1.5
        assert math.isclose(diagnostics["norm_p95"], 1.95)


def _write_minimal_model_files(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text("{}", encoding="utf-8")
    (path / "pytorch_model.bin").write_bytes(b"placeholder")
    (path / "tokenizer.json").write_text("{}", encoding="utf-8")
