"""Runtime-aligned deterministic hybrid fixtures for direct-evidence quality."""

from __future__ import annotations

import pytest

from src.evaluation.benchmark.direct_evidence import (
    BenchmarkRuntimeConfig,
    EvidenceTarget,
    provision_summary,
    summary_matches_target,
    target_key,
    target_rank,
)
from src.retrieval.coverage_aware import (
    CoverageAwareFusionConfig,
    CoverageAwareQuotaRetriever,
)
from src.retrieval.evidence import ContextAssemblyConfig, build_evidence_bundle
from src.retrieval.models import RetrievalResult, RetrievedChunk
from src.retrieval.prompting import build_naive_rag_prompt
from src.retrieval.selection import EvidenceSelectionConfig, select_evidence_for_answer

RUNTIME_CONFIG = BenchmarkRuntimeConfig.for_mode("runtime_aligned")


class StaticCandidateRetriever:
    """Async retriever that exercises fusion without Qdrant or embeddings."""

    def __init__(self, results: list[RetrievedChunk], *, vector_name: str) -> None:
        self._results = _pad_to_50(results, vector_name=vector_name)
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
@pytest.mark.parametrize(
    ("case_id", "query", "target", "dense_specs", "sparse_specs"),
    [
        (
            "q1_article_35_direct",
            "Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
            EvidenceTarget("BLLD_VBHN", "35"),
            [
                ("labor-35-clause-1", 7, "BLLD_VBHN", "35", "1", None),
                ("labor-36-clause-1", 1, "BLLD_VBHN", "36", "1", None),
            ],
            [
                ("labor-35-clause-1", 7, "BLLD_VBHN", "35", "1", None),
                ("labor-34-clause-9", 1, "BLLD_VBHN", "34", "9", None),
            ],
        ),
        (
            "q4_article_35_notice_period",
            "Người lao động phải báo trước bao lâu khi đơn phương chấm dứt hợp đồng?",
            EvidenceTarget("BLLD_VBHN", "35", "1"),
            [
                ("labor-35-clause-1", 4, "BLLD_VBHN", "35", "1", None),
                ("labor-36-clause-1", 1, "BLLD_VBHN", "36", "1", None),
            ],
            [
                ("labor-35-clause-1", 4, "BLLD_VBHN", "35", "1", None),
                ("labor-39", 1, "BLLD_VBHN", "39", None, None),
            ],
        ),
        (
            "q5_article_35_no_notice",
            "Người lao động có được nghỉ việc không cần báo trước trong trường hợp nào?",
            EvidenceTarget("BLLD_VBHN", "35", "2"),
            [
                ("labor-35-clause-2", 6, "BLLD_VBHN", "35", "2", None),
                ("labor-36-clause-1", 1, "BLLD_VBHN", "36", "1", None),
            ],
            [
                ("labor-35-clause-2", 6, "BLLD_VBHN", "35", "2", None),
                ("labor-34-clause-9", 1, "BLLD_VBHN", "34", "9", None),
            ],
        ),
        (
            "annual_leave_article_113",
            "Người lao động nghỉ hằng năm theo Khoản 1 Điều 113 được bao nhiêu ngày?",
            EvidenceTarget("BLLD_VBHN", "113", "1"),
            [
                ("annual-direct", 1, "BLLD_VBHN", "113", "1", None),
            ],
            [
                ("seniority-overlap", 1, "BLLD_VBHN", "114", None, None),
                ("annual-direct", 2, "BLLD_VBHN", "113", "1", None),
            ],
        ),
        (
            "marriage_condition_article_8_point_a",
            "Điểm a khoản 1 Điều 8 Luật Hôn nhân và gia đình quy định độ tuổi kết hôn thế nào?",
            EvidenceTarget("LHNGD_VBHN", "8", "1", "a"),
            [
                ("marriage-age", 2, "LHNGD_VBHN", "8", "1", "a"),
            ],
            [
                ("marriage-prohibition", 1, "LHNGD_VBHN", "5", "2", None),
                ("marriage-age", 2, "LHNGD_VBHN", "8", "1", "a"),
            ],
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
async def test_hybrid_runtime_aligned_direct_primary_cases(
    case_id: str,
    query: str,
    target: EvidenceTarget,
    dense_specs: list[tuple[str, int, str, str, str | None, str | None]],
    sparse_specs: list[tuple[str, int, str, str, str | None, str | None]],
) -> None:
    """Direct expected target is primary after 50+50 -> fused 10 -> selected 5."""
    diagnostics = await _run_hybrid_diagnostics(
        case_id,
        query=query,
        dense_results=_chunks_from_specs(dense_specs),
        sparse_results=_chunks_from_specs(sparse_specs),
        expected_targets=[target],
    )

    assert diagnostics["fused_rank"][target_key(target)] is not None, diagnostics
    assert diagnostics["fused_rank"][target_key(target)] <= 10, diagnostics
    assert summary_matches_target(diagnostics["selected_evidence"][0], target), diagnostics
    assert summary_matches_target(diagnostics["citations"][0], target), diagnostics


@pytest.mark.asyncio
async def test_hybrid_runtime_aligned_multi_article_targets_remain_selected_and_cited() -> None:
    """Multi-article coverage survives the production fused top-10 boundary."""
    weekly = EvidenceTarget("BLLD_VBHN", "111", "1")
    annual = EvidenceTarget("BLLD_VBHN", "113", "1")
    diagnostics = await _run_hybrid_diagnostics(
        "weekly_and_annual_leave_multi_article",
        query="Khoản 1 Điều 111 và Khoản 1 Điều 113 quy định nghỉ hằng tuần, hằng năm thế nào?",
        dense_results=[
            _chunk("annual-direct", rank=1, law_id="BLLD_VBHN", article="113", clause="1")
        ],
        sparse_results=[
            _chunk("weekly-direct", rank=1, law_id="BLLD_VBHN", article="111", clause="1"),
            _chunk("annual-direct", rank=2, law_id="BLLD_VBHN", article="113", clause="1"),
        ],
        expected_targets=[weekly, annual],
    )

    for target in (weekly, annual):
        assert any(
            summary_matches_target(item, target) for item in diagnostics["selected_evidence"]
        ), diagnostics
        assert any(summary_matches_target(item, target) for item in diagnostics["citations"]), (
            diagnostics
        )
    assert diagnostics["multi_article_coverage_pass"] is True, diagnostics


@pytest.mark.asyncio
async def test_hybrid_runtime_aligned_adversarial_cases_expose_diagnostics() -> None:
    """Adversarial lexical, actor, domain, negation, and cross-reference cases pass."""
    cases = [
        (
            "semantic_relevance_vs_lexical_overlap",
            "Khoản 1 Điều 113 quy định người lao động nghỉ hằng năm được bao nhiêu ngày?",
            EvidenceTarget("BLLD_VBHN", "113", "1"),
            [_chunk("annual-direct", rank=1, law_id="BLLD_VBHN", article="113", clause="1")],
            [
                _chunk("lexical-wrong", rank=1, law_id="BLLD_VBHN", article="114", clause=None),
                _chunk("annual-direct", rank=2, law_id="BLLD_VBHN", article="113", clause="1"),
            ],
        ),
        (
            "wrong_actor",
            "Người lao động đơn phương chấm dứt hợp đồng trong trường hợp nào?",
            EvidenceTarget("BLLD_VBHN", "35", "1"),
            [_chunk("labor-35-clause-1", rank=2, law_id="BLLD_VBHN", article="35", clause="1")],
            [
                _chunk("labor-36-clause-1", rank=1, law_id="BLLD_VBHN", article="36", clause="1"),
                _chunk("labor-35-clause-1", rank=2, law_id="BLLD_VBHN", article="35", clause="1"),
            ],
        ),
        (
            "wrong_domain",
            "Theo Bộ luật Lao động, người lao động có quyền gì khi đơn phương chấm dứt hợp đồng?",
            EvidenceTarget("BLLD_VBHN", "35", "1"),
            [_chunk("labor-35-clause-1", rank=1, law_id="BLLD_VBHN", article="35", clause="1")],
            [
                _chunk("civil-35", rank=1, law_id="BLDS_2015", article="35", clause=None),
                _chunk("labor-35-clause-1", rank=2, law_id="BLLD_VBHN", article="35", clause="1"),
            ],
        ),
        (
            "negation_contradiction",
            "Người lao động không cần báo trước trong trường hợp nào?",
            EvidenceTarget("BLLD_VBHN", "35", "2"),
            [_chunk("labor-35-clause-2", rank=1, law_id="BLLD_VBHN", article="35", clause="2")],
            [
                _chunk("labor-35-clause-1", rank=1, law_id="BLLD_VBHN", article="35", clause="1"),
                _chunk("labor-35-clause-2", rank=2, law_id="BLLD_VBHN", article="35", clause="2"),
            ],
        ),
        (
            "explicit_cross_reference_target",
            "Khoản 5 Điều 36 Luật Công chứng quy định nghĩa vụ mua bảo hiểm thế nào?",
            EvidenceTarget("LCCONGCHUNG_VBHN", "36", "5"),
            [
                _chunk(
                    "insurance-substantive",
                    rank=1,
                    law_id="LCCONGCHUNG_VBHN",
                    article="39",
                    clause="1",
                )
            ],
            [
                _chunk(
                    "notary-reference-target",
                    rank=1,
                    law_id="LCCONGCHUNG_VBHN",
                    article="36",
                    clause="5",
                ),
                _chunk(
                    "insurance-substantive",
                    rank=2,
                    law_id="LCCONGCHUNG_VBHN",
                    article="39",
                    clause="1",
                ),
            ],
        ),
    ]

    for case_id, query, target, dense_results, sparse_results in cases:
        diagnostics = await _run_hybrid_diagnostics(
            case_id,
            query=query,
            dense_results=dense_results,
            sparse_results=sparse_results,
            expected_targets=[target],
        )
        assert diagnostics["direct_primary_pass"] is True, diagnostics


@pytest.mark.asyncio
async def test_hybrid_runtime_aligned_fused_rank_10_is_available_to_selection() -> None:
    """Expected target at fused rank 10 remains available to evidence selection."""
    target = EvidenceTarget("BLLD_VBHN", "35", "2")
    shared = [
        _chunk(f"shared-{index}", rank=index, law_id="OTHER", article=str(index), clause=None)
        for index in range(1, 10)
    ]
    target_chunk = _chunk(
        "labor-35-clause-2",
        rank=10,
        law_id="BLLD_VBHN",
        article="35",
        clause="2",
    )

    diagnostics = await _run_hybrid_diagnostics(
        "fused_rank_10_available",
        query="Khoản 2 Điều 35 quy định trường hợp không cần báo trước thế nào?",
        dense_results=[*shared, target_chunk],
        sparse_results=[*shared, target_chunk],
        expected_targets=[target],
    )

    assert diagnostics["fused_rank"][target_key(target)] == 10, diagnostics
    assert diagnostics["direct_primary_pass"] is True, diagnostics


@pytest.mark.asyncio
async def test_hybrid_runtime_aligned_fused_rank_11_is_unavailable_to_selection() -> None:
    """Expected target pushed outside fused top 10 is treated as unavailable."""
    target = EvidenceTarget("BLLD_VBHN", "35", "2")
    shared = [
        _chunk(f"shared-{index}", rank=index, law_id="OTHER", article=str(index), clause=None)
        for index in range(1, 11)
    ]
    target_chunk = _chunk(
        "labor-35-clause-2",
        rank=11,
        law_id="BLLD_VBHN",
        article="35",
        clause="2",
    )

    diagnostics = await _run_hybrid_diagnostics(
        "fused_rank_11_unavailable",
        query="Khoản 2 Điều 35 quy định trường hợp không cần báo trước thế nào?",
        dense_results=[*shared, target_chunk],
        sparse_results=[*shared, target_chunk],
        expected_targets=[target],
    )

    assert diagnostics["fused_rank"][target_key(target)] is None, diagnostics
    assert diagnostics["direct_primary_pass"] is False, diagnostics


async def _run_hybrid_diagnostics(
    case_id: str,
    *,
    query: str,
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
    expected_targets: list[EvidenceTarget],
) -> dict[str, object]:
    dense = StaticCandidateRetriever(dense_results, vector_name="dense")
    sparse = StaticCandidateRetriever(sparse_results, vector_name="sparse_bm25")
    retriever = CoverageAwareQuotaRetriever(
        dense_retriever=dense,
        sparse_retriever=sparse,
        config=CoverageAwareFusionConfig(
            config_id="selected_coverage_aware_quota",
            mode="quota",
            dense_candidate_k=RUNTIME_CONFIG.dense_retrieval_top_k,
            sparse_candidate_k=RUNTIME_CONFIG.sparse_retrieval_top_k,
            final_top_k=RUNTIME_CONFIG.fusion_output_top_k,
            rrf_k=60,
            dense_weight=1.0,
            sparse_weight=1.5,
            fused_best=5,
            sparse_quota=4,
            dense_quota=1,
        ),
        collection_name="fixture",
        vector_name="dense",
    )
    retrieval = await retriever.retrieve(query=query, top_k=RUNTIME_CONFIG.fusion_output_top_k)
    bundle = build_evidence_bundle(
        retrieval,
        config=ContextAssemblyConfig(max_packets=RUNTIME_CONFIG.selection_input_top_k),
    )
    selection = select_evidence_for_answer(
        bundle,
        config=EvidenceSelectionConfig(
            max_selected_packets=RUNTIME_CONFIG.selected_evidence_budget
        ),
    )
    prompt = build_naive_rag_prompt(query=query, selection_result=selection)
    selected = [
        provision_summary(item.packet, rank=index)
        for index, item in enumerate(selection.selected_evidence, start=1)
    ]
    citations = [
        provision_summary(item, rank=index) for index, item in enumerate(prompt.evidence, start=1)
    ]
    fused_top10 = [provision_summary(item, rank=item.rank) for item in retrieval.results]
    fused_ranks = {
        target_key(target): target_rank(retrieval.results, target) for target in expected_targets
    }
    sparse_ranks = {
        target_key(target): target_rank(sparse._results, target) for target in expected_targets
    }
    dense_ranks = {
        target_key(target): target_rank(dense._results, target) for target in expected_targets
    }
    primary_target = expected_targets[0]
    direct_primary_pass = bool(selected) and summary_matches_target(selected[0], primary_target)
    citation_pass = bool(citations) and summary_matches_target(citations[0], primary_target)
    multi_article_pass = all(
        any(summary_matches_target(item, target) for item in selected)
        and any(summary_matches_target(item, target) for item in citations)
        for target in expected_targets
    )
    return {
        "case_id": case_id,
        "sparse_rank": sparse_ranks,
        "dense_rank": dense_ranks,
        "fused_rank": fused_ranks,
        "fused_top10": fused_top10,
        "selected_evidence": selected,
        "citations": citations,
        "direct_primary_pass": direct_primary_pass,
        "citation_alignment_pass": citation_pass,
        "multi_article_coverage_pass": multi_article_pass,
        "pass_reason": "pass"
        if direct_primary_pass and citation_pass and multi_article_pass
        else "target unavailable or primary/citation mismatch",
    }


def _pad_to_50(results: list[RetrievedChunk], *, vector_name: str) -> list[RetrievedChunk]:
    by_rank = {item.rank: item for item in results}
    padded = []
    for rank in range(1, 51):
        padded.append(
            by_rank.get(
                rank,
                _chunk(
                    f"{vector_name}-distractor-{rank}",
                    rank=rank,
                    law_id="OTHER",
                    article=str(900 + rank),
                    clause=None,
                ),
            )
        )
    return padded


def _chunks_from_specs(
    specs: list[tuple[str, int, str, str, str | None, str | None]],
) -> list[RetrievedChunk]:
    return [
        _chunk(chunk_id, rank=rank, law_id=law_id, article=article, clause=clause, point=point)
        for chunk_id, rank, law_id, article, clause, point in specs
    ]


def _chunk(
    chunk_id: str,
    *,
    rank: int,
    law_id: str,
    article: str,
    clause: str | None,
    point: str | None = None,
) -> RetrievedChunk:
    text = _fixture_text(law_id=law_id, article=article, clause=clause, point=point)
    return RetrievedChunk(
        rank=rank,
        score=1.0 / rank,
        chunk_id=chunk_id,
        law_id=law_id,
        law_name=_law_name(law_id),
        level="point" if point else "clause",
        chunk_kind="point_level" if point else "clause_level",
        article_number=article,
        clause_number=clause,
        point_label=point,
        citation=_citation(law_id=law_id, article=article, clause=clause, point=point),
        hierarchy_path=f"{_law_name(law_id)} / Điều {article}",
        text=text,
        parent_text=f"Điều {article}. Tiêu đề kiểm thử. {text}",
        source_url=f"https://thuvienphapluat.vn/{law_id}/{article}",
        source_domain="thuvienphapluat.vn",
        metadata={"source": "hybrid_fixture"},
    )


def _fixture_text(
    *,
    law_id: str,
    article: str,
    clause: str | None,
    point: str | None,
) -> str:
    if law_id == "BLLD_VBHN" and article == "35" and clause == "1":
        return (
            "1. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước."
        )
    if law_id == "BLLD_VBHN" and article == "35" and clause == "2":
        return (
            "2. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước."
        )
    if law_id == "BLLD_VBHN" and article == "36":
        return "1. Người sử dụng lao động có quyền đơn phương chấm dứt hợp đồng lao động."
    if law_id == "BLLD_VBHN" and article == "34":
        return "9. Người lao động đơn phương chấm dứt hợp đồng theo quy định tại Điều 35."
    if law_id == "BLLD_VBHN" and article == "39":
        return "Đơn phương chấm dứt hợp đồng lao động trái pháp luật là không đúng quy định."
    if law_id == "BLLD_VBHN" and article == "111":
        return "1. Mỗi tuần, người lao động được nghỉ ít nhất 24 giờ liên tục."
    if law_id == "BLLD_VBHN" and article == "113":
        return "1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm 12 ngày."
    if law_id == "BLLD_VBHN" and article == "114":
        return "Cứ đủ 05 năm làm việc thì số ngày nghỉ hằng năm tăng thêm 01 ngày."
    if law_id == "LHNGD_VBHN" and article == "8":
        return "a) Nam từ đủ 20 tuổi trở lên, nữ từ đủ 18 tuổi trở lên."
    if law_id == "LHNGD_VBHN" and article == "5":
        return "b) Cấm tảo hôn, cưỡng ép kết hôn, lừa dối kết hôn."
    if law_id == "LCCONGCHUNG_VBHN" and article == "36":
        return (
            "5. Mua bảo hiểm trách nhiệm nghề nghiệp cho công chứng viên theo quy định tại Điều 39."
        )
    if law_id == "LCCONGCHUNG_VBHN" and article == "39":
        return "1. Bảo hiểm trách nhiệm nghề nghiệp của công chứng viên được mua hằng năm."
    return f"Quy định kiểm thử Điều {article} không trực tiếp trả lời câu hỏi."


def _law_name(law_id: str) -> str:
    return {
        "BLLD_VBHN": "Bộ luật Lao động",
        "LHNGD_VBHN": "Luật Hôn nhân và gia đình",
        "LCCONGCHUNG_VBHN": "Luật Công chứng",
        "BLDS_2015": "Bộ luật Dân sự",
    }.get(law_id, "Luật kiểm thử")


def _citation(
    *,
    law_id: str,
    article: str,
    clause: str | None,
    point: str | None,
) -> str:
    parts = [_law_name(law_id), f"Điều {article}"]
    if clause:
        parts.append(f"Khoản {clause}")
    if point:
        parts.append(f"Điểm {point}")
    return ", ".join(parts)
