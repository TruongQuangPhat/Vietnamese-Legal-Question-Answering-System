"""Tests for strict generation evaluation and its fixed retrieval strategy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from scripts.evaluation.run_strict_generation_evaluation import (
    DEFAULT_OUTPUT_DIR,
    build_arg_parser,
    main,
)
from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    ExpectedDecision,
    FallbackReason,
    LegalDomain,
    QuestionType,
    ReviewStatus,
)
from src.evaluation.benchmark.fusion_ablation import default_ablation_configs
from src.evaluation.benchmark.loader import BenchmarkFileSet
from src.evaluation.benchmark.schemas import BenchmarkQuery
from src.evaluation.benchmark.strict_generation_evaluation import (
    BASE_GENERATION_BASELINE,
    RETRIEVAL_STRATEGY,
    WORKFLOW_NAME,
    CoverageAwareQuotaRetriever,
    FrozenResultRetriever,
    StrictGenerationPaths,
    _expected_targets_for_query,
    aggregate_strict_generation_metrics,
    build_strict_generation_manifest,
    evaluate_strict_generation_query,
    write_strict_generation_outputs,
)
from src.retrieval.dense_retriever import DenseRetrieverError
from src.retrieval.evaluation import ExpectedTarget
from src.retrieval.generation import RagGenerationConfig
from src.retrieval.llm_client import LLMClientError, LLMRequest, LLMResponse, MockLLMClient
from src.retrieval.models import RetrievalResult, RetrievedChunk
from src.retrieval.rag_pipeline import run_naive_rag
from src.retrieval.selection import AnswerabilityDecision, EvidenceSelectionConfig


@dataclass
class FakeCandidateRetriever:
    """Return configured candidates and record requested depth."""

    result: RetrievalResult
    requested: list[int]

    async def retrieve(self, query: str, *, top_k: int) -> RetrievalResult:
        self.requested.append(top_k)
        return self.result


class FailingLLMClient:
    """Raise a provider-style error without calling an external service."""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMClientError("provider offline")


class FailingRetriever:
    """Raise a retrieval-style error without calling Qdrant."""

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        raise DenseRetrieverError("dense retrieval offline")


def _selected_config() -> Any:
    return next(
        config
        for config in default_ablation_configs()
        if config.config_id == "selected_coverage_aware_quota"
    )


def _chunk(
    *,
    chunk_id: str = "chunk-1",
    rank: int = 1,
    score: float = 1.0,
) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        law_id="BLDS_2015",
        law_name="Bộ luật Dân sự 2015",
        article_number="2",
        citation="Điều 2, Bộ luật Dân sự 2015",
        text="Quyền dân sự được công nhận, tôn trọng và bảo vệ.",
        source_url="https://thuvienphapluat.vn/example",
    )


def _retrieval_result(chunks: list[RetrievedChunk], vector_name: str) -> RetrievalResult:
    return RetrievalResult(
        query="Quyền dân sự được bảo vệ như thế nào?",
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name=vector_name,
        top_k=50,
        elapsed_ms=1.0,
        query_vector_dimension=1024 if vector_name == "dense" else 0,
        results=chunks,
        issues=[],
    )


def _coverage_retriever(chunks: list[RetrievedChunk]) -> CoverageAwareQuotaRetriever:
    return CoverageAwareQuotaRetriever(
        dense_retriever=FakeCandidateRetriever(
            _retrieval_result(chunks, "dense"),
            [],
        ),
        sparse_retriever=FakeCandidateRetriever(
            _retrieval_result(chunks, "sparse_bm25"),
            [],
        ),
        config=_selected_config(),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
    )


@pytest.mark.asyncio
async def test_coverage_retriever_uses_fixed_candidate_depth_and_quota() -> None:
    dense = FakeCandidateRetriever(_retrieval_result([_chunk()], "dense"), [])
    sparse = FakeCandidateRetriever(_retrieval_result([_chunk()], "sparse_bm25"), [])
    retriever = CoverageAwareQuotaRetriever(
        dense_retriever=dense,
        sparse_retriever=sparse,
        config=_selected_config(),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        vector_name="dense",
    )

    result = await retriever.retrieve(
        query="Quyền dân sự được bảo vệ như thế nào?",
        top_k=10,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )

    assert dense.requested == [50]
    assert sparse.requested == [50]
    assert result.top_k == 10
    assert result.results[0].metadata["fusion"]["sparse_rank"] == 1
    assert "rerank" not in json.dumps(result.model_dump(mode="json")).lower()


@pytest.mark.asyncio
async def test_insufficient_evidence_falls_back_without_llm_call() -> None:
    retrieval = await _coverage_retriever([]).retrieve(
        query="Câu hỏi không có chứng cứ?",
        top_k=10,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )
    llm = MockLLMClient([_llm_response("Không được gọi [E1]")])

    result = await run_naive_rag(
        query="Câu hỏi không có chứng cứ?",
        retriever=FrozenResultRetriever(retrieval),
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
        top_k=10,
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
        selection_config=EvidenceSelectionConfig(),
    )

    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert result.llm_called is False
    assert llm.requests == []


@pytest.mark.asyncio
async def test_unselected_citation_id_forces_fallback() -> None:
    retrieval = await _coverage_retriever([_chunk()]).retrieve(
        query="Quyền dân sự được bảo vệ như thế nào?",
        top_k=10,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )
    llm = MockLLMClient([_llm_response("Nội dung không được chứng minh [E99].")])

    result = await run_naive_rag(
        query="Quyền dân sự được bảo vệ như thế nào?",
        retriever=FrozenResultRetriever(retrieval),
        llm_client=llm,
        collection_name="vnlaw_chunks_bgem3_v1_full",
        top_k=10,
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
        selection_config=EvidenceSelectionConfig(),
    )

    assert len(llm.requests) == 1
    assert result.decision == AnswerabilityDecision.FALLBACK_REQUIRED
    assert result.citations == []
    assert result.errors == ["generated answer cited unknown evidence ID [E99]"]


@pytest.mark.asyncio
async def test_generation_provider_error_is_recorded_per_case() -> None:
    retrieval = await _coverage_retriever([_chunk()]).retrieve(
        query="Quyền dân sự được bảo vệ như thế nào?",
        top_k=10,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )

    case = await evaluate_strict_generation_query(
        query=_query(),
        split="development",
        retriever=FrozenResultRetriever(retrieval),
        llm_client=FailingLLMClient(),
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
        selection_config=EvidenceSelectionConfig(),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        final_top_k=10,
        expected_targets=None,
        judgments=[],
        groups=[],
    )

    assert case["retrieval_error"] is None
    assert case["generation_error"] == "provider offline"
    assert case["error"] == "provider offline"
    assert case["case_status"] == "fail"


@pytest.mark.asyncio
async def test_retrieval_error_is_recorded_as_case_error_and_metric() -> None:
    case = await evaluate_strict_generation_query(
        query=_query(),
        split="development",
        retriever=FailingRetriever(),
        llm_client=MockLLMClient([_llm_response("Không được gọi [E1]")]),
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
        selection_config=EvidenceSelectionConfig(),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        final_top_k=10,
        expected_targets=None,
        judgments=[],
        groups=[],
    )
    metrics = aggregate_strict_generation_metrics([case])

    assert case["retrieval_error"] == "dense retrieval offline"
    assert case["generation_error"] is None
    assert case["error"] == "dense retrieval offline"
    assert case["case_status"] == "fail"
    assert metrics["retrieval_error_count"] == 1
    assert metrics["generation_error_count"] == 0


@pytest.mark.asyncio
async def test_fallback_required_query_with_empty_targets_does_not_call_llm() -> None:
    retrieval = await _coverage_retriever([_chunk()]).retrieve(
        query="Câu hỏi mơ hồ phải fallback?",
        top_k=10,
        collection_name="vnlaw_chunks_bgem3_v1_full",
    )
    llm = MockLLMClient([_llm_response("Không được gọi [E1]")])

    case = await evaluate_strict_generation_query(
        query=_query(
            expected_decision=ExpectedDecision.FALLBACK_REQUIRED,
            question_types=[QuestionType.FALLBACK],
            fallback_reason=FallbackReason.UNSAFE_AMBIGUITY,
        ),
        split="development",
        retriever=FrozenResultRetriever(retrieval),
        llm_client=llm,
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
        selection_config=EvidenceSelectionConfig(),
        collection_name="vnlaw_chunks_bgem3_v1_full",
        final_top_k=10,
        expected_targets=[],
        judgments=[],
        groups=[],
    )

    assert case["pipeline_decision"] == ExpectedDecision.FALLBACK_REQUIRED.value
    assert case["llm_called"] is False
    assert llm.requests == []
    assert "exact_target_missing_in_eval_mode" in case["fallback_reasons"]


def test_manifest_uses_functional_metadata_and_strict_guards(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    retrieval_manifest = _retrieval_manifest()

    manifest = build_strict_generation_manifest(
        paths=paths,
        benchmark_version="v0.1.0",
        retrieval_manifest=retrieval_manifest,
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
        selection_config=EvidenceSelectionConfig(),
        provider="openrouter",
        model="mock-model",
        command=["python", "run_strict_generation_evaluation.py"],
        query_count=2,
    )

    assert manifest["report_type"] == WORKFLOW_NAME
    assert manifest["workflow_name"] == WORKFLOW_NAME
    assert manifest["retrieval_strategy"] == RETRIEVAL_STRATEGY
    assert manifest["base_generation_baseline"] == BASE_GENERATION_BASELINE
    assert manifest["reranking_used"] is False
    assert manifest["generation_config"]["fail_on_invalid_citation"] is True
    assert {
        "report_type",
        "workflow_name",
        "retrieval_strategy",
        "base_generation_baseline",
        "retrieval_settings",
        "generation_config",
        "evidence_selection_config",
    } <= manifest.keys()


def test_output_writer_creates_metrics_and_comparison(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    cases = [_case("development"), _case("held_out_test")]

    write_strict_generation_outputs(
        paths=paths,
        case_results=cases,
        benchmark_version="v0.1.0",
        retrieval_manifest=_retrieval_manifest(),
        generation_config=RagGenerationConfig(fail_on_invalid_citation=True),
        selection_config=EvidenceSelectionConfig(),
        provider="openrouter",
        model="mock-model",
        command=["python", "run_strict_generation_evaluation.py"],
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
    metrics = json.loads((paths.output_dir / "metrics_all.json").read_text())
    comparison = json.loads((paths.output_dir / "comparison.json").read_text())
    assert metrics["retrieval_error_count"] == 0
    assert {
        "decision_accuracy",
        "answer_allowed_answer_rate",
        "fallback_required_fallback_rate",
        "selected_evidence_group_coverage",
        "case_pass_rate",
        "citation_id_validity_rate",
        "retrieval_error_count",
        "generation_error_count",
    } <= metrics.keys()
    assert set(comparison["systems"]) == {
        BASE_GENERATION_BASELINE,
        WORKFLOW_NAME,
    }
    assert len(comparison["key_questions"]) == 8


def test_cli_defaults_and_help_do_not_require_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = build_arg_parser().parse_args([])
    assert args.output_dir == DEFAULT_OUTPUT_DIR
    assert args.provider == "openrouter"

    monkeypatch.setattr(
        "scripts.evaluation.run_strict_generation_evaluation.load_project_dotenv",
        lambda: pytest.fail("dotenv must not load while rendering help"),
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_strict_metric_aggregation_separates_retrieval_errors() -> None:
    cases = [_case("development"), {**_case("held_out_test"), "retrieval_error": "offline"}]

    metrics = aggregate_strict_generation_metrics(cases)

    assert metrics["retrieval_error_count"] == 1
    assert metrics["generation_error_count"] == 0


def test_strict_evaluation_represents_fallback_required_targets_as_empty() -> None:
    target = ExpectedTarget(
        law_id="BLDS_2015",
        article_number="2",
        clause_number=None,
        point_label=None,
        match_level="article",
    )

    assert (
        _expected_targets_for_query(
            _query(
                expected_decision=ExpectedDecision.FALLBACK_REQUIRED,
                question_types=[QuestionType.FALLBACK],
                fallback_reason=FallbackReason.UNSAFE_AMBIGUITY,
            ),
            {"query-development": [target]},
        )
        == []
    )
    assert _expected_targets_for_query(_query(), {"query-development": [target]}) == [target]


def _paths(tmp_path: Path) -> StrictGenerationPaths:
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    split_manifest = tmp_path / "split_manifest.json"
    retrieval_config = tmp_path / "retrieval.yml"
    retrieval_manifest = tmp_path / "coverage_manifest.json"
    llm_config = tmp_path / "llm.yml"
    baseline_dir = tmp_path / "generation_baseline"
    output_dir = tmp_path / "strict"
    benchmark_manifest.write_text('{"benchmark_version": "v0.1.0"}\n')
    split_manifest.write_text('{"assignments": {}}\n')
    retrieval_config.write_text("schema_version: '0.1.0'\n")
    retrieval_manifest.write_text('{"retrieval_method": "coverage_aware_quota"}\n')
    llm_config.write_text("provider: openrouter\n")
    baseline_dir.mkdir()
    (baseline_dir / "baseline_manifest.json").write_text('{"report_type": "baseline"}\n')
    baseline_metrics = aggregate_strict_generation_metrics(
        [_case("development"), _case("held_out_test")]
    )
    for filename in (
        "metrics_all.json",
        "metrics_development.json",
        "metrics_held_out_test.json",
    ):
        (baseline_dir / filename).write_text(json.dumps(baseline_metrics))
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
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
        output_dir=output_dir,
    )


def _retrieval_manifest() -> dict[str, Any]:
    config = _selected_config()
    return {
        "qdrant_collection_name": "vnlaw_chunks_bgem3_v1_full",
        "vector_name": "dense",
        "embedding_model": "BAAI/bge-m3",
        "dense_candidate_k": config.dense_candidate_k,
        "sparse_candidate_k": config.sparse_candidate_k,
        "final_top_k": config.final_top_k,
        "rrf_k": config.rrf_k,
        "dense_weight": config.dense_weight,
        "sparse_weight": config.sparse_weight,
        "quota": config.model_dump()["quota"],
    }


def _query(
    *,
    expected_decision: ExpectedDecision = ExpectedDecision.ANSWER_ALLOWED,
    question_types: list[QuestionType] | None = None,
    fallback_reason: FallbackReason | None = None,
) -> BenchmarkQuery:
    return BenchmarkQuery(
        id="query-development",
        query="Quyền dân sự được bảo vệ như thế nào?",
        primary_domain=LegalDomain.CIVIL_FAMILY_IDENTITY,
        question_types=question_types or [QuestionType.SINGLE_ARTICLE_LOOKUP],
        expected_decision=expected_decision,
        fallback_reason=fallback_reason,
        review_status=ReviewStatus.FROZEN,
        split=BenchmarkSplit.DEVELOPMENT,
        reviewer_notes="Mock query for strict generation evaluation tests.",
    )


def _case(split: str) -> dict[str, Any]:
    return {
        "query_id": f"query-{split}",
        "split": split,
        "primary_domain": "civil_family_identity",
        "question_types": ["single_article_lookup"],
        "blocking": False,
        "expected_decision": "answer_allowed",
        "pipeline_decision": "answer_allowed",
        "pipeline_answered": True,
        "llm_called": True,
        "cited_evidence_ids": ["E1"],
        "citation_guard_result": {
            "citation_id_valid": True,
            "citation_coverage_valid": True,
        },
        "missing_required_evidence_check": {
            "missing_required_evidence": False,
            "selected_required_direct_coverage": 1.0,
            "selected_evidence_group_coverage": 1.0,
        },
        "unsupported_or_uncited_claim_check": {"issue_present": False},
        "case_status": "pass",
        "latency_ms": 1.0,
        "error": None,
        "generation_error": None,
        "retrieval_error": None,
    }


def _llm_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        model="mock-model",
        provider="mock",
        latency_ms=1.0,
        finish_reason="stop",
    )
