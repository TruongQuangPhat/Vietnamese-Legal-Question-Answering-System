"""Unit tests for Phase 9A.2 evidence safety and context assembly."""

from __future__ import annotations

from src.retrieval.evidence import (
    CitationScope,
    ContextAssemblyConfig,
    EvidenceSafetyLevel,
    ParentContextPolicy,
    build_evidence_bundle,
    build_evidence_packet,
)
from src.retrieval.models import RetrievalFilters, RetrievalResult, RetrievedChunk


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
    parent_text_hash: str | None = "parent-113",
    source_url: str | None = "https://thuvienphapluat.vn/example",
    source_domain: str | None = "thuvienphapluat.vn",
    is_empty_or_repealed: bool | None = None,
    is_source_unit_repealed: bool | None = None,
) -> RetrievedChunk:
    """Build one retrieved chunk for evidence tests."""
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
        parent_text_hash=parent_text_hash,
        source_url=source_url,
        source_domain=source_domain,
        metadata={},
        warnings=[],
        is_empty_or_repealed=is_empty_or_repealed,
        is_source_unit_repealed=is_source_unit_repealed,
    )


def make_result(chunks: list[RetrievedChunk]) -> RetrievalResult:
    """Build one retrieval result for evidence bundle tests."""
    return RetrievalResult(
        query="test",
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
        top_k=20,
        elapsed_ms=1.0,
        query_vector_dimension=1024,
        filters=RetrievalFilters(),
        results=chunks,
    )


def test_article_level_chunk_with_citation_is_safe() -> None:
    """Article chunks can safely cite article-level text."""
    chunk = make_chunk(
        level="article",
        chunk_kind="article",
        clause_number=None,
        text="Điều 8. Điều kiện kết hôn...",
        parent_text="Điều 8. Điều kiện kết hôn...",
        citation="Điều 8, Luật Hôn nhân và gia đình",
    )

    packet = build_evidence_packet(chunk)

    assert packet.safety_level == EvidenceSafetyLevel.SAFE
    assert packet.citation_scope == CitationScope.ARTICLE_CONTEXT
    assert packet.parent_context_policy == ParentContextPolicy.CITABLE_ARTICLE_CONTEXT
    assert packet.safe_citable_text is not None
    assert packet.auxiliary_context is None


def test_clause_level_chunk_without_parent_text_is_safe() -> None:
    """Child text with complete citation metadata is directly citable."""
    packet = build_evidence_packet(make_chunk(parent_text=None))

    assert packet.safety_level == EvidenceSafetyLevel.SAFE
    assert packet.citation_scope == CitationScope.CHILD_EXACT
    assert packet.parent_context_policy == ParentContextPolicy.ABSENT
    assert packet.safe_citable_text is not None


def test_clause_level_chunk_with_broader_parent_text_is_caution() -> None:
    """Broader parent Article context is auxiliary, not child-citable."""
    chunk = make_chunk(
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động (VBHN 2025)",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text=(
            "Điều 113. Nghỉ hằng năm\n"
            "1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm...\n"
            "4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm."
        ),
    )

    packet = build_evidence_packet(chunk)

    assert packet.safety_level == EvidenceSafetyLevel.CAUTION
    assert packet.citation_scope == CitationScope.UNSAFE_PARENT_CONTEXT
    assert packet.parent_context_policy == ParentContextPolicy.AUXILIARY_ONLY
    assert packet.safe_citable_text is not None
    assert packet.auxiliary_context is not None
    assert "parent_context_auxiliary_only" in {issue.code for issue in packet.safety_issues}


def test_point_level_chunk_with_broader_parent_text_is_caution() -> None:
    """Point chunks also treat broader Article text as auxiliary only."""
    packet = build_evidence_packet(
        make_chunk(
            level="point",
            chunk_kind="point",
            clause_number="1",
            point_label="a",
            citation="Điểm a, Khoản 1, Điều 113, Bộ luật Lao động",
            text="a) 12 ngày làm việc đối với người làm công việc trong điều kiện bình thường;",
            parent_text="Điều 113. Nghỉ hằng năm\n1. a) 12 ngày...\nb) 14 ngày...",
        )
    )

    assert packet.safety_level == EvidenceSafetyLevel.CAUTION
    assert packet.citation_scope == CitationScope.UNSAFE_PARENT_CONTEXT
    assert packet.auxiliary_context is not None


def test_missing_critical_metadata_is_unsafe() -> None:
    """Missing citation, law_id, source URL, or child text blocks citation use."""
    for field_name, kwargs in [
        ("missing_citation", {"citation": None}),
        ("missing_law_id", {"law_id": None}),
        ("missing_source_url", {"source_url": None}),
        ("missing_child_text", {"text": None}),
    ]:
        packet = build_evidence_packet(
            make_chunk(**kwargs),
            config=ContextAssemblyConfig(min_safety_level=EvidenceSafetyLevel.UNSAFE),
        )

        assert packet.safety_level == EvidenceSafetyLevel.UNSAFE
        assert field_name in {issue.code for issue in packet.safety_issues}


def test_empty_or_repealed_flags_are_unsafe() -> None:
    """Known empty/repealed flags prevent direct evidence use."""
    packet = build_evidence_packet(
        make_chunk(is_empty_or_repealed=True, is_source_unit_repealed=True),
        config=ContextAssemblyConfig(min_safety_level=EvidenceSafetyLevel.UNSAFE),
    )

    codes = {issue.code for issue in packet.safety_issues}
    assert packet.safety_level == EvidenceSafetyLevel.UNSAFE
    assert "empty_or_repealed_chunk" in codes
    assert "source_unit_repealed" in codes


def test_duplicate_chunk_id_is_deduplicated() -> None:
    """Evidence bundles keep only the first repeated chunk_id."""
    first = make_chunk(rank=1, chunk_id="same")
    duplicate = make_chunk(rank=2, chunk_id="same", score=0.8)

    bundle = build_evidence_bundle(make_result([first, duplicate]))

    assert bundle.total_packets == 1
    assert bundle.packets[0].rank == 1


def test_repeated_parent_text_is_deduplicated_for_sibling_chunks() -> None:
    """Sibling chunks can omit repeated auxiliary Article context in rendering."""
    parent = "Điều 113. Nghỉ hằng năm\n1. Nội dung...\n4. Nội dung..."
    first = make_chunk(rank=1, chunk_id="c1", clause_number="4", parent_text=parent)
    second = make_chunk(rank=2, chunk_id="c2", clause_number="6", parent_text=parent)

    bundle = build_evidence_bundle(make_result([first, second]))

    assert bundle.total_packets == 2
    assert bundle.packets[0].auxiliary_context is not None
    assert bundle.packets[1].auxiliary_context is None
    assert bundle.packets[1].parent_context_policy == ParentContextPolicy.DEDUPLICATED


def test_render_context_separates_citable_text_from_auxiliary_context() -> None:
    """Rendered context keeps citation adjacent to child citable text."""
    chunk = make_chunk(
        rank=1,
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text="Điều 113. Nghỉ hằng năm\n1. Người lao động được nghỉ...",
    )
    bundle = build_evidence_bundle(make_result([chunk]))

    rendered = bundle.render_context()

    assert "Citation: Khoản 4, Điều 113, Bộ luật Lao động" in rendered
    assert "Citable text:" in rendered
    assert "Auxiliary article context, not directly citable under this child citation:" in rendered
    assert rendered.index("Citation:") < rendered.index("Citable text:")


def test_truncated_text_is_marked() -> None:
    """Truncated citable and parent text carry an explicit marker and issue."""
    chunk = make_chunk(
        text="x" * 80,
        parent_text="y" * 120,
    )
    packet = build_evidence_packet(
        chunk,
        config=ContextAssemblyConfig(max_child_chars=30, max_parent_chars=40),
    )

    assert packet.child_text is not None
    assert packet.child_text.truncated is True
    assert packet.child_text.text.endswith("...[TRUNCATED]")
    assert packet.parent_text is not None
    assert packet.parent_text.truncated is True
    codes = {issue.code for issue in packet.safety_issues}
    assert "child_text_truncated" in codes
    assert "parent_text_truncated" in codes


def test_annual_leave_sibling_clause_parent_text_is_not_directly_citable() -> None:
    """Article 113 sibling Clause context remains auxiliary, not child-citable."""
    chunk = make_chunk(
        rank=3,
        clause_number="4",
        citation="Khoản 4, Điều 113, Bộ luật Lao động (VBHN 2025)",
        text="4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm.",
        parent_text=(
            "Điều 113. Nghỉ hằng năm\n"
            "1. Người lao động làm việc đủ 12 tháng thì được nghỉ hằng năm, hưởng nguyên lương...\n"
            "4. Người sử dụng lao động có trách nhiệm quy định lịch nghỉ hằng năm."
        ),
    )

    packet = build_evidence_packet(chunk)

    assert packet.safety_level == EvidenceSafetyLevel.CAUTION
    assert packet.citation_scope == CitationScope.UNSAFE_PARENT_CONTEXT
    assert packet.parent_context_policy == ParentContextPolicy.AUXILIARY_ONLY
    assert packet.safe_citable_text is not None
    assert "Khoản 4" in (packet.citation or "")
    assert packet.auxiliary_context is not None
    assert "đủ 12 tháng" in packet.auxiliary_context.text
    assert "đủ 12 tháng" not in packet.safe_citable_text.text
