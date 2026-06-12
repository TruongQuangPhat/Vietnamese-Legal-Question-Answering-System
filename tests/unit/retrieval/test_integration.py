"""Unit tests for Phase 9A.4 selection smoke integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.retrieval.evaluation import ExpectedTarget, ManualRetrievalQuery
from src.retrieval.evidence import (
    CitationScope,
    ContextAssemblyConfig,
    EvidenceBundle,
    EvidencePacket,
    EvidenceSafetyLevel,
    build_evidence_packet,
)
from src.retrieval.integration import (
    SelectionSmokeError,
    filter_query_records,
    run_selection_smoke_for_query,
    run_selection_smoke_suite,
)
from src.retrieval.models import RetrievalFilters, RetrievalResult, RetrievedChunk
from src.retrieval.selection import (
    AnswerabilityDecision,
    EvidenceRejectionReason,
    EvidenceSelectionConfig,
    EvidenceSelectionResult,
    FallbackReason,
    FallbackReasonCode,
    RejectedEvidence,
    SelectedEvidence,
)
from src.retrieval.workflows import selection_smoke as smoke_cli


class FakeRetriever:
    """Fake retriever returning configured results or errors."""

    def __init__(self, outputs: list[RetrievalResult | Exception], events: list[str] | None = None):
        self.outputs = list(outputs)
        self.events = events
        self.calls: list[dict[str, Any]] = []

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        if self.events is not None:
            self.events.append("retrieve")
        self.calls.append({"query": query, "top_k": top_k, "collection_name": collection_name})
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def make_target(
    *,
    law_id: str = "BLLD_VBHN",
    article_number: str = "113",
    clause_number: str | None = "1",
    point_label: str | None = None,
    match_level: str = "clause",
) -> ExpectedTarget:
    """Build one expected target."""
    return ExpectedTarget(
        law_id=law_id,
        article_number=article_number,
        clause_number=clause_number,
        point_label=point_label,
        match_level=match_level,
    )


def make_record(
    *,
    query_id: str = "annual_leave_days",
    allowed_decisions: list[str] | None = None,
    expected_decision: str | None = None,
    expected: list[ExpectedTarget] | None = None,
) -> ManualRetrievalQuery:
    """Build one manual smoke query record."""
    return ManualRetrievalQuery(
        query_id=query_id,
        query=f"{query_id}?",
        expected=expected or [make_target()],
        expected_decision=expected_decision,
        allowed_decisions=allowed_decisions,
        notes="test",
    )


def make_chunk(
    *,
    rank: int = 1,
    chunk_id: str = "chunk-1",
    law_id: str | None = "BLLD_VBHN",
    article_number: str | None = "113",
    clause_number: str | None = "1",
    point_label: str | None = None,
    citation: str | None = "Khoản 1, Điều 113, Bộ luật Lao động",
    text: str | None = "1. Người lao động được nghỉ hằng năm.",
    parent_text: str | None = None,
    score: float = 0.9,
) -> RetrievedChunk:
    """Build one retrieved chunk."""
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        law_id=law_id,
        law_name="Law",
        article_number=article_number,
        clause_number=clause_number,
        point_label=point_label,
        citation=citation,
        source_url="https://thuvienphapluat.vn/example",
        source_domain="thuvienphapluat.vn",
        text=text,
        parent_text=parent_text,
    )


def make_result(chunks: list[RetrievedChunk]) -> RetrievalResult:
    """Build one retrieval result."""
    return RetrievalResult(
        query="test",
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
        top_k=20,
        elapsed_ms=12.0,
        query_vector_dimension=1024,
        filters=RetrievalFilters(),
        results=chunks,
    )


def make_packet(**kwargs: object) -> EvidencePacket:
    """Build one evidence packet."""
    return build_evidence_packet(
        make_chunk(**kwargs),
        config=ContextAssemblyConfig(min_safety_level=EvidenceSafetyLevel.UNSAFE),
    )


def make_bundle(packets: list[EvidencePacket]) -> EvidenceBundle:
    """Build one evidence bundle."""
    return EvidenceBundle(
        query="test",
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
        top_k=20,
        packets=packets,
        total_packets=len(packets),
        safe_count=sum(1 for packet in packets if packet.safety_level == EvidenceSafetyLevel.SAFE),
        caution_count=sum(
            1 for packet in packets if packet.safety_level == EvidenceSafetyLevel.CAUTION
        ),
        unsafe_count=sum(
            1 for packet in packets if packet.safety_level == EvidenceSafetyLevel.UNSAFE
        ),
        issue_count=sum(len(packet.safety_issues) for packet in packets),
    )


def make_selection(
    *,
    decision: AnswerabilityDecision,
    selected_packet: EvidencePacket | None = None,
    rejected_packet: EvidencePacket | None = None,
    rendered_context: str = "Citation: x\nCitable text:\ny",
) -> EvidenceSelectionResult:
    """Build a controlled evidence selection result."""
    selected: list[SelectedEvidence] = []
    rejected: list[RejectedEvidence] = []
    fallback_reasons: list[FallbackReason] = []
    if selected_packet is not None:
        selected.append(
            SelectedEvidence(
                packet=selected_packet,
                packet_id=selected_packet.packet_id,
                rank=selected_packet.rank,
                score=selected_packet.score,
                chunk_id=selected_packet.chunk_id,
                citation=selected_packet.citation,
                safety_level=selected_packet.safety_level,
                citation_scope=selected_packet.citation_scope,
                has_auxiliary_context=selected_packet.auxiliary_context is not None,
            )
        )
    if rejected_packet is not None:
        rejected.append(
            RejectedEvidence(
                packet=rejected_packet,
                packet_id=rejected_packet.packet_id,
                rank=rejected_packet.rank,
                chunk_id=rejected_packet.chunk_id,
                reasons=[EvidenceRejectionReason.UNSAFE_EVIDENCE],
            )
        )
    if decision != AnswerabilityDecision.ANSWER_ALLOWED:
        fallback_reasons.append(
            FallbackReason(
                code=FallbackReasonCode.EXACT_TARGET_MISSING_IN_EVAL_MODE,
                message="exact target missing",
            )
        )
    return EvidenceSelectionResult(
        decision=decision,
        selected_evidence=selected,
        rejected_evidence=rejected,
        fallback_reasons=fallback_reasons,
        warnings=[],
        rendered_context=rendered_context if selected else "",
        selected_count=len(selected),
        rejected_count=len(rejected),
        unsafe_rejected_count=sum(
            1 for item in rejected if item.packet.safety_level == EvidenceSafetyLevel.UNSAFE
        ),
        caution_selected_count=sum(
            1 for item in selected if item.safety_level == EvidenceSafetyLevel.CAUTION
        ),
    )


@pytest.mark.asyncio
async def test_single_query_pipeline_calls_components_in_order() -> None:
    """Smoke pipeline composes retriever, evidence builder, and selector."""
    events: list[str] = []
    packet = make_packet()
    bundle = make_bundle([packet])

    def builder(result: RetrievalResult, config: ContextAssemblyConfig | None) -> EvidenceBundle:
        assert result.results[0].chunk_id == "chunk-1"
        assert config is not None
        events.append("build")
        return bundle

    def selector(
        evidence_bundle: EvidenceBundle,
        config: EvidenceSelectionConfig | None,
        expected_targets: list[Any],
        risk_flags: list[Any],
    ) -> EvidenceSelectionResult:
        assert evidence_bundle is bundle
        assert config is not None
        assert expected_targets
        assert not risk_flags
        events.append("select")
        return make_selection(decision=AnswerabilityDecision.ANSWER_ALLOWED, selected_packet=packet)

    result = await run_selection_smoke_for_query(
        make_record(allowed_decisions=["answer_allowed"]),
        FakeRetriever([make_result([make_chunk()])], events),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_config=ContextAssemblyConfig(),
        selection_config=EvidenceSelectionConfig(),
        evidence_builder=builder,
        evidence_selector=selector,
    )

    assert events == ["retrieve", "build", "select"]
    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.decision_passed is True
    assert result.result_count == 1


@pytest.mark.asyncio
async def test_batch_smoke_report_aggregates_decisions() -> None:
    """Suite reports aggregate decision and pass/fail counts."""
    safe_packet = make_packet()
    fallback_packet = make_packet(chunk_id="chunk-2")
    selections = [
        make_selection(decision=AnswerabilityDecision.ANSWER_ALLOWED, selected_packet=safe_packet),
        make_selection(decision=AnswerabilityDecision.FALLBACK_REQUIRED),
    ]

    def builder(_: RetrievalResult, __: ContextAssemblyConfig | None) -> EvidenceBundle:
        return make_bundle([safe_packet, fallback_packet])

    def selector(*_: Any) -> EvidenceSelectionResult:
        return selections.pop(0)

    report = await run_selection_smoke_suite(
        [
            make_record(query_id="ok", allowed_decisions=["answer_allowed"]),
            make_record(query_id="fallback", allowed_decisions=["fallback_required"]),
        ],
        FakeRetriever([make_result([make_chunk()]), make_result([make_chunk(chunk_id="chunk-2")])]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_builder=builder,
        evidence_selector=selector,
    )

    assert report.query_count == 2
    assert report.aggregate_summary.answer_allowed_count == 1
    assert report.aggregate_summary.fallback_required_count == 1
    assert report.aggregate_summary.decision_pass_count == 2
    assert report.aggregate_pass_fail_counts["decision_pass_count"] == 2


@pytest.mark.asyncio
async def test_allowed_decisions_pass_and_fail_checks() -> None:
    """Allowed decision metadata controls smoke expectation pass/fail."""
    packet = make_packet()

    def builder(_: RetrievalResult, __: ContextAssemblyConfig | None) -> EvidenceBundle:
        return make_bundle([packet])

    def selector(*_: Any) -> EvidenceSelectionResult:
        return make_selection(decision=AnswerabilityDecision.ANSWER_ALLOWED, selected_packet=packet)

    passed = await run_selection_smoke_for_query(
        make_record(allowed_decisions=["answer_allowed"]),
        FakeRetriever([make_result([make_chunk()])]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_builder=builder,
        evidence_selector=selector,
    )
    failed = await run_selection_smoke_for_query(
        make_record(allowed_decisions=["fallback_required", "needs_review"]),
        FakeRetriever([make_result([make_chunk()])]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_builder=builder,
        evidence_selector=selector,
    )

    assert passed.decision_passed is True
    assert failed.decision_passed is False


@pytest.mark.asyncio
async def test_annual_leave_style_answer_allowed_fails_expectation() -> None:
    """Annual-leave smoke expectation must not pass clean answer_allowed."""
    packet = make_packet(clause_number="4")

    result = await run_selection_smoke_for_query(
        make_record(
            query_id="annual_leave_days",
            allowed_decisions=["fallback_required", "needs_review"],
        ),
        FakeRetriever([make_result([make_chunk(clause_number="4")])]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_builder=lambda *_: make_bundle([packet]),
        evidence_selector=lambda *_: make_selection(
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            selected_packet=packet,
        ),
    )

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.decision_passed is False


@pytest.mark.asyncio
async def test_health_insurance_answer_allowed_passes() -> None:
    """Health-insurance exact point case can pass answer_allowed expectation."""
    expected = [
        make_target(
            law_id="LBHYT_VBHN",
            article_number="16",
            clause_number="3",
            point_label="d",
            match_level="point",
        )
    ]
    packet = make_packet(
        law_id="LBHYT_VBHN",
        article_number="16",
        clause_number="3",
        point_label="d",
    )

    result = await run_selection_smoke_for_query(
        make_record(
            query_id="health_insurance_children_under_6",
            expected=expected,
            allowed_decisions=["answer_allowed"],
        ),
        FakeRetriever(
            [
                make_result(
                    [
                        make_chunk(
                            law_id="LBHYT_VBHN",
                            article_number="16",
                            clause_number="3",
                            point_label="d",
                        )
                    ]
                )
            ]
        ),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_builder=lambda *_: make_bundle([packet]),
        evidence_selector=lambda *_: make_selection(
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            selected_packet=packet,
        ),
    )

    assert result.decision_passed is True
    assert result.selected_count == 1


@pytest.mark.asyncio
async def test_non_strict_smoke_reports_risk_but_allows_valid_expected_evidence() -> None:
    """Non-strict smoke mode reports risk flags without forcing fallback."""
    expected = [
        make_target(
            law_id="BLDS_2015",
            article_number="2",
            clause_number=None,
            point_label=None,
            match_level="article",
        )
    ]
    result = await run_selection_smoke_for_query(
        make_record(
            query_id="civil_rights_protection",
            expected=expected,
            allowed_decisions=["answer_allowed", "needs_review"],
        ),
        FakeRetriever(
            [
                make_result(
                    [
                        make_chunk(
                            rank=1,
                            chunk_id="article-11-clause-1",
                            law_id="BLDS_2015",
                            article_number="11",
                            clause_number="1",
                            citation="Khoản 1, Điều 11, Bộ luật Dân sự 2015",
                            text="1. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự của mình.",
                            parent_text="Điều 11. Các phương thức bảo vệ quyền dân sự...",
                        ),
                        make_chunk(
                            rank=2,
                            chunk_id="article-2",
                            law_id="BLDS_2015",
                            article_number="2",
                            clause_number=None,
                            citation="Điều 2, Bộ luật Dân sự 2015",
                            text=("Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự."),
                            parent_text=(
                                "Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự."
                            ),
                        ),
                    ]
                )
            ]
        ),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        selection_config=EvidenceSelectionConfig(max_selected_packets=1),
    )

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.decision_passed is True
    assert "top_result_wrong_article_when_expected_article_exists_lower" in result.risk_flags
    assert result.selected_evidence[0].chunk_id == "article-2"


@pytest.mark.asyncio
async def test_strict_smoke_can_enforce_high_citation_risk() -> None:
    """Strict smoke mode can turn high evaluation risk into fallback."""
    expected = [
        make_target(
            law_id="BLDS_2015",
            article_number="2",
            clause_number=None,
            point_label=None,
            match_level="article",
        )
    ]
    result = await run_selection_smoke_for_query(
        make_record(
            query_id="civil_rights_protection",
            expected=expected,
            allowed_decisions=["answer_allowed", "needs_review"],
        ),
        FakeRetriever(
            [
                make_result(
                    [
                        make_chunk(
                            rank=1,
                            chunk_id="article-11-clause-1",
                            law_id="BLDS_2015",
                            article_number="11",
                            clause_number="1",
                            citation="Khoản 1, Điều 11, Bộ luật Dân sự 2015",
                            text="1. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự của mình.",
                            parent_text="Điều 11. Các phương thức bảo vệ quyền dân sự...",
                        ),
                        make_chunk(
                            rank=2,
                            chunk_id="article-2",
                            law_id="BLDS_2015",
                            article_number="2",
                            clause_number=None,
                            citation="Điều 2, Bộ luật Dân sự 2015",
                            text=("Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự."),
                            parent_text=(
                                "Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự."
                            ),
                        ),
                    ]
                )
            ]
        ),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        selection_config=EvidenceSelectionConfig(max_selected_packets=1),
        enforce_risk_flags_in_selection=True,
    )

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert result.decision_passed is False
    assert FallbackReasonCode.HIGH_CITATION_RISK.value in result.fallback_reasons
    assert result.selected_evidence[0].chunk_id == "article-2"


@pytest.mark.asyncio
async def test_one_query_error_does_not_stop_batch() -> None:
    """One retrieval error is captured while later records still run."""
    packet = make_packet()

    report = await run_selection_smoke_suite(
        [
            make_record(query_id="error"),
            make_record(query_id="ok", allowed_decisions=["answer_allowed"]),
        ],
        FakeRetriever([RuntimeError("boom"), make_result([make_chunk()])]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_builder=lambda *_: make_bundle([packet]),
        evidence_selector=lambda *_: make_selection(
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            selected_packet=packet,
        ),
    )

    assert report.query_count == 2
    assert report.error_count == 1
    assert report.per_query[0].errors == ["boom"]
    assert report.per_query[1].decision == AnswerabilityDecision.ANSWER_ALLOWED


@pytest.mark.asyncio
async def test_empty_query_list_raises_clean_error() -> None:
    """The suite rejects empty manual datasets with a clear error."""
    with pytest.raises(SelectionSmokeError, match="query_records"):
        await run_selection_smoke_suite(
            [],
            FakeRetriever([]),
            collection_name="vnlaw_chunks_bgem3_v1_full",
        )


def test_case_id_filtering_returns_match_and_raises_for_missing_id() -> None:
    """case-id filtering selects one record or fails clearly."""
    records = [make_record(query_id="a"), make_record(query_id="b")]

    assert filter_query_records(records, case_id="b")[0].query_id == "b"
    with pytest.raises(SelectionSmokeError, match="query_id not found"):
        filter_query_records(records, case_id="missing")


@pytest.mark.asyncio
async def test_json_report_shape_and_context_preview_truncation() -> None:
    """Report model dump includes aggregate/per-query fields and bounded previews."""
    packet = make_packet()
    long_context = "x" * 80

    report = await run_selection_smoke_suite(
        [make_record(allowed_decisions=["answer_allowed"])],
        FakeRetriever([make_result([make_chunk()])]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        context_preview_chars=20,
        evidence_builder=lambda *_: make_bundle([packet]),
        evidence_selector=lambda *_: make_selection(
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            selected_packet=packet,
            rendered_context=long_context,
        ),
    )

    payload = report.model_dump(mode="json")
    assert payload["report_type"] == "selection_smoke_report"
    assert "aggregate_summary" in payload
    assert "aggregate_decision_counts" in payload
    assert payload["per_query"][0]["rendered_context_preview"].endswith("...")
    assert len(payload["per_query"][0]["rendered_context_preview"]) == 20


@pytest.mark.asyncio
async def test_evidence_summaries_serialize_enum_values_cleanly() -> None:
    """Selected/rejected summaries expose stable string values for enum fields."""
    safe_packet = make_packet()
    unsafe_packet = make_packet(chunk_id="unsafe", citation=None)

    result = await run_selection_smoke_for_query(
        make_record(allowed_decisions=["answer_allowed"]),
        FakeRetriever([make_result([make_chunk()])]),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        evidence_builder=lambda *_: make_bundle([safe_packet, unsafe_packet]),
        evidence_selector=lambda *_: make_selection(
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            selected_packet=safe_packet,
            rejected_packet=unsafe_packet,
        ),
    )
    payload = result.model_dump(mode="json")

    assert payload["selected_evidence"][0]["safety_level"] == EvidenceSafetyLevel.SAFE.value
    assert payload["selected_evidence"][0]["citation_scope"] == CitationScope.CHILD_EXACT.value
    assert payload["rejected_evidence"][0]["rejection_reasons"] == [
        EvidenceRejectionReason.UNSAFE_EVIDENCE.value
    ]
    assert {item.chunk_id for item in result.selected_evidence} == {"chunk-1"}


def test_cli_parser_and_validation() -> None:
    """The smoke CLI exposes expected arguments and path safety."""
    parser = smoke_cli.build_arg_parser()
    args = parser.parse_args(
        [
            "--queries",
            "data/eval/manual_retrieval_queries.jsonl",
            "--top-k",
            "20",
            "--strict",
            "--case-id",
            "annual_leave_days",
        ]
    )

    assert args.strict is True
    assert args.case_id == "annual_leave_days"
    smoke_cli.validate_cli_arguments(
        queries_path=Path("data/eval/manual_retrieval_queries.jsonl"),
        output_path=Path("artifacts/reports/retrieval/selection_smoke_report.json"),
        top_k=20,
        max_selected_packets=5,
        context_preview_chars=1200,
    )
    with pytest.raises(ValueError, match="top-k"):
        smoke_cli.validate_cli_arguments(
            queries_path=Path("data/eval/manual_retrieval_queries.jsonl"),
            output_path=Path("artifacts/reports/retrieval/selection_smoke_report.json"),
            top_k=0,
            max_selected_packets=5,
            context_preview_chars=1200,
        )
    with pytest.raises(ValueError, match="protected"):
        smoke_cli.validate_cli_arguments(
            queries_path=Path("data/eval/manual_retrieval_queries.jsonl"),
            output_path=Path("data/processed/smoke.json"),
            top_k=20,
            max_selected_packets=5,
            context_preview_chars=1200,
        )
