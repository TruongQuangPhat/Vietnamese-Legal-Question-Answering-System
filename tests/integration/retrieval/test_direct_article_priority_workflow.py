"""Golden retrieval/evidence tests for direct legal article priority."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.retrieval.evidence import build_evidence_bundle
from src.retrieval.prompting import build_naive_rag_prompt
from src.retrieval.selection import select_evidence_for_answer
from src.retrieval.sparse_retriever import SparseBM25Retriever

CHUNKS_PATH = Path("data/processed/legal_chunks.jsonl")
LABOR_LAW_ID = "BLLD_VBHN"


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    query: str
    expected_article: str
    expected_primary_clauses: tuple[str | None, ...]


GOLDEN_CASES = (
    GoldenCase(
        case_id="employee_unilateral_termination",
        query="Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
        expected_article="35",
        expected_primary_clauses=("1", "2"),
    ),
    GoldenCase(
        case_id="employer_unilateral_termination",
        query="Người sử dụng lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
        expected_article="36",
        expected_primary_clauses=("1",),
    ),
    GoldenCase(
        case_id="unlawful_unilateral_termination",
        query="Khi nào đơn phương chấm dứt hợp đồng lao động bị coi là trái pháp luật?",
        expected_article="39",
        expected_primary_clauses=(None,),
    ),
    GoldenCase(
        case_id="employee_notice_period",
        query="Người lao động phải báo trước bao lâu khi đơn phương chấm dứt hợp đồng?",
        expected_article="35",
        expected_primary_clauses=("1",),
    ),
    GoldenCase(
        case_id="employee_no_notice",
        query="Người lao động có được nghỉ việc không cần báo trước trong trường hợp nào?",
        expected_article="35",
        expected_primary_clauses=("2",),
    ),
)


@pytest.fixture(scope="module")
def sparse_retriever() -> SparseBM25Retriever:
    """Build the local sparse retriever once for golden integration checks."""
    if not CHUNKS_PATH.exists():
        pytest.skip(f"processed chunks file is missing: {CHUNKS_PATH}")
    return SparseBM25Retriever.from_jsonl(CHUNKS_PATH, default_top_k=50)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[case.case_id for case in GOLDEN_CASES])
async def test_direct_article_priority_golden_cases(
    sparse_retriever: SparseBM25Retriever,
    case: GoldenCase,
) -> None:
    """Golden questions select and cite the direct substantive article first."""
    retrieval = await sparse_retriever.retrieve(case.query, top_k=50)
    bundle = build_evidence_bundle(retrieval)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=case.query, selection_result=selection)

    direct_candidates = [
        chunk
        for chunk in retrieval.results
        if chunk.law_id == LABOR_LAW_ID and chunk.article_number == case.expected_article
    ]
    assert direct_candidates, f"{case.case_id}: expected direct article absent from candidates"

    primary = selection.selected_evidence[0].packet
    primary_citation = prompt.evidence[0]
    assert primary.law_id == LABOR_LAW_ID
    assert primary.article_number == case.expected_article
    assert primary.clause_number in case.expected_primary_clauses
    assert primary_citation.law_id == LABOR_LAW_ID
    assert primary_citation.article_number == case.expected_article
    assert primary_citation.clause_number in case.expected_primary_clauses


@pytest.mark.asyncio
async def test_employee_termination_keeps_article_34_clause_9_auxiliary_not_primary(
    sparse_retriever: SparseBM25Retriever,
) -> None:
    """Article 34 Clause 9 may appear as a cross-reference, but is not primary."""
    query = "Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?"
    retrieval = await sparse_retriever.retrieve(query, top_k=50)
    bundle = build_evidence_bundle(retrieval)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=query, selection_result=selection)

    article_34_clause_9 = [
        chunk
        for chunk in retrieval.results
        if chunk.law_id == LABOR_LAW_ID
        and chunk.article_number == "34"
        and chunk.clause_number == "9"
    ]
    assert article_34_clause_9
    assert "Điều 35" in (article_34_clause_9[0].text or "")

    primary = selection.selected_evidence[0].packet
    assert primary.article_number == "35"
    assert prompt.evidence[0].article_number == "35"
    assert all(
        not (evidence.article_number == "34" and evidence.clause_number == "9")
        for evidence in prompt.evidence
    )
    assert all(
        selected.packet.article_number != "39" for selected in selection.selected_evidence[:1]
    )
