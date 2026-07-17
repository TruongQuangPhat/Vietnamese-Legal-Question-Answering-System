"""Unit tests for coverage-aware dense fallback behavior."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.retrieval.coverage_aware import CoverageAwareFusionConfig, CoverageAwareQuotaRetriever
from src.retrieval.dense_retriever import QueryEmbeddingTimeoutError
from src.retrieval.models import RetrievalResult, RetrievedChunk


class StaticCandidateRetriever:
    """Return configured candidates and record requested depths."""

    def __init__(
        self,
        result: RetrievalResult | None = None,
        *,
        error: BaseException | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.result = result or _retrieval_result([], "dense")
        self.error = error
        self.delay_seconds = delay_seconds
        self.calls: list[dict[str, Any]] = []

    async def retrieve(self, query: str, *, top_k: int) -> RetrievalResult:
        self.calls.append({"query": query, "top_k": top_k})
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return self.result.model_copy(update={"query": query, "top_k": top_k})


@pytest.mark.asyncio
async def test_sparse_fallback_attempted_when_dense_times_out_and_enabled() -> None:
    dense = StaticCandidateRetriever(error=QueryEmbeddingTimeoutError(timeout_seconds=1.0))
    sparse = StaticCandidateRetriever(_retrieval_result([_chunk()], "sparse_bm25"))
    retriever = _coverage_retriever(
        dense,
        sparse,
        dense_fallback_enabled=True,
        dense_fallback_timeout_seconds=1.0,
    )

    result = await retriever.retrieve(query="Hợp đồng dân sự vô hiệu khi nào?")

    assert result.vector_name == "sparse_bm25_fallback"
    assert result.query_vector_dimension == 0
    assert result.results[0].chunk_id == "chunk-1"
    assert [issue.code for issue in result.issues] == ["query_embedding_timeout"]
    assert dense.calls == [{"query": "Hợp đồng dân sự vô hiệu khi nào?", "top_k": 50}]
    assert sparse.calls == [{"query": "Hợp đồng dân sự vô hiệu khi nào?", "top_k": 10}]


@pytest.mark.asyncio
async def test_sparse_fallback_not_attempted_when_disabled() -> None:
    dense = StaticCandidateRetriever(error=QueryEmbeddingTimeoutError(timeout_seconds=1.0))
    sparse = StaticCandidateRetriever(_retrieval_result([_chunk()], "sparse_bm25"))
    retriever = _coverage_retriever(dense, sparse, dense_fallback_enabled=False)

    with pytest.raises(QueryEmbeddingTimeoutError):
        await retriever.retrieve(query="Hợp đồng dân sự vô hiệu khi nào?")

    assert sparse.calls == []


@pytest.mark.asyncio
async def test_sparse_fallback_is_bounded_by_timeout() -> None:
    dense = StaticCandidateRetriever(error=QueryEmbeddingTimeoutError(timeout_seconds=1.0))
    sparse = StaticCandidateRetriever(
        _retrieval_result([_chunk()], "sparse_bm25"),
        delay_seconds=0.05,
    )
    retriever = _coverage_retriever(
        dense,
        sparse,
        dense_fallback_enabled=True,
        dense_fallback_timeout_seconds=0.001,
    )

    with pytest.raises(RuntimeError, match="sparse fallback timed out"):
        await retriever.retrieve(query="Hợp đồng dân sự vô hiệu khi nào?")


def _coverage_retriever(
    dense: StaticCandidateRetriever,
    sparse: StaticCandidateRetriever,
    *,
    dense_fallback_enabled: bool,
    dense_fallback_timeout_seconds: float = 10.0,
) -> CoverageAwareQuotaRetriever:
    return CoverageAwareQuotaRetriever(
        dense_retriever=dense,
        sparse_retriever=sparse,
        config=CoverageAwareFusionConfig(
            config_id="selected_coverage_aware_quota",
            mode="quota",
            dense_candidate_k=50,
            sparse_candidate_k=50,
            final_top_k=10,
            rrf_k=60,
            dense_weight=1.0,
            sparse_weight=1.5,
            fused_best=5,
            sparse_quota=4,
            dense_quota=1,
        ),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
        dense_fallback_enabled=dense_fallback_enabled,
        dense_fallback_timeout_seconds=dense_fallback_timeout_seconds,
    )


def _retrieval_result(chunks: list[RetrievedChunk], vector_name: str) -> RetrievalResult:
    return RetrievalResult(
        query="Hợp đồng dân sự vô hiệu khi nào?",
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name=vector_name,
        top_k=50,
        elapsed_ms=1.0,
        query_vector_dimension=1024 if vector_name == "dense" else 0,
        results=chunks,
        issues=[],
    )


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        rank=1,
        score=1.0,
        chunk_id="chunk-1",
        law_id="BLDS_2015",
        law_name="Bộ luật Dân sự 2015",
        article_number="123",
        citation="Điều 123 Bộ luật Dân sự 2015",
        text="Giao dịch dân sự vô hiệu khi vi phạm điều cấm của luật.",
        source_url="https://thuvienphapluat.vn/example",
    )
