"""Prompt construction for fallback-aware Naive RAG."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.retrieval.selection import (
    AnswerabilityDecision,
    EvidenceSelectionResult,
    SelectedEvidence,
)


class PromptEvidence(BaseModel):
    """One selected evidence item exposed to the LLM with an internal anchor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(..., pattern=r"^E[1-9][0-9]*$")
    packet_id: str
    chunk_id: str | None = None
    citation: str | None = None
    law_id: str | None = None
    law_title: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    source_url: str | None = None
    score: float
    citation_scope: str | None = None
    safety_level: str | None = None
    is_directly_citable: bool = True
    citable_text: str
    auxiliary_context: str | None = None


class RagPrompt(BaseModel):
    """Rendered prompt and evidence mapping used for one LLM generation call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_message: str
    user_message: str
    evidence: list[PromptEvidence] = Field(default_factory=list)


def build_naive_rag_prompt(
    *,
    query: str,
    selection_result: EvidenceSelectionResult,
    include_auxiliary_context: bool = True,
) -> RagPrompt:
    """Build a legal QA prompt from selected evidence only.

    Args:
        query: User legal question.
        selection_result: Evidence gate output. Only ``selected_evidence`` is
            used; rejected and unsafe evidence are intentionally ignored.
        include_auxiliary_context: Whether auxiliary parent Article context is
            shown in a non-citable section.

    Returns:
        Prompt with internal citation IDs ``[E1]``, ``[E2]``, ... mapped to the
        selected evidence packets.

    Raises:
        ValueError: If no selected evidence has citable text.
    """
    evidence_items = [
        _prompt_evidence(index, selected, include_auxiliary_context=include_auxiliary_context)
        for index, selected in enumerate(selection_result.selected_evidence, start=1)
        if selected.packet.safe_citable_text is not None
    ]
    if not evidence_items:
        raise ValueError("cannot build a RAG prompt without selected citable evidence")

    system_message = (
        "Bạn là trợ lý hỗ trợ nghiên cứu pháp luật Việt Nam. "
        "Bạn chỉ được trả lời dựa trên phần Citable evidence được cung cấp. "
        "Chỉ trả lời đúng phạm vi câu hỏi và bỏ qua quy định chỉ liên quan gián tiếp. "
        "Không bắt buộc dùng mọi bằng chứng đã chọn; chỉ dùng bằng chứng trực tiếp hỗ trợ câu trả lời. "
        "Mỗi nhận định pháp lý phải có mã trích dẫn dạng [E1], [E2]. "
        "Không trình bày danh sách đầy đủ nếu bằng chứng không chứng minh đầy đủ danh sách. "
        "Không bịa luật, điều, khoản, điểm, thủ tục, mức phạt hoặc nguồn. "
        "Không trích dẫn mã không có trong bằng chứng. "
        "Không xem Auxiliary context là căn cứ trích dẫn trực tiếp. "
        "Nếu bằng chứng không đủ, hãy nói rõ là bằng chứng chưa đủ. "
        "Nếu yêu cầu được đánh dấu cần thận trọng, hãy nêu rõ giới hạn bằng chứng "
        "trước khi trả lời và chỉ trả lời trong phạm vi bằng chứng đó. "
        "Trả lời bằng tiếng Việt và không thay thế tư vấn pháp lý chuyên nghiệp."
    )
    caution_requirement = (
        "- Bằng chứng được chọn yếu hoặc cần thận trọng; mở đầu bằng một lưu ý ngắn "
        "rằng câu trả lời chỉ dựa trên bằng chứng hiện có.\n"
        if selection_result.decision == AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED
        else ""
    )
    user_message = "\n\n".join(
        [
            "Question:",
            query.strip(),
            "Citable evidence:",
            "\n\n".join(_render_citable_evidence(item) for item in evidence_items),
            _render_auxiliary_context(evidence_items),
            (
                "Answer requirements:\n"
                f"{caution_requirement}"
                "- Trả lời ngắn gọn, có cấu trúc.\n"
                "- Chỉ trả lời vấn đề pháp lý được hỏi; không mở rộng sang quy định liên quan gián tiếp.\n"
                "- Không dùng mọi [E#] chỉ vì chúng được cung cấp; ưu tiên tập bằng chứng nhỏ nhất đủ trả lời.\n"
                "- Mỗi câu chứa nhận định pháp lý phải có ít nhất một mã [E#].\n"
                "- Chỉ dùng các mã [E#] đã cung cấp.\n"
                '- Không dùng cách diễn đạt đầy đủ như "bao gồm" hoặc "gồm các điều kiện sau" '
                "nếu bằng chứng không bao phủ toàn bộ danh sách.\n"
                "- Nếu bằng chứng chỉ hỗ trợ một phần danh sách, nói rõ giới hạn đó và không tự bổ sung phần còn thiếu.\n"
                "- Ưu tiên luật/điều trực tiếp khớp câu hỏi; tránh mở rộng sang luật khác, định nghĩa, "
                "ngoại lệ, thủ tục hoặc trường hợp đặc biệt nếu không được hỏi hoặc không bắt buộc.\n"
                "- Chỉ trích dẫn [E#] trực tiếp hỗ trợ nhận định; bỏ qua bằng chứng chỉ liên quan.\n"
                "- Không dùng Auxiliary context làm căn cứ trích dẫn trực tiếp."
            ),
        ]
    )
    return RagPrompt(
        system_message=system_message,
        user_message=user_message,
        evidence=evidence_items,
    )


def _prompt_evidence(
    index: int,
    selected: SelectedEvidence,
    *,
    include_auxiliary_context: bool,
) -> PromptEvidence:
    packet = selected.packet
    if packet.safe_citable_text is None:
        raise ValueError(f"selected packet {packet.packet_id} has no citable text")
    return PromptEvidence(
        evidence_id=f"E{index}",
        packet_id=packet.packet_id,
        chunk_id=packet.chunk_id,
        citation=packet.citation,
        law_id=packet.law_id,
        law_title=packet.law_title,
        article_number=packet.article_number,
        clause_number=packet.clause_number,
        point_label=packet.point_label,
        source_url=packet.source_url,
        score=selected.score,
        citation_scope=selected.citation_scope.value,
        safety_level=selected.safety_level.value,
        is_directly_citable=True,
        citable_text=packet.safe_citable_text.text,
        auxiliary_context=(
            packet.auxiliary_context.text
            if include_auxiliary_context and packet.auxiliary_context is not None
            else None
        ),
    )


def _render_citable_evidence(item: PromptEvidence) -> str:
    lines = [
        f"[{item.evidence_id}]",
        f"Citation: {item.citation or 'MISSING'}",
        f"Law ID: {item.law_id or 'MISSING'}",
        f"Source URL: {item.source_url or 'MISSING'}",
        f"Retrieval Score: {item.score:.6f}",
        "Text:",
        item.citable_text,
    ]
    return "\n".join(lines)


def _render_auxiliary_context(evidence_items: list[PromptEvidence]) -> str:
    auxiliary_blocks = [
        f"[{item.evidence_id}] Auxiliary context, not directly citable:\n{item.auxiliary_context}"
        for item in evidence_items
        if item.auxiliary_context
    ]
    if not auxiliary_blocks:
        return "Auxiliary context, not directly citable:\nNone."
    return "Auxiliary context, not directly citable:\n" + "\n\n".join(auxiliary_blocks)
