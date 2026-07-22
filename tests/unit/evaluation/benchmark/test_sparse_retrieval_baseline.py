"""Unit tests for sparse retrieval baseline artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.evaluation import run_frozen_sparse_retrieval_baseline as sparse_cli
from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    LegalDomain,
    QuestionType,
    RelevanceLevel,
    ReviewStatus,
)
from src.evaluation.benchmark.retrieval_baseline import evaluate_case_retrieval
from src.evaluation.benchmark.schemas import BenchmarkQuery, EvidenceGroup, EvidenceJudgment
from src.evaluation.benchmark.sparse_retrieval_baseline import (
    SparseBenchmarkConfig,
    write_sparse_outputs,
)
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


def test_write_sparse_outputs_creates_required_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "reports"
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    split_manifest = tmp_path / "split_manifest.json"
    chunk_source = tmp_path / "legal_chunks.jsonl"
    benchmark_manifest.write_text('{"benchmark_version": "v0.1.0"}\n', encoding="utf-8")
    split_manifest.write_text('{"assignments": {}}\n', encoding="utf-8")
    chunk_source.write_text('{"chunk_id": "chunk_a"}\n', encoding="utf-8")
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

    write_sparse_outputs(
        output_dir=output_dir,
        case_results=case_results,
        benchmark_version="v0.1.0",
        benchmark_manifest_path=benchmark_manifest,
        split_manifest_path=split_manifest,
        chunk_source_path=chunk_source,
        dense_reference_dir=None,
        config=SparseBenchmarkConfig(top_k=10),
        document_count=2,
        average_document_length=4.0,
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
    assert manifest["retrieval_method"] == "sparse_bm25"
    assert manifest["query_count"] == 2
    assert manifest["chunk_source_sha256"]
    assert "Comparison Against Dense Baseline" in (output_dir / "summary.md").read_text(
        encoding="utf-8"
    )
    assert not _contains_secret_like_key(manifest)


def test_sparse_cli_output_policy_failure_does_not_overwrite_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_file = tmp_path / "existing-output.json"
    output_file.write_text("do not truncate", encoding="utf-8")

    exit_code = sparse_cli.main(
        [
            "--output-dir",
            str(output_file),
            "--output-policy",
            "staging",
            "--quiet",
        ]
    )

    assert exit_code == sparse_cli.EXIT_FAILURE
    assert output_file.read_text(encoding="utf-8") == "do not truncate"
    captured = capsys.readouterr()
    assert "staging output policy rejected output-dir" in captured.err


def test_sparse_cli_delegates_output_validation_to_shared_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_validate_benchmark_output_dir(*args: object, **kwargs: object) -> Path:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return tmp_path / "resolved"

    monkeypatch.setattr(
        sparse_cli,
        "validate_benchmark_output_dir",
        fake_validate_benchmark_output_dir,
    )

    sparse_cli.validate_cli_arguments(tmp_path / "staged", output_policy="staging")

    assert captured["args"] == (tmp_path / "staged",)
    assert captured["kwargs"] == {
        "repo_root": sparse_cli.REPO_ROOT,
        "evaluation_reports_root": sparse_cli.EVALUATION_REPORTS_ROOT,
        "output_policy": "staging",
        "label": "output-dir",
    }


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
