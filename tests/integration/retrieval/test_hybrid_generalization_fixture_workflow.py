"""Deterministic hybrid fixtures for direct-evidence quality failure modes."""

from __future__ import annotations

import pytest

from src.retrieval.coverage_aware import (
    CoverageAwareFusionConfig,
    CoverageAwareQuotaRetriever,
)
from src.retrieval.evidence import ContextAssemblyConfig, build_evidence_bundle
from src.retrieval.models import RetrievalResult, RetrievedChunk
from src.retrieval.prompting import build_naive_rag_prompt
from src.retrieval.selection import select_evidence_for_answer


class StaticCandidateRetriever:
    """Small async retriever used to exercise fusion without Qdrant writes."""

    def __init__(self, results: list[RetrievedChunk], *, vector_name: str) -> None:
        self._results = results
        self._vector_name = vector_name

    async def retrieve(self, query: str, *, top_k: int) -> RetrievalResult:
        """Return bounded in-memory candidates."""
        return RetrievalResult(
            query=query,
            collection_name="fixture",
            vector_name=self._vector_name,
            top_k=top_k,
            elapsed_ms=0.0,
            query_vector_dimension=1024 if self._vector_name == "dense" else 0,
            results=self._results[:top_k],
            issues=[],
        )


@pytest.mark.asyncio
async def test_hybrid_fixture_semantic_dense_candidate_outranks_related_leave_article() -> None:
    """Dense direct Article 113 evidence must beat sparse seniority leave overlap."""
    query = "Người lao động nghỉ hằng năm theo Khoản 1 Điều 113 được bao nhiêu ngày?"
    dense = StaticCandidateRetriever(
        [
            _chunk(
                "annual-direct",
                rank=1,
                law_id="BLLD_VBHN",
                article="113",
                clause="1",
                text="1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm 12 ngày.",
            )
        ],
        vector_name="dense",
    )
    sparse = StaticCandidateRetriever(
        [
            _chunk(
                "seniority-overlap",
                rank=1,
                law_id="BLLD_VBHN",
                article="114",
                clause=None,
                text="Cứ đủ 05 năm làm việc thì số ngày nghỉ hằng năm tăng thêm 01 ngày.",
            ),
            _chunk(
                "annual-direct",
                rank=2,
                law_id="BLLD_VBHN",
                article="113",
                clause="1",
                text="1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm 12 ngày.",
            ),
        ],
        vector_name="sparse_bm25",
    )

    prompt = await _run_hybrid_prompt(query, dense=dense, sparse=sparse)

    assert prompt.evidence[0].law_id == "BLLD_VBHN"
    assert prompt.evidence[0].article_number == "113"
    assert prompt.evidence[0].clause_number == "1"


@pytest.mark.asyncio
async def test_hybrid_fixture_multi_article_targets_remain_selected_and_cited() -> None:
    """Hybrid quota and selection must not collapse a valid multi-article query."""
    query = "Khoản 1 Điều 111 và Khoản 1 Điều 113 quy định nghỉ hằng tuần, hằng năm thế nào?"
    dense = StaticCandidateRetriever(
        [
            _chunk(
                "annual-direct",
                rank=1,
                law_id="BLLD_VBHN",
                article="113",
                clause="1",
                text="1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm 12 ngày.",
            )
        ],
        vector_name="dense",
    )
    sparse = StaticCandidateRetriever(
        [
            _chunk(
                "weekly-direct",
                rank=1,
                law_id="BLLD_VBHN",
                article="111",
                clause="1",
                text="1. Mỗi tuần, người lao động được nghỉ ít nhất 24 giờ liên tục.",
            ),
            _chunk(
                "annual-direct",
                rank=2,
                law_id="BLLD_VBHN",
                article="113",
                clause="1",
                text="1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm 12 ngày.",
            ),
        ],
        vector_name="sparse_bm25",
    )

    prompt = await _run_hybrid_prompt(query, dense=dense, sparse=sparse)
    cited = {(item.law_id, item.article_number, item.clause_number) for item in prompt.evidence}

    assert ("BLLD_VBHN", "111", "1") in cited
    assert ("BLLD_VBHN", "113", "1") in cited


@pytest.mark.asyncio
async def test_hybrid_fixture_explicit_cross_reference_target_remains_primary() -> None:
    """A referring provision may remain primary when the query explicitly names it."""
    query = "Khoản 5 Điều 36 Luật Công chứng quy định nghĩa vụ mua bảo hiểm thế nào?"
    dense = StaticCandidateRetriever(
        [
            _chunk(
                "insurance-substantive",
                rank=1,
                law_id="LCCONGCHUNG_VBHN",
                article="39",
                clause="1",
                text="1. Bảo hiểm trách nhiệm nghề nghiệp của công chứng viên được mua hằng năm.",
            )
        ],
        vector_name="dense",
    )
    sparse = StaticCandidateRetriever(
        [
            _chunk(
                "notary-reference-target",
                rank=1,
                law_id="LCCONGCHUNG_VBHN",
                article="36",
                clause="5",
                text="5. Mua bảo hiểm trách nhiệm nghề nghiệp cho công chứng viên theo quy định tại Điều 39.",
            ),
            _chunk(
                "insurance-substantive",
                rank=2,
                law_id="LCCONGCHUNG_VBHN",
                article="39",
                clause="1",
                text="1. Bảo hiểm trách nhiệm nghề nghiệp của công chứng viên được mua hằng năm.",
            ),
        ],
        vector_name="sparse_bm25",
    )

    prompt = await _run_hybrid_prompt(query, dense=dense, sparse=sparse)

    assert prompt.evidence[0].law_id == "LCCONGCHUNG_VBHN"
    assert prompt.evidence[0].article_number == "36"
    assert prompt.evidence[0].clause_number == "5"


async def _run_hybrid_prompt(
    query: str,
    *,
    dense: StaticCandidateRetriever,
    sparse: StaticCandidateRetriever,
) -> object:
    retriever = CoverageAwareQuotaRetriever(
        dense_retriever=dense,
        sparse_retriever=sparse,
        config=CoverageAwareFusionConfig(
            config_id="selected_coverage_aware_quota",
            mode="quota",
            dense_candidate_k=50,
            sparse_candidate_k=50,
            final_top_k=5,
            rrf_k=60,
            dense_weight=1.0,
            sparse_weight=1.5,
            fused_best=2,
            sparse_quota=2,
            dense_quota=1,
        ),
        collection_name="fixture",
        vector_name="dense",
    )
    retrieval = await retriever.retrieve(query=query, top_k=5)
    bundle = build_evidence_bundle(retrieval, config=ContextAssemblyConfig(max_packets=5))
    selection = select_evidence_for_answer(bundle)
    return build_naive_rag_prompt(query=query, selection_result=selection)


def _chunk(
    chunk_id: str,
    *,
    rank: int,
    law_id: str,
    article: str,
    clause: str | None,
    text: str,
) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=1.0 / rank,
        chunk_id=chunk_id,
        law_id=law_id,
        law_name="Luật kiểm thử",
        level="clause",
        chunk_kind="clause_level",
        article_number=article,
        clause_number=clause,
        citation=f"Luật kiểm thử, Điều {article}" + (f", Khoản {clause}" if clause else ""),
        hierarchy_path=f"Luật kiểm thử / Điều {article}",
        text=text,
        parent_text=f"Điều {article}. Tiêu đề kiểm thử. {text}",
        source_url=f"https://thuvienphapluat.vn/{law_id}/{article}",
        source_domain="thuvienphapluat.vn",
        metadata={"source": "hybrid_fixture"},
    )
