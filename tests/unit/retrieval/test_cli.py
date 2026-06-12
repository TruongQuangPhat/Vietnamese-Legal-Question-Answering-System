"""Unit tests for the Phase 9A dense retrieval CLI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.retrieval.models import RetrievalFilters, RetrievalResult, RetrievedChunk
from src.retrieval.workflows import dense_retrieval


def test_parser_requires_query() -> None:
    """The CLI exposes the expected single-query arguments."""
    parser = dense_retrieval.build_arg_parser()

    args = parser.parse_args(["--query", "Quyền sử dụng đất là gì?", "--top-k", "5"])

    assert args.query == "Quyền sử dụng đất là gì?"
    assert args.top_k == 5


def test_validate_cli_rejects_blank_query() -> None:
    """Blank queries fail at CLI validation."""
    with pytest.raises(ValueError, match="query"):
        dense_retrieval.validate_cli_arguments(
            query=" ",
            top_k=1,
            output_path=None,
            preview_chars=100,
        )


def test_validate_cli_rejects_bad_top_k() -> None:
    """top-k must be positive."""
    with pytest.raises(ValueError, match="top-k"):
        dense_retrieval.validate_cli_arguments(
            query="test",
            top_k=0,
            output_path=None,
            preview_chars=100,
        )


def test_validate_cli_allows_retrieval_report_output() -> None:
    """Manual retrieval reports may be written under retrieval reports."""
    dense_retrieval.validate_cli_arguments(
        query="test",
        top_k=1,
        output_path=Path("artifacts/reports/retrieval/manual_query_result.json"),
        preview_chars=100,
    )


def test_validate_cli_rejects_corpus_output() -> None:
    """CLI output cannot write into protected corpus paths."""
    with pytest.raises(ValueError, match="protected"):
        dense_retrieval.validate_cli_arguments(
            query="test",
            top_k=1,
            output_path=Path("data/processed/result.json"),
            preview_chars=100,
        )


def test_build_cli_report_uses_previews_and_law_title_alias() -> None:
    """The JSON report is compact and includes user-facing preview fields."""
    result = RetrievalResult(
        query="test",
        collection_name="dev",
        vector_name="dense",
        top_k=1,
        elapsed_ms=1.2,
        query_vector_dimension=1024,
        filters=RetrievalFilters(),
        results=[
            RetrievedChunk(
                rank=1,
                score=0.9,
                chunk_id="chunk-1",
                law_id="BLDS_2015",
                law_name="Bộ luật Dân sự 2015",
                article_number="1",
                citation="Bộ luật Dân sự 2015, Điều 1",
                source_url="https://thuvienphapluat.vn/example",
                text="Một hai ba bốn năm",
                parent_text="Điều 1. Một hai ba bốn năm sáu",
            )
        ],
    )

    report = dense_retrieval.build_cli_report(result, preview_chars=12)

    assert report["results"][0]["law_title"] == "Bộ luật Dân sự 2015"
    assert report["results"][0]["text_preview"] == "Một hai b..."
    assert report["results"][0]["parent_text_preview"] == "Điều 1. M..."


def test_print_summary_accepts_report(capsys: pytest.CaptureFixture[str]) -> None:
    """The human-readable summary includes rank, score, citation, and preview."""
    report = {
        "query": "test",
        "collection_name": "dev",
        "top_k": 1,
        "result_count": 1,
        "elapsed_ms": 1.0,
        "issues": [],
        "results": [
            {
                "rank": 1,
                "score": 0.9,
                "chunk_id": "chunk-1",
                "citation": "Citation",
                "law_name": "Law",
                "law_id": "LAW",
                "article_number": "1",
                "clause_number": None,
                "point_label": None,
                "source_url": "https://thuvienphapluat.vn/example",
                "text_preview": "Preview",
                "issues": [],
            }
        ],
    }

    dense_retrieval.print_summary(report)

    captured = capsys.readouterr()
    assert "#1 score=0.900000 chunk_id=chunk-1" in captured.out
    assert "Citation: Citation" in captured.out
