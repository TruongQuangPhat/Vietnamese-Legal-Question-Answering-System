from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from src.evaluation.benchmark.generation_baseline import (
    aggregate_generation_metrics,
    build_generation_breakdowns,
    evaluate_generation_case,
)
from src.evaluation.benchmark.schemas import BenchmarkQuery, EvidenceGroup, EvidenceJudgment


@dataclass(frozen=True)
class _Evidence:
    evidence_id: str
    chunk_id: str


@dataclass(frozen=True)
class _Issue:
    code: str

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return {"code": self.code}


@dataclass(frozen=True)
class _Result:
    decision: ExpectedDecision
    answer: str
    used_evidence: list[_Evidence]
    citations: list[_Evidence]
    citation_issues: list[_Issue]
    llm_called: bool
    model: str = "synthetic-model"
    provider: str = "synthetic-provider"
    fallback_reasons: list[str] | None = None
    selection_warnings: list[str] | None = None
    generation_metadata: dict[str, Any] | None = None
    selection_metadata: dict[str, Any] | None = None


def _query(
    *,
    query_id: str = "q1",
    expected_decision: ExpectedDecision = ExpectedDecision.ANSWER_ALLOWED,
    question_types: list[QuestionType] | None = None,
    blocking: bool = False,
) -> BenchmarkQuery:
    return BenchmarkQuery(
        id=query_id,
        query="Synthetic Vietnamese legal query?",
        primary_domain=LegalDomain.CIVIL_FAMILY_IDENTITY,
        question_types=question_types or [QuestionType.SINGLE_ARTICLE_LOOKUP],
        expected_decision=expected_decision,
        fallback_reason=None,
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


def _judgment(chunk_id: str, *, query_id: str = "q1") -> EvidenceJudgment:
    return EvidenceJudgment(
        query_id=query_id,
        chunk_id=chunk_id,
        relevance=RelevanceLevel.REQUIRED_DIRECT,
        evidence_group_ids=["g1"],
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


def test_generation_case_counts_selected_evidence_and_groups() -> None:
    result = _Result(
        decision=ExpectedDecision.ANSWER_ALLOWED,
        answer="Câu trả lời có Điều 1. [E1]",
        used_evidence=[_Evidence("E1", "chunk_a")],
        citations=[_Evidence("E1", "chunk_a")],
        citation_issues=[],
        llm_called=True,
    )

    case = evaluate_generation_case(
        query=_query(blocking=True),
        split="development",
        result=result,
        retrieved_chunks=[{"chunk_id": "chunk_a"}],
        judgments=[_judgment("chunk_a")],
        groups=[_group()],
        elapsed_ms=12.0,
    )

    assert case["pipeline_decision"] == "answer_allowed"
    assert case["blocking"] is True
    assert case["citation_guard_result"]["citation_id_valid"] is True
    assert case["missing_required_evidence_check"][
        "selected_required_direct_coverage"
    ] == pytest.approx(1.0)
    assert case["missing_required_evidence_check"][
        "selected_evidence_group_coverage"
    ] == pytest.approx(1.0)
    assert case["case_status"] == "pass"


def test_generation_metrics_separate_answer_and_fallback_cases() -> None:
    answer_case = evaluate_generation_case(
        query=_query(),
        split="development",
        result=_Result(
            decision=ExpectedDecision.ANSWER_ALLOWED,
            answer="Câu trả lời có Điều 1. [E1]",
            used_evidence=[_Evidence("E1", "chunk_a")],
            citations=[_Evidence("E1", "chunk_a")],
            citation_issues=[],
            llm_called=True,
        ),
        retrieved_chunks=[{"chunk_id": "chunk_a"}],
        judgments=[_judgment("chunk_a")],
        groups=[_group()],
        elapsed_ms=10.0,
    )
    fallback_case = evaluate_generation_case(
        query=_fallback_query(),
        split="held_out_test",
        result=_Result(
            decision=ExpectedDecision.FALLBACK_REQUIRED,
            answer="Không đủ căn cứ để trả lời.",
            used_evidence=[],
            citations=[],
            citation_issues=[],
            llm_called=False,
        ),
        retrieved_chunks=[],
        judgments=[],
        groups=[],
        elapsed_ms=5.0,
    )

    metrics = aggregate_generation_metrics([answer_case, fallback_case])
    breakdowns = build_generation_breakdowns([answer_case, fallback_case])

    assert metrics["query_count"] == 2
    assert metrics["decision_accuracy"] == pytest.approx(1.0)
    assert metrics["answer_allowed_answer_rate"] == pytest.approx(1.0)
    assert metrics["fallback_required_fallback_rate"] == pytest.approx(1.0)
    assert metrics["citation_id_validity_rate"] == pytest.approx(1.0)
    assert breakdowns["split"]["development"]["query_count"] == 1
    assert breakdowns["split"]["held_out_test"]["query_count"] == 1
