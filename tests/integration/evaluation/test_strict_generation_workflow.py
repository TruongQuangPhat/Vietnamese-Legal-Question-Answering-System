"""Integration tests for strict generation evaluation workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluation import (
    analyze_evidence_selection_diagnostics,
    analyze_strict_generation_errors,
    run_strict_generation_evaluation,
)
from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    ExpectedDecision,
    FallbackReason,
    LegalDomain,
    QuestionType,
    ReviewStatus,
)
from src.evaluation.benchmark.loader import BenchmarkFileSet
from src.evaluation.benchmark.schemas import BenchmarkQuery
from src.evaluation.benchmark.strict_generation_evaluation import (
    StrictGenerationPaths,
    aggregate_strict_generation_metrics,
    evaluate_strict_generation_query,
    write_strict_generation_outputs,
)
from src.retrieval.evaluation import ExpectedTarget
from src.retrieval.generation import RagGenerationConfig
from src.retrieval.llm_client import LLMResponse, MockLLMClient
from src.retrieval.models import RetrievalResult, RetrievedChunk
from src.retrieval.rag_pipeline import RagRetrieverProtocol
from src.retrieval.selection import EvidenceSelectionConfig


class FakeRetriever(RagRetrieverProtocol):
    """Return a fixed retrieval result without external services."""

    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int | None, str | None]] = []

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        self.calls.append((query, top_k, collection_name))
        return self.result


@pytest.mark.asyncio
async def test_strict_generation_workflow_uses_llm_only_for_answerable_case(
    tmp_path: Path,
) -> None:
    """Strict generation evaluates answerable and fallback-required cases safely."""
    answer_retriever = FakeRetriever(_retrieval_result([_chunk()]))
    fallback_retriever = FakeRetriever(_retrieval_result([_chunk()]))
    llm = MockLLMClient([_llm_response("Quyền dân sự được bảo vệ theo luật [E1].")])
    generation_config = RagGenerationConfig(fail_on_invalid_citation=True)
    selection_config = EvidenceSelectionConfig()

    answer_case = await evaluate_strict_generation_query(
        query=_query("answer-case"),
        split="development",
        retriever=answer_retriever,
        llm_client=llm,
        generation_config=generation_config,
        selection_config=selection_config,
        collection_name="fixture_collection",
        final_top_k=10,
        expected_targets=[
            ExpectedTarget(
                law_id="BLDS_2015",
                article_number="2",
                clause_number=None,
                point_label=None,
                match_level="article",
            )
        ],
        judgments=[],
        groups=[],
    )
    fallback_case = await evaluate_strict_generation_query(
        query=_query(
            "fallback-case",
            expected_decision=ExpectedDecision.FALLBACK_REQUIRED,
            question_types=[QuestionType.FALLBACK],
            fallback_reason=FallbackReason.UNSAFE_AMBIGUITY,
        ),
        split="development",
        retriever=fallback_retriever,
        llm_client=llm,
        generation_config=generation_config,
        selection_config=selection_config,
        collection_name="fixture_collection",
        final_top_k=10,
        expected_targets=[],
        judgments=[],
        groups=[],
    )
    invalid_llm = MockLLMClient([_llm_response("Câu trả lời viện dẫn sai [E99].")])
    invalid_case = await evaluate_strict_generation_query(
        query=_query("invalid-citation-case"),
        split="development",
        retriever=FakeRetriever(_retrieval_result([_chunk()])),
        llm_client=invalid_llm,
        generation_config=generation_config,
        selection_config=selection_config,
        collection_name="fixture_collection",
        final_top_k=10,
        expected_targets=[
            ExpectedTarget(
                law_id="BLDS_2015",
                article_number="2",
                clause_number=None,
                point_label=None,
                match_level="article",
            )
        ],
        judgments=[],
        groups=[],
    )

    assert len(llm.requests) == 1
    assert answer_case["llm_called"] is True
    assert answer_case["pipeline_decision"] == "answer_allowed"
    assert answer_case["citation_guard_result"]["citation_id_valid"] is True
    assert fallback_case["llm_called"] is False
    assert fallback_case["pipeline_decision"] == "fallback_required"
    assert "exact_target_missing_in_eval_mode" in fallback_case["fallback_reasons"]
    assert invalid_case["pipeline_decision"] == "fallback_required"
    assert invalid_case["generation_error"] == "generated answer cited unknown evidence ID [E99]"

    held_out_case = dict(answer_case)
    held_out_case["query_id"] = "held-out-answer-case"
    held_out_case["split"] = "held_out_test"
    cases = [answer_case, fallback_case, invalid_case, held_out_case]
    metrics = aggregate_strict_generation_metrics(cases)
    assert {
        "decision_accuracy",
        "answer_allowed_answer_rate",
        "fallback_required_fallback_rate",
        "citation_id_validity_rate",
        "retrieval_error_count",
        "generation_error_count",
    } <= metrics.keys()
    assert metrics["retrieval_error_count"] == 0
    assert metrics["generation_error_count"] == 1

    paths = _strict_paths(tmp_path)
    write_strict_generation_outputs(
        paths=paths,
        case_results=cases,
        benchmark_version="v0.1.0",
        retrieval_manifest=_retrieval_manifest(),
        generation_config=generation_config,
        selection_config=selection_config,
        provider="mock",
        model="mock-model",
        command=["pytest", "strict_generation_workflow"],
    )
    assert {path.name for path in paths.output_dir.iterdir()} == {
        "baseline_manifest.json",
        "metrics_all.json",
        "metrics_development.json",
        "metrics_held_out_test.json",
        "breakdowns.json",
        "case_results.jsonl",
        "generation_summary.md",
        "comparison.json",
        "comparison.md",
    }
    assert all(path.is_relative_to(tmp_path) for path in paths.output_dir.iterdir())


def test_evaluation_cli_help_smoke_does_not_load_runtime_dependencies(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Evaluation script help exits before constructing real clients."""
    modules = [
        run_strict_generation_evaluation,
        analyze_strict_generation_errors,
        analyze_evidence_selection_diagnostics,
    ]

    for module in modules:
        with pytest.raises(SystemExit) as exc_info:
            module.main(["--help"])
        assert exc_info.value.code == 0

    output = capsys.readouterr().out
    assert "usage:" in output


def _chunk() -> RetrievedChunk:
    """Build one citable child evidence candidate."""
    return RetrievedChunk(
        rank=1,
        score=1.0,
        chunk_id="chunk-article-2",
        law_id="BLDS_2015",
        law_name="Bộ luật Dân sự 2015",
        level="clause",
        chunk_kind="clause_level",
        article_number="2",
        clause_number="1",
        citation="Bộ luật Dân sự 2015, Khoản 1, Điều 2",
        hierarchy_path="Bộ luật Dân sự 2015 / Điều 2 / Khoản 1",
        text="Quyền dân sự được công nhận, tôn trọng, bảo vệ và bảo đảm.",
        parent_text=(
            "Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự\n"
            "1. Quyền dân sự được công nhận, tôn trọng, bảo vệ và bảo đảm."
        ),
        source_url="https://thuvienphapluat.vn/example",
        source_domain="thuvienphapluat.vn",
        metadata={"is_empty_or_repealed": False, "is_source_unit_repealed": False},
    )


def _retrieval_result(chunks: list[RetrievedChunk]) -> RetrievalResult:
    """Build a typed retrieval result from tiny in-memory chunks."""
    return RetrievalResult(
        query="Quyền dân sự được bảo vệ như thế nào?",
        collection_name="fixture_collection",
        vector_name="dense",
        top_k=10,
        elapsed_ms=1.0,
        query_vector_dimension=3,
        results=chunks,
        issues=[],
    )


def _query(
    query_id: str,
    *,
    expected_decision: ExpectedDecision = ExpectedDecision.ANSWER_ALLOWED,
    question_types: list[QuestionType] | None = None,
    fallback_reason: FallbackReason | None = None,
) -> BenchmarkQuery:
    """Build a tiny benchmark query without reading real benchmark files."""
    return BenchmarkQuery(
        id=query_id,
        query="Quyền dân sự được bảo vệ như thế nào?",
        primary_domain=LegalDomain.CIVIL_FAMILY_IDENTITY,
        question_types=question_types or [QuestionType.SINGLE_ARTICLE_LOOKUP],
        expected_decision=expected_decision,
        fallback_reason=fallback_reason,
        review_status=ReviewStatus.FROZEN,
        split=BenchmarkSplit.DEVELOPMENT,
        reviewer_notes="Tiny integration fixture.",
    )


def _llm_response(text: str) -> LLMResponse:
    """Build one fake provider response."""
    return LLMResponse(
        text=text,
        model="mock-model",
        provider="mock",
        latency_ms=1.0,
        finish_reason="stop",
    )


def _strict_paths(tmp_path: Path) -> StrictGenerationPaths:
    """Create strict-generation output paths and baseline fixtures under tmp_path."""
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    baseline_dir = tmp_path / "generation_baseline"
    baseline_dir.mkdir()
    baseline_case = _baseline_case()
    baseline_metrics = aggregate_strict_generation_metrics([baseline_case])
    (baseline_dir / "baseline_manifest.json").write_text('{"report_type":"generation_baseline"}\n')
    for name in ("metrics_all.json", "metrics_development.json", "metrics_held_out_test.json"):
        (baseline_dir / name).write_text(json.dumps(baseline_metrics), encoding="utf-8")
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    split_manifest = tmp_path / "split_manifest.json"
    retrieval_config = tmp_path / "retrieval.yml"
    retrieval_manifest = tmp_path / "coverage_manifest.json"
    llm_config = tmp_path / "llm.yml"
    benchmark_manifest.write_text('{"benchmark_version":"v0.1.0"}\n', encoding="utf-8")
    split_manifest.write_text('{"assignments":{}}\n', encoding="utf-8")
    retrieval_config.write_text("retrieval_strategy: coverage_aware_quota\n", encoding="utf-8")
    retrieval_manifest.write_text('{"retrieval_method":"coverage_aware_quota"}\n', encoding="utf-8")
    llm_config.write_text("provider: mock\n", encoding="utf-8")
    return StrictGenerationPaths(
        file_set=BenchmarkFileSet(
            queries=empty,
            legal_targets=empty,
            evidence_judgments=empty,
            evidence_groups=empty,
            review_records=empty,
        ),
        split_manifest=split_manifest,
        benchmark_manifest=benchmark_manifest,
        retrieval_config=retrieval_config,
        coverage_retrieval_manifest=retrieval_manifest,
        generation_baseline_dir=baseline_dir,
        llm_config=llm_config,
        output_dir=tmp_path / "strict_generation_output",
    )


def _baseline_case() -> dict[str, object]:
    """Build one passing baseline case for comparison fixtures."""
    return {
        "query_id": "baseline-case",
        "split": "development",
        "primary_domain": "civil_family_identity",
        "question_types": ["single_article_lookup"],
        "expected_decision": "answer_allowed",
        "pipeline_decision": "answer_allowed",
        "pipeline_answered": True,
        "llm_called": True,
        "citation_guard_result": {"citation_id_valid": True, "citation_coverage_valid": True},
        "cited_evidence_ids": ["E1"],
        "missing_required_evidence_check": {
            "missing_required_evidence": False,
            "selected_required_direct_coverage": 1.0,
            "selected_evidence_group_coverage": 1.0,
        },
        "unsupported_or_uncited_claim_check": {"issue_present": False},
        "case_status": "pass",
        "generation_error": None,
        "retrieval_error": None,
        "error": None,
        "latency_ms": 1.0,
    }


def _retrieval_manifest() -> dict[str, object]:
    """Build minimal coverage-aware retrieval metadata for output writer."""
    return {
        "qdrant_collection_name": "fixture_collection",
        "vector_name": "dense",
        "embedding_model": "fake-embedding",
        "dense_candidate_k": 5,
        "sparse_candidate_k": 5,
        "final_top_k": 10,
        "rrf_k": 60,
        "dense_weight": 1.0,
        "sparse_weight": 1.5,
        "quota": {"fused_best": 2, "sparse_quota": 1, "dense_quota": 1},
    }
