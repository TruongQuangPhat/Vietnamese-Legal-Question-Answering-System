"""Unit tests for hybrid retrieval baseline artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    LegalDomain,
    QuestionType,
    RelevanceLevel,
    ReviewStatus,
)
from src.evaluation.benchmark.hybrid_retrieval_baseline import (
    HybridBenchmarkConfig,
    write_hybrid_outputs,
)
from src.evaluation.benchmark.retrieval_baseline import evaluate_case_retrieval
from src.evaluation.benchmark.schemas import BenchmarkQuery, EvidenceGroup, EvidenceJudgment
from src.retrieval.models import RetrievedChunk


def _query(query_id: str, split: BenchmarkSplit) -> BenchmarkQuery:
    return BenchmarkQuery(
        id=query_id,
        query="Synthetic Vietnamese legal query?",
        primary_domain=LegalDomain.CIVIL_FAMILY_IDENTITY,
        question_types=[QuestionType.SINGLE_ARTICLE_LOOKUP],
        expected_decision=ExpectedDecision.ANSWER_ALLOWED,
        review_status=ReviewStatus.FROZEN,
        reviewer_notes="Synthetic fixture.",
        split=split,
    )


def _judgment(query_id: str, chunk_id: str) -> EvidenceJudgment:
    return EvidenceJudgment(
        query_id=query_id,
        chunk_id=chunk_id,
        relevance=RelevanceLevel.REQUIRED_DIRECT,
        evidence_group_ids=[f"{query_id}_group"],
    )


def _group(query_id: str, chunk_id: str) -> EvidenceGroup:
    return EvidenceGroup(
        query_id=query_id,
        evidence_group_id=f"{query_id}_group",
        requirement=EvidenceGroupRequirement.REQUIRED,
        minimum_hits=1,
        acceptable_chunk_ids=[chunk_id],
        acceptable_legal_targets=[
            {
                "law_id": "LAW_A",
                "article_number": "1",
                "match_level": "article",
            }
        ],
    )


def _hit(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        rank=1,
        score=1.0,
        chunk_id=chunk_id,
        law_id="LAW_A",
        article_number="1",
        text="Synthetic legal text.",
    )


def _write_reference_report(path: Path) -> None:
    path.mkdir(parents=True)
    metrics = {
        "query_count": 2,
        "evaluated_query_count": 2,
        "retrieval_error_count": 0,
        "answer_allowed_count": 2,
        "fallback_required_count": 0,
        "mean_retrieval_latency_ms": 1.0,
        "mrr_at_10": 1.0,
        "ndcg_at_10": 1.0,
        "fallback_diagnostics": {"fallback_case_count": 0},
        "recall_at_10": 1.0,
        "required_direct_coverage_at_10": 1.0,
        "evidence_group_coverage_at_10": 1.0,
    }
    for name in ("metrics_all.json", "metrics_development.json", "metrics_held_out_test.json"):
        (path / name).write_text(json.dumps(metrics), encoding="utf-8")
    (path / "baseline_manifest.json").write_text('{"report_type": "reference"}\n', encoding="utf-8")
    (path / "case_results.jsonl").write_text("", encoding="utf-8")


def test_write_hybrid_outputs_creates_required_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "hybrid"
    dense_dir = tmp_path / "dense"
    sparse_dir = tmp_path / "sparse"
    _write_reference_report(dense_dir)
    _write_reference_report(sparse_dir)
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    split_manifest = tmp_path / "split_manifest.json"
    chunk_source = tmp_path / "legal_chunks.jsonl"
    dense_config = tmp_path / "retrieval.yml"
    benchmark_manifest.write_text('{"benchmark_version": "v0.1.0"}\n', encoding="utf-8")
    split_manifest.write_text('{"assignments": {}}\n', encoding="utf-8")
    chunk_source.write_text('{"chunk_id": "chunk_a"}\n', encoding="utf-8")
    dense_config.write_text("schema_version: '0.1.0'\n", encoding="utf-8")
    case_results = [
        evaluate_case_retrieval(
            query=_query("q_dev", BenchmarkSplit.DEVELOPMENT),
            split=BenchmarkSplit.DEVELOPMENT,
            retrieved=[_hit("chunk_a")],
            judgments=[_judgment("q_dev", "chunk_a")],
            groups=[_group("q_dev", "chunk_a")],
        ),
        evaluate_case_retrieval(
            query=_query("q_test", BenchmarkSplit.HELD_OUT_TEST),
            split=BenchmarkSplit.HELD_OUT_TEST,
            retrieved=[_hit("chunk_b")],
            judgments=[_judgment("q_test", "chunk_b")],
            groups=[_group("q_test", "chunk_b")],
        ),
    ]

    write_hybrid_outputs(
        output_dir=output_dir,
        case_results=case_results,
        benchmark_version="v0.1.0",
        benchmark_manifest_path=benchmark_manifest,
        split_manifest_path=split_manifest,
        chunk_source_path=chunk_source,
        dense_config_path=dense_config,
        dense_config_payload={"schema_version": "0.1.0"},
        dense_reference_dir=dense_dir,
        sparse_reference_dir=sparse_dir,
        config=HybridBenchmarkConfig(),
        qdrant_collection_name="vnlaw_chunks_bgem3_v1_full",
        qdrant_collection_info={"points_count": 40389},
        embedding_model="BAAI/bge-m3",
        vector_name="dense",
        command=["python", "script.py"],
    )

    expected_files = {
        "case_results.jsonl",
        "metrics_all.json",
        "metrics_development.json",
        "metrics_held_out_test.json",
        "breakdowns.json",
        "baseline_manifest.json",
        "summary.md",
    }
    assert {path.name for path in output_dir.iterdir()} == expected_files
    manifest = json.loads((output_dir / "baseline_manifest.json").read_text(encoding="utf-8"))
    assert manifest["retrieval_method"] == "hybrid_dense_sparse_rrf"
    assert manifest["dense_candidate_k"] == 50
    assert manifest["sparse_candidate_k"] == 50
    assert manifest["final_top_k"] == 10
    assert manifest["rrf_k"] == 60
    assert manifest["dense_baseline_manifest_sha256"]
    assert manifest["sparse_baseline_manifest_sha256"]
    assert not _contains_secret_like_key(manifest)


def _contains_secret_like_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            "secret" in key.lower()
            or "authorization" in key.lower()
            or "api_key" in key.lower()
            or _contains_secret_like_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret_like_key(item) for item in value)
    return False
