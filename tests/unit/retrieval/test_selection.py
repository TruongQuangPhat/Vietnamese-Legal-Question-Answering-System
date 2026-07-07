"""Unit tests for evidence selection evidence selection and fallback rules."""

from __future__ import annotations

from src.retrieval.evaluation import EvidenceRiskFlag, ExpectedTarget
from src.retrieval.evidence import (
    CitationScope,
    ContextAssemblyConfig,
    EvidenceBundle,
    EvidencePacket,
    EvidenceSafetyLevel,
    build_evidence_packet,
)
from src.retrieval.models import RetrievalIssue, RetrievalIssueSeverity, RetrievedChunk
from src.retrieval.selection import (
    AnswerabilityDecision,
    EvidenceRejectionReason,
    EvidenceSelectionConfig,
    FallbackReasonCode,
    SelectionWarningCode,
    select_evidence_for_answer,
)


def make_chunk(
    *,
    rank: int = 1,
    score: float = 0.9,
    chunk_id: str | None = "chunk-1",
    law_id: str | None = "BLLD_VBHN",
    law_name: str | None = "Bộ luật Lao động (VBHN 2025)",
    level: str | None = "clause",
    chunk_kind: str | None = "clause",
    article_number: str | None = "113",
    clause_number: str | None = "1",
    point_label: str | None = None,
    citation: str | None = "Khoản 1, Điều 113, Bộ luật Lao động (VBHN 2025)",
    text: str | None = "1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm.",
    parent_text: str | None = None,
    source_url: str | None = "https://thuvienphapluat.vn/example",
    source_domain: str | None = "thuvienphapluat.vn",
    issues: list[RetrievalIssue] | None = None,
) -> RetrievedChunk:
    """Build one retrieved chunk for selection tests."""
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        law_id=law_id,
        law_name=law_name,
        level=level,
        chunk_kind=chunk_kind,
        article_number=article_number,
        clause_number=clause_number,
        point_label=point_label,
        citation=citation,
        text=text,
        parent_text=parent_text,
        source_url=source_url,
        source_domain=source_domain,
        issues=issues or [],
    )


def make_packet(**kwargs: object) -> EvidencePacket:
    """Build one evidence packet through the evidence safety classifier."""
    return build_evidence_packet(
        make_chunk(**kwargs),
        config=ContextAssemblyConfig(min_safety_level=EvidenceSafetyLevel.UNSAFE),
    )


def make_bundle(packets: list[EvidencePacket]) -> EvidenceBundle:
    """Build an evidence bundle from already-classified packets."""
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


def test_safe_evidence_packet_allows_answer() -> None:
    """A safe citable packet passes the evidence gate."""
    result = select_evidence_for_answer(make_bundle([make_packet(parent_text=None)]))

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1
    assert result.rejected_count == 0
    assert "Citable text:" in result.rendered_context
    assert "Citation:" in result.rendered_context


def test_empty_bundle_requires_fallback() -> None:
    """No evidence cannot support generation."""
    result = select_evidence_for_answer(make_bundle([]))

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert [reason.code for reason in result.fallback_reasons] == [FallbackReasonCode.NO_EVIDENCE]


def test_unsafe_only_bundle_requires_fallback() -> None:
    """All-unsafe evidence is rejected and forces fallback."""
    result = select_evidence_for_answer(make_bundle([make_packet(citation=None)]))

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert result.selected_count == 0
    assert result.rejected_count == 1
    assert result.rejected_evidence[0].packet.safety_level == EvidenceSafetyLevel.UNSAFE
    assert result.fallback_reasons[0].code == FallbackReasonCode.ALL_EVIDENCE_UNSAFE


def test_missing_required_metadata_is_rejected() -> None:
    """Critical metadata gaps produce rejection reasons and fallback."""
    cases = [
        ({"citation": None}, EvidenceRejectionReason.MISSING_REQUIRED_CITATION),
        ({"law_id": None}, EvidenceRejectionReason.MISSING_REQUIRED_LAW_ID),
        ({"source_url": None}, EvidenceRejectionReason.MISSING_REQUIRED_SOURCE_URL),
        ({"text": None}, EvidenceRejectionReason.MISSING_REQUIRED_CHILD_TEXT),
    ]
    for kwargs, expected_reason in cases:
        result = select_evidence_for_answer(make_bundle([make_packet(**kwargs)]))

        assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
        assert expected_reason in result.rejected_evidence[0].reasons


def test_safe_evidence_is_selected_before_caution_evidence() -> None:
    """Selection sorts safe packets before caution packets, then by rank."""
    caution = make_packet(
        rank=1,
        chunk_id="caution",
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )
    safe = make_packet(rank=2, chunk_id="safe", parent_text=None)

    result = select_evidence_for_answer(
        make_bundle([caution, safe]),
        config=EvidenceSelectionConfig(max_selected_packets=2),
    )

    assert result.selected_count == 2
    assert result.selected_evidence[0].chunk_id == "safe"
    assert result.selected_evidence[1].chunk_id == "caution"


def test_caution_evidence_with_citable_child_text_can_be_selected() -> None:
    """Caution evidence is selectable when citation and child text are present."""
    caution = make_packet(
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )

    result = select_evidence_for_answer(
        make_bundle([caution]),
        config=EvidenceSelectionConfig(
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=True,
        ),
    )

    assert result.selected_count == 1
    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_evidence[0].citation_scope == CitationScope.CHILD_EXACT


def test_citable_child_with_auxiliary_parent_context_allows_answer_by_default() -> None:
    """Auxiliary parent context does not block a citation-ready child packet."""
    caution = make_packet(
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )

    result = select_evidence_for_answer(make_bundle([caution]))

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1
    assert result.selected_evidence[0].citation_scope == CitationScope.CHILD_EXACT
    assert FallbackReasonCode.PARENT_CONTEXT_ONLY not in {
        reason.code for reason in result.fallback_reasons
    }


def test_parent_context_without_child_text_still_fallbacks() -> None:
    """Parent context alone remains non-citable."""
    parent_only = make_packet(
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text=None,
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )

    result = select_evidence_for_answer(make_bundle([parent_only]))

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert result.selected_count == 0
    assert result.rejected_evidence[0].packet.safety_level == EvidenceSafetyLevel.UNSAFE
    assert (
        EvidenceRejectionReason.MISSING_REQUIRED_CHILD_TEXT in result.rejected_evidence[0].reasons
    )


def test_weak_citable_evidence_allows_answer_with_caution() -> None:
    """Weak but citable evidence can proceed only through the caution status."""
    ambiguous = make_packet(
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
        issues=[
            RetrievalIssue(
                code="ambiguous_candidate",
                severity=RetrievalIssueSeverity.WARNING,
                message="candidate needs review before answer use",
            )
        ],
    )

    result = select_evidence_for_answer(make_bundle([ambiguous]))

    assert result.decision == AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED
    assert FallbackReasonCode.ALL_SELECTED_EVIDENCE_CAUTION in {
        reason.code for reason in result.fallback_reasons
    }
    assert result.rendered_context


def test_weak_citable_evidence_can_still_require_review_when_configured() -> None:
    """The legacy review path remains available for stricter offline gates."""
    ambiguous = make_packet(
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
        issues=[
            RetrievalIssue(
                code="ambiguous_candidate",
                severity=RetrievalIssueSeverity.WARNING,
                message="candidate needs review before answer use",
            )
        ],
    )

    result = select_evidence_for_answer(
        make_bundle([ambiguous]),
        config=EvidenceSelectionConfig(allow_answer_with_caution=False),
    )

    assert result.decision == AnswerabilityDecision.NEEDS_REVIEW


def test_parent_text_rendered_only_as_auxiliary_context() -> None:
    """Selected caution context separates citable child text from parent_text."""
    caution = make_packet(
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )

    result = select_evidence_for_answer(
        make_bundle([caution]),
        config=EvidenceSelectionConfig(
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=True,
        ),
    )

    assert "Citable text:" in result.rendered_context
    assert "Auxiliary article context, not directly citable under this child citation:" in (
        result.rendered_context
    )
    assert result.rendered_context.index("Citation:") < result.rendered_context.index(
        "Citable text:"
    )


def test_unsafe_evidence_is_excluded_from_rendered_context() -> None:
    """Unsafe evidence can be rejected while safe evidence remains renderable."""
    safe = make_packet(chunk_id="safe", citation="Khoản 1, Điều 113, Bộ luật Lao động")
    unsafe = make_packet(
        rank=2,
        chunk_id="unsafe",
        citation=None,
        text="unsafe text should not render",
    )

    result = select_evidence_for_answer(make_bundle([safe, unsafe]))

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1
    assert result.rejected_count == 1
    assert "unsafe text should not render" not in result.rendered_context


def test_duplicate_evidence_is_not_reselected() -> None:
    """Selection also deduplicates by chunk_id if a bundle contains duplicates."""
    first = make_packet(rank=1, chunk_id="same")
    duplicate = make_packet(rank=2, chunk_id="same")

    result = select_evidence_for_answer(make_bundle([first, duplicate]))

    assert result.selected_count == 1
    assert result.rejected_count == 1
    assert EvidenceRejectionReason.DUPLICATE_EVIDENCE in result.rejected_evidence[0].reasons


def test_annual_leave_missing_exact_target_fallbacks_in_eval_mode() -> None:
    """Sibling Article 113 clauses cannot pass the exact-target evaluation gate."""
    sibling_clause = make_packet(
        rank=3,
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động (VBHN 2025)",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text=(
            "Điều 113. Nghỉ hằng năm\n"
            "1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm..."
        ),
    )
    expected = [
        ExpectedTarget(
            law_id="BLLD_VBHN",
            article_number="113",
            clause_number="1",
            point_label=None,
            match_level="clause",
        )
    ]
    risks = [
        EvidenceRiskFlag(
            code="child_provision_mismatch_under_expected_article",
            message="sibling clause retrieved under expected Article",
        )
    ]

    result = select_evidence_for_answer(
        make_bundle([sibling_clause]),
        config=EvidenceSelectionConfig(fallback_on_parent_context_only=False),
        expected_targets=expected,
        risk_flags=risks,
    )

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    codes = {reason.code for reason in result.fallback_reasons}
    assert FallbackReasonCode.EXACT_TARGET_MISSING_IN_EVAL_MODE in codes
    assert FallbackReasonCode.HIGH_CITATION_RISK in codes


def test_health_insurance_exact_point_evidence_allows_answer() -> None:
    """Exact point-level evidence can pass the evaluation-assisted gate."""
    packet = make_packet(
        law_id="LBHYT_VBHN",
        article_number="16",
        clause_number="3",
        point_label="d",
        citation="Điểm d, Khoản 3, Điều 16, Luật Bảo hiểm y tế",
        text="d) Trẻ em dưới 6 tuổi thì thẻ bảo hiểm y tế có giá trị sử dụng...",
        level="point",
        chunk_kind="point",
    )
    expected = [
        ExpectedTarget(
            law_id="LBHYT_VBHN",
            article_number="16",
            clause_number="3",
            point_label="d",
            match_level="point",
        )
    ]

    result = select_evidence_for_answer(make_bundle([packet]), expected_targets=expected)

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1


def test_article_level_evidence_allows_answer() -> None:
    """Article-level target can be satisfied by an article-level packet."""
    packet = make_packet(
        law_id="BLDS_2015",
        article_number="1",
        clause_number=None,
        point_label=None,
        level="article",
        chunk_kind="article",
        citation="Điều 1, Bộ luật Dân sự 2015",
        text="Điều 1. Phạm vi điều chỉnh...",
        parent_text="Điều 1. Phạm vi điều chỉnh...",
    )
    expected = [
        ExpectedTarget(
            law_id="BLDS_2015",
            article_number="1",
            clause_number=None,
            point_label=None,
            match_level="article",
        )
    ]

    result = select_evidence_for_answer(make_bundle([packet]), expected_targets=expected)

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1


def test_expected_target_safe_packet_is_selected_ahead_of_non_target_safe_packet() -> None:
    """Evaluation-mode selection keeps the selectable expected target in context."""
    non_target = make_packet(
        rank=1,
        chunk_id="article-11",
        law_id="BLDS_2015",
        article_number="11",
        clause_number=None,
        level="article",
        chunk_kind="article",
        citation="Điều 11, Bộ luật Dân sự 2015",
        text="Điều 11. Các phương thức bảo vệ quyền dân sự...",
        parent_text="Điều 11. Các phương thức bảo vệ quyền dân sự...",
    )
    target = make_packet(
        rank=6,
        chunk_id="article-2",
        law_id="BLDS_2015",
        article_number="2",
        clause_number=None,
        level="article",
        chunk_kind="article",
        citation="Điều 2, Bộ luật Dân sự 2015",
        text="Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự...",
        parent_text="Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự...",
    )
    expected = [
        ExpectedTarget(
            law_id="BLDS_2015",
            article_number="2",
            clause_number=None,
            point_label=None,
            match_level="article",
        )
    ]

    result = select_evidence_for_answer(
        make_bundle([non_target, target]),
        config=EvidenceSelectionConfig(max_selected_packets=1),
        expected_targets=expected,
    )

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1
    assert result.selected_evidence[0].chunk_id == "article-2"


def test_expected_target_caution_packet_can_be_selected_ahead_of_non_target_safe_packet() -> None:
    """A valid caution target is not displaced by unrelated safe evidence."""
    non_target = make_packet(
        rank=1,
        chunk_id="safe-other",
        law_id="OTHER",
        article_number="99",
        clause_number=None,
        level="article",
        chunk_kind="article",
        citation="Điều 99, Other",
        text="Điều 99. Nội dung khác.",
        parent_text="Điều 99. Nội dung khác.",
    )
    target = make_packet(
        rank=8,
        chunk_id="article-2-clause-1",
        law_id="BLDS_2015",
        article_number="2",
        clause_number="1",
        citation="Khoản 1, Điều 2, Bộ luật Dân sự 2015",
        text="1. Ở nước Cộng hòa xã hội chủ nghĩa Việt Nam, các quyền dân sự...",
        parent_text="Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự...",
    )
    expected = [
        ExpectedTarget(
            law_id="BLDS_2015",
            article_number="2",
            clause_number=None,
            point_label=None,
            match_level="article",
        )
    ]

    result = select_evidence_for_answer(
        make_bundle([non_target, target]),
        config=EvidenceSelectionConfig(
            max_selected_packets=1,
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=False,
        ),
        expected_targets=expected,
    )

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1
    assert result.selected_evidence[0].chunk_id == "article-2-clause-1"
    assert result.selected_evidence[0].safety_level == EvidenceSafetyLevel.CAUTION


def test_required_child_evidence_with_auxiliary_parent_context_passes_eval_gate() -> None:
    """A retrieved target child remains selectable when parent context is auxiliary."""
    target = make_packet(
        chunk_id="article-2-clause-1",
        law_id="BLDS_2015",
        article_number="2",
        clause_number="1",
        citation="Khoản 1, Điều 2, Bộ luật Dân sự 2015",
        text="1. Ở nước Cộng hòa xã hội chủ nghĩa Việt Nam, các quyền dân sự...",
        parent_text="Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự...",
    )
    expected = [
        ExpectedTarget(
            law_id="BLDS_2015",
            article_number="2",
            clause_number="1",
            point_label=None,
            match_level="clause",
        )
    ]

    result = select_evidence_for_answer(make_bundle([target]), expected_targets=expected)

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_count == 1
    assert result.selected_evidence[0].chunk_id == "article-2-clause-1"
    assert result.selected_evidence[0].citation_scope == CitationScope.CHILD_EXACT
    assert result.selected_evidence[0].has_auxiliary_context is True


def test_expected_target_sorting_does_not_treat_sibling_clause_as_match() -> None:
    """Annual-leave sibling clauses remain insufficient for Clause 1 targets."""
    sibling = make_packet(
        rank=1,
        chunk_id="article-113-clause-4",
        article_number="113",
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )
    other = make_packet(
        rank=2,
        chunk_id="other-safe",
        law_id="OTHER",
        article_number="1",
        clause_number=None,
        level="article",
        chunk_kind="article",
        citation="Điều 1, Other",
        text="Điều 1. Nội dung khác.",
        parent_text="Điều 1. Nội dung khác.",
    )
    expected = [
        ExpectedTarget(
            law_id="BLLD_VBHN",
            article_number="113",
            clause_number="1",
            point_label=None,
            match_level="clause",
        )
    ]

    result = select_evidence_for_answer(
        make_bundle([sibling, other]),
        config=EvidenceSelectionConfig(
            max_selected_packets=2,
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=False,
        ),
        expected_targets=expected,
    )

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert FallbackReasonCode.EXACT_TARGET_MISSING_IN_EVAL_MODE in {
        reason.code for reason in result.fallback_reasons
    }


def test_civil_rights_article_target_can_pass_when_article_two_packet_is_present() -> None:
    """Civil-rights Article 2 target can pass when selected evidence includes Article 2."""
    wrong_top = make_packet(
        rank=1,
        chunk_id="article-11",
        law_id="BLDS_2015",
        article_number="11",
        clause_number="1",
        citation="Khoản 1, Điều 11, Bộ luật Dân sự 2015",
        text="1. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự của mình.",
        parent_text="Điều 11. Các phương thức bảo vệ quyền dân sự...",
    )
    article_two = make_packet(
        rank=2,
        chunk_id="article-2",
        law_id="BLDS_2015",
        article_number="2",
        clause_number=None,
        level="article",
        chunk_kind="article",
        citation="Điều 2, Bộ luật Dân sự 2015",
        text="Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự...",
        parent_text="Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự...",
    )
    expected = [
        ExpectedTarget(
            law_id="BLDS_2015",
            article_number="2",
            clause_number=None,
            point_label=None,
            match_level="article",
        )
    ]

    result = select_evidence_for_answer(
        make_bundle([wrong_top, article_two]),
        config=EvidenceSelectionConfig(
            max_selected_packets=1,
            fallback_on_parent_context_only=False,
        ),
        expected_targets=expected,
    )

    assert result.decision == AnswerabilityDecision.ANSWER_ALLOWED
    assert result.selected_evidence[0].chunk_id == "article-2"


def test_rendered_context_includes_caution_warnings_when_selected() -> None:
    """Caution selected evidence renders safety issues for future review."""
    caution = make_packet(
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )

    result = select_evidence_for_answer(
        make_bundle([caution]),
        config=EvidenceSelectionConfig(
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=True,
        ),
    )

    assert "Safety issues:" in result.rendered_context
    assert "parent_context_auxiliary_only" in result.rendered_context
    assert SelectionWarningCode.CAUTION_EVIDENCE_SELECTED in {
        warning.code for warning in result.warnings
    }


def test_auxiliary_context_can_be_suppressed_in_rendered_context() -> None:
    """Config can keep selected caution evidence while hiding auxiliary context."""
    caution = make_packet(
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )

    result = select_evidence_for_answer(
        make_bundle([caution]),
        config=EvidenceSelectionConfig(
            fallback_on_parent_context_only=False,
            needs_review_on_all_evidence_caution=True,
            include_auxiliary_context_in_rendered_output=False,
        ),
    )

    assert "Auxiliary article context" not in result.rendered_context
    assert SelectionWarningCode.AUXILIARY_PARENT_CONTEXT_SUPPRESSED in {
        warning.code for warning in result.warnings
    }
