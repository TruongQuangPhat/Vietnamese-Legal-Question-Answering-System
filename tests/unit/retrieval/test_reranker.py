"""Unit tests for deterministic reranking utilities."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.retrieval.models import RetrievedChunk
from src.retrieval.reranker import (
    FlagEmbeddingReranker,
    NativeTransformersReranker,
    RerankerError,
    deduplicate_candidates,
    min_max_normalize,
    rerank_candidates,
)


class _NoGrad:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class _FakeCuda:
    @staticmethod
    def is_available() -> bool:
        return False


class _FakeTorch:
    cuda = _FakeCuda()

    @staticmethod
    def no_grad() -> _NoGrad:
        return _NoGrad()


class _FakeVector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def detach(self) -> _FakeVector:
        return self

    def cpu(self) -> _FakeVector:
        return self

    def tolist(self) -> list[float]:
        return self._values


class _FakeLogits:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows
        self.shape = (len(rows), len(rows[0]) if rows else 0)

    def __getitem__(self, key: tuple[slice, int]) -> _FakeVector:
        _, column = key
        return _FakeVector([row[column] for row in self._rows])


class _FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        queries: list[str],
        documents: list[str],
        **kwargs: Any,
    ) -> dict[str, int]:
        self.calls.append({"queries": queries, "documents": documents, **kwargs})
        return {"batch_size": len(queries)}


class _FakeModel:
    def __init__(self, *, two_logits: bool = False) -> None:
        self.two_logits = two_logits
        self.device: str | None = None
        self.eval_called = False

    def to(self, device: str) -> _FakeModel:
        self.device = device
        return self

    def eval(self) -> _FakeModel:
        self.eval_called = True
        return self

    def __call__(self, *, batch_size: int) -> SimpleNamespace:
        rows = (
            [[-float(index), float(index)] for index in range(1, batch_size + 1)]
            if self.two_logits
            else [[float(index)] for index in range(1, batch_size + 1)]
        )
        return SimpleNamespace(logits=_FakeLogits(rows))


class DeterministicMockReranker:
    """Small query-document scorer used without a real model."""

    model_name = "deterministic-mock"

    def score(self, query: str, candidates: Sequence[RetrievedChunk]) -> list[float]:
        """Score by text length and preserve input cardinality."""
        return [float(len(candidate.text or "")) for candidate in candidates]


def _candidate(
    chunk_id: str,
    *,
    rank: int,
    fused_score: float,
    dense_rank: int | None = None,
    sparse_rank: int | None = None,
    text: str = "legal text",
    metadata: dict[str, object] | None = None,
) -> RetrievedChunk:
    fusion = {
        "fused_score": fused_score,
        "dense_rank": dense_rank,
        "sparse_rank": sparse_rank,
    }
    return RetrievedChunk(
        rank=rank,
        score=fused_score,
        chunk_id=chunk_id,
        text=text,
        metadata={"fusion": fusion, **(metadata or {})},
    )


def test_mock_reranker_interface_is_deterministic() -> None:
    reranker = DeterministicMockReranker()
    candidates = [
        _candidate("a", rank=1, fused_score=0.2, text="a"),
        _candidate("b", rank=2, fused_score=0.1, text="bbbb"),
    ]

    assert reranker.score("query", candidates) == [1.0, 4.0]
    assert reranker.score("query", candidates) == [1.0, 4.0]


def test_empty_candidate_pool_is_safe() -> None:
    assert DeterministicMockReranker().score("query", []) == []
    assert (
        rerank_candidates(
            candidates=[],
            reranker_scores=[],
            final_top_k=10,
            reranker_weight=1.0,
            base_weight=0.0,
            model_name="mock",
        )
        == []
    )


def test_candidate_deduplication_preserves_first_rank() -> None:
    candidates = [
        _candidate("same", rank=1, fused_score=0.3),
        _candidate("same", rank=2, fused_score=0.2),
        _candidate("other", rank=3, fused_score=0.1),
    ]

    deduplicated = deduplicate_candidates(candidates)

    assert [candidate.chunk_id for candidate in deduplicated] == ["same", "other"]
    assert deduplicated[0].rank == 1


def test_min_max_normalization_handles_equal_and_missing_scores() -> None:
    assert min_max_normalize([1.0, 2.0, 3.0]) == pytest.approx([0.0, 0.5, 1.0])
    assert min_max_normalize([2.0, 2.0, None]) == [1.0, 1.0, 0.0]
    assert min_max_normalize([None, None]) == [0.0, 0.0]


def test_mixed_reranker_and_base_scoring() -> None:
    candidates = [
        _candidate("base_top", rank=1, fused_score=3.0),
        _candidate("reranker_top", rank=2, fused_score=1.0),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[0.0, 10.0],
        final_top_k=2,
        reranker_weight=0.7,
        base_weight=0.3,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["reranker_top", "base_top"]
    assert reranked[0].metadata["reranking"]["final_score"] == pytest.approx(0.7)
    assert reranked[1].metadata["reranking"]["final_score"] == pytest.approx(0.3)


def test_tie_breaking_uses_reranker_base_source_ranks_and_chunk_id() -> None:
    candidates = [
        _candidate("b", rank=1, fused_score=1.0, dense_rank=2, sparse_rank=1),
        _candidate("a", rank=2, fused_score=1.0, dense_rank=1, sparse_rank=2),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[1.0, 1.0],
        final_top_k=2,
        reranker_weight=1.0,
        base_weight=0.0,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["a", "b"]


def test_candidate_pool_can_be_larger_than_final_top_k() -> None:
    candidates = [
        _candidate(f"chunk_{index}", rank=index, fused_score=float(10 - index))
        for index in range(1, 6)
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[1.0, 2.0, 3.0, 4.0, 5.0],
        final_top_k=2,
        reranker_weight=1.0,
        base_weight=0.0,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["chunk_5", "chunk_4"]


def test_quota_preserving_rerank_keeps_sparse_and_dense_origins() -> None:
    candidates = [
        _candidate("shared", rank=1, fused_score=5.0, dense_rank=1, sparse_rank=1),
        _candidate("dense_only", rank=2, fused_score=4.0, dense_rank=2),
        _candidate("sparse_2", rank=3, fused_score=3.0, sparse_rank=2),
        _candidate("sparse_3", rank=4, fused_score=2.0, sparse_rank=3),
        _candidate("sparse_4", rank=5, fused_score=1.0, sparse_rank=4),
        _candidate("neither", rank=6, fused_score=0.5),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[6.0, 5.0, 1.0, 2.0, 3.0, 4.0],
        final_top_k=5,
        reranker_weight=1.0,
        base_weight=0.0,
        preserve_source_quota=True,
        sparse_quota=4,
        dense_quota=1,
        model_name="mock",
    )

    sparse_count = sum(
        candidate.metadata["fusion"]["sparse_rank"] is not None for candidate in reranked
    )
    dense_count = sum(
        candidate.metadata["fusion"]["dense_rank"] is not None for candidate in reranked
    )
    assert sparse_count >= 4
    assert dense_count >= 1


def test_gold_metadata_does_not_change_ranking() -> None:
    candidates = [
        _candidate(
            "first",
            rank=1,
            fused_score=2.0,
            metadata={"relevance": "irrelevant", "evidence_group_ids": []},
        ),
        _candidate(
            "second",
            rank=2,
            fused_score=1.0,
            metadata={"relevance": "required_direct", "evidence_group_ids": ["gold"]},
        ),
    ]

    reranked = rerank_candidates(
        candidates=candidates,
        reranker_scores=[2.0, 1.0],
        final_top_k=2,
        reranker_weight=1.0,
        base_weight=0.0,
        model_name="mock",
    )

    assert [candidate.chunk_id for candidate in reranked] == ["first", "second"]


def test_score_count_mismatch_is_rejected() -> None:
    with pytest.raises(RerankerError, match="score count"):
        rerank_candidates(
            candidates=[_candidate("a", rank=1, fused_score=1.0)],
            reranker_scores=[],
            final_top_k=1,
            reranker_weight=1.0,
            base_weight=0.0,
            model_name="mock",
        )


def test_native_reranker_loads_local_only_and_returns_one_finite_score_per_candidate(
    tmp_path: Path,
) -> None:
    tokenizer = _FakeTokenizer()
    model = _FakeModel(two_logits=True)
    tokenizer_load: dict[str, Any] = {}
    model_load: dict[str, Any] = {}

    def load_tokenizer(path: str, **kwargs: Any) -> _FakeTokenizer:
        tokenizer_load.update({"path": path, **kwargs})
        return tokenizer

    def load_model(path: str, **kwargs: Any) -> _FakeModel:
        model_load.update({"path": path, **kwargs})
        return model

    reranker = NativeTransformersReranker(
        model_name="local-test-model",
        model_path=tmp_path,
        device="cpu",
        batch_size=2,
        max_length=128,
        tokenizer_factory=load_tokenizer,
        model_factory=load_model,
        torch_module=_FakeTorch(),
    )
    scores = reranker.score(
        "legal query",
        [
            _candidate("a", rank=1, fused_score=0.2),
            _candidate("b", rank=2, fused_score=0.1),
        ],
    )

    assert tokenizer_load["local_files_only"] is True
    assert model_load["local_files_only"] is True
    assert model.device == "cpu"
    assert model.eval_called is True
    assert scores == [1.0, 2.0]
    assert all(math.isfinite(score) for score in scores)
    assert tokenizer.calls[0]["max_length"] == 128


def test_native_reranker_empty_candidates_skip_tokenization(tmp_path: Path) -> None:
    tokenizer = _FakeTokenizer()
    reranker = NativeTransformersReranker(
        model_name="local-test-model",
        model_path=tmp_path,
        tokenizer_factory=lambda *_args, **_kwargs: tokenizer,
        model_factory=lambda *_args, **_kwargs: _FakeModel(),
        torch_module=_FakeTorch(),
    )

    assert reranker.score("legal query", []) == []
    assert tokenizer.calls == []


def test_flagembedding_failure_does_not_affect_native_path(tmp_path: Path) -> None:
    class BrokenFlagModel:
        def compute_score(self, *_args: Any, **_kwargs: Any) -> list[float]:
            raise AttributeError("prepare_for_model")

    legacy = FlagEmbeddingReranker(
        model_name="legacy",
        model_path=tmp_path,
        factory=lambda *_args, **_kwargs: BrokenFlagModel(),
    )
    with pytest.raises(RerankerError, match="scoring failed"):
        legacy.score(
            "query",
            [_candidate("legacy", rank=1, fused_score=0.1)],
        )

    native = NativeTransformersReranker(
        model_name="native",
        model_path=tmp_path,
        tokenizer_factory=lambda *_args, **_kwargs: _FakeTokenizer(),
        model_factory=lambda *_args, **_kwargs: _FakeModel(),
        torch_module=_FakeTorch(),
    )
    assert native.score(
        "query",
        [_candidate("native", rank=1, fused_score=0.1)],
    ) == [1.0]
