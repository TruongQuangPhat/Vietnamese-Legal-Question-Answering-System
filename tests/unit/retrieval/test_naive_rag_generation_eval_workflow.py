"""Unit tests for the generation evaluation generation evaluation workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.retrieval.generation import (
    FALLBACK_ANSWER_VI,
    RagAnswerResult,
    RagCitation,
    UsedEvidence,
)
from src.retrieval.generation_evaluation import (
    GenerationEvalQuery,
    load_generation_eval_queries,
)
from src.retrieval.selection import AnswerabilityDecision
from src.retrieval.workflows import naive_rag_generation_eval


def test_load_generation_eval_queries_from_jsonl(tmp_path: Path) -> None:
    """The generation evaluation JSONL loader validates manual query records."""
    path = tmp_path / "queries.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "case-1",
                "query": "Câu hỏi pháp luật?",
                "allowed_decisions": ["fallback_required"],
                "expected_llm_called": False,
                "requires_citation_ids": False,
                "expected_language": "vi",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_generation_eval_queries(path)

    assert len(cases) == 1
    assert cases[0].id == "case-1"


def test_load_generation_eval_queries_accepts_review_metadata(tmp_path: Path) -> None:
    """Optional non-blocking review metadata remains schema-compatible."""
    path = tmp_path / "queries.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "review-case",
                "query": "Quyền dân sự được bảo vệ như thế nào?",
                "allowed_decisions": ["answer_allowed", "needs_review"],
                "expected_llm_called": None,
                "requires_citation_ids": True,
                "manual_review_required": True,
                "blocking": False,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    case = load_generation_eval_queries(path)[0]

    assert case.expected_llm_called is None
    assert case.manual_review_required is True
    assert case.blocking is False


@pytest.mark.asyncio
async def test_suite_calls_runner_once_per_case_and_aggregates() -> None:
    """Injected runner is called once per case without external dependencies."""
    cases = [_allowed_case(), _fallback_case()]
    calls: list[str] = []

    async def runner(case: GenerationEvalQuery) -> RagAnswerResult:
        calls.append(case.id)
        if case.expected_llm_called:
            return _result(
                decision=AnswerabilityDecision.ANSWER_ALLOWED,
                answer="Nội dung hợp lệ [E1].",
                llm_called=True,
                citations=[_citation()],
            )
        return _result(
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            answer=FALLBACK_ANSWER_VI,
            llm_called=False,
            citations=[],
        )

    report = await naive_rag_generation_eval.run_generation_eval_suite(
        cases,
        runner,
        dataset_path=Path("queries.jsonl"),
        collection_name="collection",
        vector_name="dense",
        top_k=20,
        provider="openrouter",
        model="test/model",
    )

    assert calls == ["allowed", "fallback"]
    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.status == "expanded_generation_eval_passed"


@pytest.mark.asyncio
async def test_suite_rejects_empty_case_list() -> None:
    """Generation evaluation requires at least one case."""

    async def runner(case: GenerationEvalQuery) -> RagAnswerResult:
        raise AssertionError(f"runner must not be called: {case.id}")

    with pytest.raises(ValueError, match="at least one case"):
        await naive_rag_generation_eval.run_generation_eval_suite(
            [],
            runner,
            dataset_path=Path("queries.jsonl"),
            collection_name="collection",
            vector_name="dense",
            top_k=20,
            provider="openrouter",
            model="test/model",
        )


@pytest.mark.asyncio
async def test_report_write_does_not_expose_environment_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake environment credentials are absent from the serialized report."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")

    async def runner(case: GenerationEvalQuery) -> RagAnswerResult:
        return _result(
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            answer="Nội dung hợp lệ [E1].",
            llm_called=True,
            citations=[_citation()],
        )

    report = await naive_rag_generation_eval.run_generation_eval_suite(
        [_allowed_case()],
        runner,
        dataset_path=Path("queries.jsonl"),
        collection_name="collection",
        vector_name="dense",
        top_k=20,
        provider="openrouter",
        model="test/model",
    )
    output = tmp_path / "report.json"

    naive_rag_generation_eval.write_report(output, report)

    serialized = output.read_text(encoding="utf-8")
    assert "test-openrouter-key" not in serialized
    assert json.loads(serialized)["citation_id_coverage_rate"] == 1.0


@pytest.mark.asyncio
async def test_suite_can_include_evidence_previews_without_external_calls() -> None:
    """Opt-in preview mode serializes selected child evidence from fake results."""

    async def runner(case: GenerationEvalQuery) -> RagAnswerResult:
        del case
        return _result(
            decision=AnswerabilityDecision.ANSWER_ALLOWED,
            answer="Nội dung hợp lệ [E1].",
            llm_called=True,
            citations=[_citation()],
            used_evidence=[
                UsedEvidence(
                    evidence_id="E1",
                    packet_id="P1",
                    citation="Điều 1",
                    score=0.9,
                    safe_citable_text="Nội dung Điều 1.",
                    citation_scope="child_exact",
                    safety_level="safe",
                    is_directly_citable=True,
                )
            ],
        )

    report = await naive_rag_generation_eval.run_generation_eval_suite(
        [_allowed_case()],
        runner,
        dataset_path=Path("queries.jsonl"),
        collection_name="collection",
        vector_name="dense",
        top_k=20,
        provider="openrouter",
        model="test/model",
        include_evidence_preview=True,
        evidence_preview_chars=500,
    )

    assert report.evidence_preview_total_count == 1
    assert report.cases[0].evidence_previews[0].text_preview == "Nội dung Điều 1."


def test_parser_accepts_documented_generation_eval_flags() -> None:
    """The workflow parser accepts the documented live command."""
    args = naive_rag_generation_eval.build_arg_parser().parse_args(
        [
            "--queries",
            "data/eval/manual_naive_rag_generation_queries.jsonl",
            "--collection-name",
            "vnlaw_chunks_bgem3_v1_full",
            "--url",
            "http://localhost:6333",
            "--top-k",
            "20",
            "--device",
            "cpu",
            "--provider",
            "openrouter",
            "--model",
            "google/gemini-2.5-flash-lite",
            "--output",
            "artifacts/reports/retrieval/naive_rag_generation_eval.json",
            "--include-evidence-preview",
            "--evidence-preview-chars",
            "500",
        ]
    )

    assert args.model == "google/gemini-2.5-flash-lite"
    assert args.top_k == 20
    assert args.include_evidence_preview is True
    assert args.evidence_preview_chars == 500


def test_script_is_thin_workflow_wrapper() -> None:
    """The top-level generation evaluation script contains no evaluation business logic."""
    source = Path("scripts/retrieval/evaluate_naive_rag_generation.py").read_text(encoding="utf-8")

    assert "from src.retrieval.workflows.naive_rag_generation_eval import main" in source
    assert "def build_arg_parser" not in source
    assert "async def run_" not in source


def _allowed_case() -> GenerationEvalQuery:
    return GenerationEvalQuery(
        id="allowed",
        query="Bộ luật Dân sự điều chỉnh những quan hệ nào?",
        allowed_decisions=[AnswerabilityDecision.ANSWER_ALLOWED],
        expected_llm_called=True,
        requires_citation_ids=True,
    )


def _fallback_case() -> GenerationEvalQuery:
    return GenerationEvalQuery(
        id="fallback",
        query="Người lao động được nghỉ hằng năm bao nhiêu ngày?",
        allowed_decisions=[AnswerabilityDecision.FALLBACK_REQUIRED],
        expected_llm_called=False,
        requires_citation_ids=False,
    )


def _result(
    *,
    decision: AnswerabilityDecision,
    answer: str,
    llm_called: bool,
    citations: list[RagCitation],
    used_evidence: list[UsedEvidence] | None = None,
) -> RagAnswerResult:
    return RagAnswerResult(
        query="Câu hỏi",
        decision=decision,
        answer=answer,
        citations=citations,
        used_evidence=used_evidence or [],
        fallback_reasons=[],
        selection_warnings=[],
        citation_issues=[],
        retrieval_metadata={},
        selection_metadata={},
        generation_metadata={},
        llm_called=llm_called,
        model="test/model",
        provider="mock",
        errors=[],
    )


def _citation() -> RagCitation:
    return RagCitation(
        evidence_id="E1",
        packet_id="P1",
        citation="Điều 1",
        source_url="https://thuvienphapluat.vn/test",
    )
