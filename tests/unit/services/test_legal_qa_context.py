from __future__ import annotations

import pytest

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


def test_no_context_keeps_current_retrieval_question() -> None:
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(question="Vậy hợp đồng xác định thời hạn thì sao?")
    )

    assert prepared.retrieval_question == prepared.original_question
    assert prepared.context_used is False
    assert prepared.follow_up_detected is True


def test_non_follow_up_question_does_not_use_context() -> None:
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=(
                "Điều kiện để người lao động được hưởng trợ cấp thất nghiệp "
                "bao gồm những nội dung nào?"
            ),
            conversation_context=[{"role": "user", "content": "Câu hỏi trước không liên quan"}],
        )
    )

    assert prepared.follow_up_detected is False
    assert prepared.context_used is False
    assert prepared.retrieval_question == prepared.original_question


def test_follow_up_question_uses_most_recent_user_topic_anchor() -> None:
    prior_question = "Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?"
    current_question = "Vậy hợp đồng xác định thời hạn thì sao?"
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=current_question,
            conversation_context=[
                {"role": "user", "content": prior_question},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    assert prepared.follow_up_detected is True
    assert prepared.context_used is True
    assert prepared.retrieval_question == f"{prior_question} {current_question}"


@pytest.mark.parametrize(
    "question",
    [
        "Vậy hợp đồng xác định thời hạn thì sao?",
        "Còn hợp đồng không xác định thời hạn?",
        "Trường hợp đó có cần báo trước không?",
        "Như trên thì người lao động có được trợ cấp không?",
        "Nếu vậy thì công ty có phải bồi thường không?",
        "Vậy trường hợp này thì sao?",
        "Còn nếu chưa đủ tuổi?",
        "Thế có bị phạt không?",
        "Cái đó áp dụng cho ai?",
        "Như trên thì có được không?",
    ],
)
def test_explicit_follow_up_markers_use_prior_user_anchor(question: str) -> None:
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=question,
            conversation_context=[
                {
                    "role": "user",
                    "content": "Người lao động đơn phương chấm dứt hợp đồng khi nào?",
                }
            ],
        )
    )

    assert prepared.follow_up_detected is True
    assert prepared.context_used is True
    assert prepared.retrieval_question.endswith(question)


@pytest.mark.parametrize(
    "question",
    [
        "Điều kiện kết hôn là gì?",
        "Bảo hiểm y tế trẻ em?",
        "Nghỉ phép năm bao nhiêu ngày?",
        "Trẻ em dưới 6 tuổi có được cấp thẻ bảo hiểm y tế không?",
        "Thời hiệu khởi kiện là gì?",
        "Ly hôn thuận tình cần gì?",
        "Thế chấp tài sản là gì?",
        "Hợp đồng lao động là gì?",
        "Tội trộm cắp tài sản xử lý thế nào?",
    ],
)
def test_short_independent_questions_do_not_use_prior_context(question: str) -> None:
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=question,
            conversation_context=[
                {
                    "role": "user",
                    "content": "Người lao động đơn phương chấm dứt hợp đồng khi nào?",
                }
            ],
        )
    )

    assert prepared.follow_up_detected is False
    assert prepared.context_used is False
    assert prepared.retrieval_question == question


def test_short_standalone_question_does_not_inherit_unrelated_marriage_context() -> None:
    question = "Nghỉ phép năm bao nhiêu ngày?"
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=question,
            conversation_context=[
                {"role": "user", "content": "Điều kiện kết hôn là gì?"},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    assert prepared.follow_up_detected is False
    assert prepared.context_used is False
    assert prepared.retrieval_question == question


def test_short_standalone_question_does_not_inherit_health_insurance_context() -> None:
    question = "Điều kiện kết hôn là gì?"
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=question,
            conversation_context=[
                {"role": "user", "content": "Bảo hiểm y tế trẻ em?"},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    assert prepared.follow_up_detected is False
    assert prepared.context_used is False
    assert prepared.retrieval_question == question


def test_true_follow_up_can_use_annual_leave_context() -> None:
    prior_question = "Nghỉ phép năm bao nhiêu ngày?"
    current_question = "Vậy có được nghỉ thêm không?"
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=current_question,
            conversation_context=[
                {"role": "user", "content": prior_question},
                {"role": "assistant", "content": "Câu trả lời trước"},
            ],
        )
    )

    assert prepared.follow_up_detected is True
    assert prepared.context_used is True
    assert prepared.retrieval_question == f"{prior_question} {current_question}"


def test_ambiguous_question_without_context_reference_stays_standalone() -> None:
    question = "Có cần giấy tờ gì?"
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=question,
            conversation_context=[
                {"role": "user", "content": "Điều kiện kết hôn là gì?"},
            ],
        )
    )

    assert prepared.follow_up_detected is False
    assert prepared.context_used is False
    assert prepared.retrieval_question == question


def test_assistant_only_context_is_not_used_as_topic_anchor() -> None:
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question="Vậy thì sao?",
            conversation_context=[
                {"role": "assistant", "content": "Nội dung trợ lý không phải nguồn luật"}
            ],
        )
    )

    assert prepared.follow_up_detected is True
    assert prepared.context_used is False
    assert prepared.retrieval_question == "Vậy thì sao?"


def test_prepared_retrieval_question_is_bounded_and_preserves_current_question() -> None:
    current_question = f"Vậy {'q' * 2495}"
    prepared = LegalQAContextPreparer().prepare(
        LegalQARequest(
            question=current_question,
            conversation_context=[{"role": "user", "content": "a" * 2000}],
        )
    )

    assert prepared.context_used is True
    assert len(prepared.retrieval_question) == 4000
    assert prepared.retrieval_question.endswith(current_question)
