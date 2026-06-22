from __future__ import annotations

import pytest

from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    LegalDomain,
    QuestionType,
    RelevanceLevel,
    ReviewStatus,
)
from src.evaluation.benchmark.loader import LoadedBenchmarkDataset
from src.evaluation.benchmark.retrieval_baseline import (
    aggregate_case_metrics,
    build_benchmark_case_inputs,
    build_breakdowns,
    evaluate_case_retrieval,
)
from src.evaluation.benchmark.schemas import BenchmarkQuery, EvidenceGroup, EvidenceJudgment
from src.retrieval.models import RetrievedChunk


def _query(
    *,
    query_id: str = "q1",
    expected_decision: ExpectedDecision = ExpectedDecision.ANSWER_ALLOWED,
    question_types: list[QuestionType] | None = None,
    complete_evidence_required: bool = False,
    blocking: bool = False,
) -> BenchmarkQuery:
    return BenchmarkQuery(
        id=query_id,
        query="Synthetic Vietnamese legal query?",
        primary_domain=LegalDomain.CIVIL_FAMILY_IDENTITY,
        question_types=question_types or [QuestionType.SINGLE_ARTICLE_LOOKUP],
        expected_decision=expected_decision,
        fallback_reason=None,
        complete_evidence_required=complete_evidence_required,
        blocking=blocking,
        blocking_rationale="Synthetic high-risk fixture." if blocking else None,
        review_status=ReviewStatus.FROZEN,
        reviewer_notes="Synthetic fixture.",
        split=BenchmarkSplit.DEVELOPMENT,
    )


def _fallback_query() -> BenchmarkQuery:
    return BenchmarkQuery.model_validate(
        {
            "id": "fallback_q",
            "query": "Synthetic ambiguous query?",
            "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY,
            "question_types": [QuestionType.FALLBACK, QuestionType.AMBIGUOUS],
            "expected_decision": ExpectedDecision.FALLBACK_REQUIRED,
            "fallback_reason": "unsafe_ambiguity",
            "ambiguity_category": "unsafe_for_answer_generation",
            "review_status": ReviewStatus.FROZEN,
            "reviewer_notes": "Synthetic fallback fixture.",
            "split": BenchmarkSplit.HELD_OUT_TEST,
        }
    )


def _judgment(
    chunk_id: str,
    *,
    query_id: str = "q1",
    relevance: RelevanceLevel = RelevanceLevel.REQUIRED_DIRECT,
    group_ids: list[str] | None = None,
) -> EvidenceJudgment:
    return EvidenceJudgment(
        query_id=query_id,
        chunk_id=chunk_id,
        relevance=relevance,
        evidence_group_ids=group_ids or ["g1"],
    )


def _group(
    *,
    query_id: str = "q1",
    group_id: str = "g1",
    chunk_ids: list[str] | None = None,
) -> EvidenceGroup:
    return EvidenceGroup(
        query_id=query_id,
        evidence_group_id=group_id,
        requirement=EvidenceGroupRequirement.REQUIRED,
        minimum_hits=1,
        acceptable_chunk_ids=chunk_ids or ["chunk_a"],
        acceptable_legal_targets=[
            {
                "law_id": "LAW_A",
                "article_number": "1",
                "match_level": "article",
            }
        ],
    )


def _hit(rank: int, chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=1.0 / rank,
        chunk_id=chunk_id,
        law_id="LAW_A",
        article_number="1",
        text="Synthetic legal text.",
    )


def test_evaluate_case_retrieval_counts_direct_and_group_coverage() -> None:
    case = evaluate_case_retrieval(
        query=_query(complete_evidence_required=True),
        split=BenchmarkSplit.DEVELOPMENT,
        retrieved=[_hit(1, "noise"), _hit(2, "chunk_a")],
        judgments=[_judgment("chunk_a")],
        groups=[_group()],
    )

    assert case["first_direct_rank"] == 2
    assert case["reciprocal_rank_at_10"] == pytest.approx(0.5)
    assert case["cutoffs"]["1"]["direct_hit"] is False
    assert case["cutoffs"]["3"]["direct_hit"] is True
    assert case["cutoffs"]["3"]["required_direct_coverage"] == pytest.approx(1.0)
    assert case["cutoffs"]["3"]["evidence_group_coverage"] == pytest.approx(1.0)


def test_aggregate_metrics_separate_answer_allowed_and_fallback() -> None:
    answer_case = evaluate_case_retrieval(
        query=_query(),
        split=BenchmarkSplit.DEVELOPMENT,
        retrieved=[_hit(1, "chunk_a")],
        judgments=[_judgment("chunk_a")],
        groups=[_group()],
    )
    fallback_case = evaluate_case_retrieval(
        query=_fallback_query(),
        split=BenchmarkSplit.HELD_OUT_TEST,
        retrieved=[_hit(1, "supporting_chunk"), _hit(2, "near_miss_chunk")],
        judgments=[
            _judgment(
                "supporting_chunk",
                query_id="fallback_q",
                relevance=RelevanceLevel.SUPPORTING,
                group_ids=[],
            ),
            _judgment(
                "near_miss_chunk",
                query_id="fallback_q",
                relevance=RelevanceLevel.NEAR_MISS,
                group_ids=[],
            ),
        ],
        groups=[],
    )

    metrics = aggregate_case_metrics([answer_case, fallback_case])

    assert metrics["query_count"] == 2
    assert metrics["answer_allowed_count"] == 1
    assert metrics["fallback_required_count"] == 1
    assert metrics["recall_at_10"] == pytest.approx(1.0)
    assert metrics["fallback_diagnostics"]["supporting_retrieved_at_10"]["count"] == 1
    assert metrics["fallback_diagnostics"]["near_miss_retrieved_at_10"]["count"] == 1
    assert metrics["fallback_diagnostics"]["direct_evidence_retrieved_at_10"]["count"] == 0


def test_breakdowns_include_multivalue_question_types() -> None:
    case = evaluate_case_retrieval(
        query=_query(question_types=[QuestionType.SINGLE_ARTICLE_LOOKUP, QuestionType.PARAPHRASE]),
        split=BenchmarkSplit.DEVELOPMENT,
        retrieved=[_hit(1, "chunk_a")],
        judgments=[_judgment("chunk_a")],
        groups=[_group()],
    )

    breakdowns = build_breakdowns([case])

    assert set(breakdowns["question_types"]) == {"paraphrase", "single_article_lookup"}
    assert breakdowns["split"]["development"]["query_count"] == 1


def test_build_benchmark_case_inputs_indexes_records_by_query() -> None:
    dataset = LoadedBenchmarkDataset(
        queries=[_query()],
        legal_targets=[],
        evidence_judgments=[_judgment("chunk_a")],
        evidence_groups=[_group()],
        review_records=[],
        checked_files=[],
    )

    judgments, groups = build_benchmark_case_inputs(dataset)

    assert judgments["q1"][0].chunk_id == "chunk_a"
    assert groups["q1"][0].evidence_group_id == "g1"
