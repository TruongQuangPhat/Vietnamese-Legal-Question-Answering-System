"""Unit tests for the read-only local hybrid validation adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from scripts.evaluation.run_local_hybrid_retrieval_validation import (
    _case_metrics_row,
    _run_one_case,
)
from src.evaluation.benchmark.direct_evidence import (
    EvidenceTarget,
    compute_aggregate_metrics,
    target_key,
)


@dataclass
class FakeCandidate:
    """Minimal provision object used by canonical target matching helpers."""

    rank: int
    chunk_id: str
    law_id: str
    article_number: str
    clause_number: str | None = None
    point_label: str | None = None
    citation: str | None = None


@dataclass
class FakeRetrievalResult:
    """Minimal retrieval result compatible with the adapter."""

    results: list[FakeCandidate]


class FakeRetriever:
    """Async retriever returning fixed candidates."""

    def __init__(self, results: list[FakeCandidate], *, default_top_k: int = 50) -> None:
        self.results = results
        self.default_top_k = default_top_k

    async def retrieve(self, query: str, *, top_k: int) -> FakeRetrievalResult:
        """Return the configured candidates bounded by the requested top-k."""
        return FakeRetrievalResult(self.results[:top_k])


@dataclass
class FakeSelectionItem:
    """Minimal selected-evidence wrapper."""

    packet: FakeCandidate
    rank: int


@dataclass
class FakeSelection:
    """Minimal selection result consumed by the local adapter."""

    selected_evidence: list[FakeSelectionItem]
    warnings: list[Any] = field(default_factory=list)
    decision: str = "answer"
    fallback_reasons: list[Any] = field(default_factory=list)


@dataclass
class FakePrompt:
    """Minimal prompt object with mapped evidence."""

    evidence: list[FakeCandidate]


@pytest.mark.asyncio
async def test_local_hybrid_adapter_uses_canonical_target_metrics_without_services() -> None:
    """The adapter path reuses canonical target keys and aggregate metrics."""
    target = EvidenceTarget("BLLD_VBHN", "35", "2")
    correct = FakeCandidate(
        rank=1,
        chunk_id="c35-2",
        law_id="BLLD_VBHN",
        article_number="35",
        clause_number="2",
        citation="Khoản 2 Điều 35 Bộ luật Lao động",
    )
    distractor = FakeCandidate(
        rank=2,
        chunk_id="c36-1",
        law_id="BLLD_VBHN",
        article_number="36",
        clause_number="1",
        citation="Khoản 1 Điều 36 Bộ luật Lao động",
    )
    correct_dense = FakeCandidate(
        rank=2,
        chunk_id="c35-2",
        law_id="BLLD_VBHN",
        article_number="35",
        clause_number="2",
        citation="Khoản 2 Điều 35 Bộ luật Lao động",
    )
    distractor_dense = FakeCandidate(
        rank=1,
        chunk_id="c36-1",
        law_id="BLLD_VBHN",
        article_number="36",
        clause_number="1",
        citation="Khoản 1 Điều 36 Bộ luật Lao động",
    )
    sparse = FakeRetriever([correct, distractor])
    dense = FakeRetriever([distractor_dense, correct_dense])
    fused = FakeRetriever([correct, distractor])

    def bundle_builder(result: FakeRetrievalResult, *, config: object) -> FakeRetrievalResult:
        return result

    def selector(bundle: FakeRetrievalResult, *, config: object) -> FakeSelection:
        return FakeSelection(
            selected_evidence=[
                FakeSelectionItem(packet=item, rank=index)
                for index, item in enumerate(bundle.results[:1], start=1)
            ]
        )

    def prompt_builder(query: str, selection_result: FakeSelection) -> FakePrompt:
        return FakePrompt([item.packet for item in selection_result.selected_evidence])

    case = await _run_one_case(
        {"case_id": "employee_no_notice", "query": "q", "expected_targets": [target]},
        retriever=fused,
        dense=dense,
        sparse=sparse,
        context_config=object(),
        selection_config=object(),
        fusion_top_k=10,
        prompt_builder=prompt_builder,
        bundle_builder=bundle_builder,
        selector=selector,
    )

    key = target_key(target)
    assert case["sparse_target_rank"][key] == 1
    assert case["dense_target_rank"][key] == 2
    assert case["fused_target_rank"][key] == 1
    assert case["direct_primary_pass"] is True
    assert case["multi_article_coverage_pass"] is True
    json.dumps(case, ensure_ascii=False)

    metrics_row = _case_metrics_row(case, selection_input_top_k=10)
    metrics = compute_aggregate_metrics([metrics_row])
    assert metrics["primary_evidence_accuracy"] == 1.0
    assert metrics["citation_alignment_accuracy"] == 1.0
