from __future__ import annotations

from src.api.schemas import LegalQARequest
from src.services.legal_qa_context import LegalQAContextPreparer


def test_context_preparer_keeps_recent_non_empty_messages() -> None:
    preparer = LegalQAContextPreparer(max_messages=3)
    request = LegalQARequest(
        question="  Câu hỏi hiện tại?  ",
        conversation_id="  conversation-1  ",
        conversation_context=[
            {"role": "user", "content": "Tin nhắn cũ"},
            {"role": "assistant", "content": "   "},
            {"role": "user", "content": "  Câu hỏi gần đây  "},
            {"role": "assistant", "content": "  Câu trả lời gần đây  "},
        ],
    )

    prepared = preparer.prepare(request)

    assert prepared.effective_question == "Câu hỏi hiện tại?"
    assert prepared.conversation_id == "conversation-1"
    assert prepared.message_count == 2
    assert [(message.role, message.content) for message in prepared.messages] == [
        ("user", "Câu hỏi gần đây"),
        ("assistant", "Câu trả lời gần đây"),
    ]
    assert prepared.compact_text == ("user: Câu hỏi gần đây\nassistant: Câu trả lời gần đây")


def test_context_preparer_does_not_treat_context_as_effective_question() -> None:
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question="Câu hỏi hiện tại?",
            conversation_context=[
                {"role": "user", "content": "Nội dung hội thoại không phải bằng chứng"}
            ],
        )
    )

    assert prepared.effective_question == "Câu hỏi hiện tại?"
    assert prepared.compact_text != prepared.effective_question
