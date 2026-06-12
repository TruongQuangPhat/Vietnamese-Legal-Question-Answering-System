"""Unit tests for Phase 9A.1 dense retrieval evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.retrieval.evaluation import (
    ExpectedTarget,
    ManualRetrievalQuery,
    aggregate_metrics,
    article_level_match,
    best_article_rank,
    best_exact_rank,
    build_risk_flags,
    evaluate_dense_retrieval,
    evaluate_retrieval_result,
    exact_provision_match,
    load_manual_retrieval_queries,
    matches_clause,
    matches_expected_target,
    matches_point,
    reciprocal_rank,
    target_match_result,
)
from src.retrieval.models import RetrievalFilters, RetrievalResult, RetrievedChunk
from src.retrieval.workflows import dense_evaluation as eval_cli


def make_target(
    *,
    law_id: str = "BLLD_VBHN",
    article_number: str = "113",
    clause_number: str | None = "1",
    point_label: str | None = None,
    match_level: str = "clause",
) -> ExpectedTarget:
    """Build one expected target."""
    return ExpectedTarget(
        law_id=law_id,
        article_number=article_number,
        clause_number=clause_number,
        point_label=point_label,
        match_level=match_level,
    )


def make_record(
    *,
    query_id: str = "annual_leave_days",
    query: str = "Người lao động được nghỉ hằng năm bao nhiêu ngày?",
    expected: list[ExpectedTarget] | None = None,
) -> ManualRetrievalQuery:
    """Build one manual query record."""
    return ManualRetrievalQuery(
        query_id=query_id,
        query=query,
        expected=expected or [make_target()],
        notes="test",
    )


def make_chunk(
    *,
    rank: int,
    law_id: str = "BLLD_VBHN",
    article_number: str = "113",
    clause_number: str | None = "1",
    point_label: str | None = None,
    citation: str | None = "Citation",
    source_url: str | None = "https://thuvienphapluat.vn/example",
    parent_text: str | None = "Điều 113. Nghỉ hằng năm\n1. Nội dung.",
    score: float = 0.9,
) -> RetrievedChunk:
    """Build one retrieved chunk summary for evaluation."""
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=f"chunk-{rank}",
        law_id=law_id,
        law_name="Law",
        article_number=article_number,
        clause_number=clause_number,
        point_label=point_label,
        citation=citation,
        source_url=source_url,
        text=f"Text {rank}",
        parent_text=parent_text,
    )


def make_result(chunks: list[RetrievedChunk], *, elapsed_ms: float = 12.0) -> RetrievalResult:
    """Build one dense retrieval result."""
    return RetrievalResult(
        query="test",
        collection_name="dev",
        vector_name="dense",
        top_k=20,
        elapsed_ms=elapsed_ms,
        query_vector_dimension=1024,
        filters=RetrievalFilters(),
        results=chunks,
    )


class FakeRetriever:
    """Fake retrieval service returning configured results or exceptions."""

    def __init__(self, outputs: list[RetrievalResult | Exception]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        self.calls.append({"query": query, "top_k": top_k, "collection_name": collection_name})
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def test_load_manual_retrieval_queries_parses_jsonl(tmp_path: Path) -> None:
    """Manual query records load from JSONL and validate expected target depth."""
    path = tmp_path / "queries.jsonl"
    path.write_text(
        json.dumps(
            {
                "query_id": "q1",
                "query": "Điều kiện kết hôn là gì?",
                "expected": [
                    {
                        "law_id": "LHNGD_VBHN",
                        "article_number": "8",
                        "clause_number": None,
                        "point_label": None,
                        "match_level": "article",
                    }
                ],
                "notes": "manual",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    records = load_manual_retrieval_queries(path)

    assert records[0].query_id == "q1"
    assert records[0].expected[0].law_id == "LHNGD_VBHN"
    assert records[0].expected[0].match_level == "article"


def test_manual_dataset_loads_from_repo_with_match_levels() -> None:
    """The checked-in manual dataset remains valid and declares match levels."""
    records = load_manual_retrieval_queries("data/eval/manual_retrieval_queries.jsonl")
    by_id = {record.query_id: record for record in records}

    assert set(by_id) >= {
        "annual_leave_days",
        "marriage_conditions",
        "health_insurance_children_under_6",
    }
    assert {target.match_level for target in by_id["annual_leave_days"].expected} == {
        "clause",
        "point",
    }
    assert by_id["marriage_conditions"].expected[0].match_level == "article"


def test_expected_target_validates_required_fields_for_match_level() -> None:
    """Clause and point targets require enough hierarchy metadata."""
    ExpectedTarget(law_id="L", article_number="8", match_level="article")
    with pytest.raises(ValidationError, match="clause_number"):
        ExpectedTarget(law_id="L", article_number="8", match_level="clause")
    with pytest.raises(ValidationError, match="point_label"):
        ExpectedTarget(
            law_id="L",
            article_number="8",
            clause_number="1",
            match_level="point",
        )


def test_article_target_matches_child_chunks_under_same_article() -> None:
    """Article-level targets match Article, Clause, or Point chunks under that Article."""
    target = make_target(clause_number=None, point_label=None, match_level="article")
    clause_chunk = make_chunk(rank=1, clause_number="1", point_label=None)
    point_chunk = make_chunk(rank=2, clause_number="1", point_label="d")

    assert article_level_match(target, clause_chunk) is True
    assert exact_provision_match(target, clause_chunk) is True
    assert matches_expected_target(target, point_chunk) is True
    assert best_exact_rank(target, [point_chunk]) == 2


def test_clause_target_matches_point_under_clause_but_not_sibling_clause() -> None:
    """Clause-level targets ignore point_label but still constrain the Clause."""
    target = make_target(clause_number="1", point_label=None, match_level="clause")
    same_clause_point = make_chunk(rank=1, clause_number="1", point_label="a")
    sibling_clause = make_chunk(rank=2, clause_number="4", point_label=None)

    assert matches_clause(target, same_clause_point) is True
    assert exact_provision_match(target, same_clause_point) is True
    assert exact_provision_match(target, sibling_clause) is False
    assert best_article_rank(target, [sibling_clause, same_clause_point]) == 2
    assert best_exact_rank(target, [sibling_clause, same_clause_point]) == 1


def test_point_target_requires_exact_point_label() -> None:
    """Point-level targets require law, Article, Clause, and Point."""
    target = make_target(clause_number="1", point_label="a", match_level="point")
    same_point = make_chunk(rank=1, clause_number="1", point_label="a")
    wrong_point = make_chunk(rank=2, clause_number="1", point_label="b")

    assert matches_point(target, same_point) is True
    assert exact_provision_match(target, same_point) is True
    assert exact_provision_match(target, wrong_point) is False


def test_null_fields_are_not_exact_null_constraints() -> None:
    """Null expected fields are unconstrained below the declared target depth."""
    article_target = make_target(clause_number=None, point_label=None, match_level="article")
    clause_target = make_target(clause_number="1", point_label=None, match_level="clause")
    point_chunk = make_chunk(rank=1, clause_number="1", point_label="c")

    assert exact_provision_match(article_target, point_chunk) is True
    assert exact_provision_match(clause_target, point_chunk) is True


def test_target_match_result_exposes_depth_specific_ranks() -> None:
    """Reports expose Article, Clause, Point, and exact-depth ranks separately."""
    target = make_target(clause_number="1", point_label="a", match_level="point")
    hits = [
        make_chunk(rank=1, clause_number="4", point_label=None),
        make_chunk(rank=2, clause_number="1", point_label="b"),
        make_chunk(rank=3, clause_number="1", point_label="a"),
    ]

    match = target_match_result(target, hits)

    assert match.article_match_rank == 1
    assert match.clause_match_rank == 2
    assert match.point_match_rank == 3
    assert match.best_exact_rank == 3
    assert match.exact_match_depth == "point"


def test_reciprocal_rank_respects_cutoff() -> None:
    """MRR contribution is zero outside the cutoff."""
    assert reciprocal_rank(4, cutoff=20) == 0.25
    assert reciprocal_rank(21, cutoff=20) == 0.0
    assert reciprocal_rank(None, cutoff=20) == 0.0


def test_evaluate_result_uses_match_level_for_exact_hits() -> None:
    """Per-query metrics use the declared match depth for exact recall."""
    record = make_record(expected=[make_target(clause_number=None, match_level="article")])
    result = make_result(
        [
            make_chunk(rank=1, law_id="OTHER", article_number="99", clause_number=None),
            make_chunk(rank=2, clause_number="4", point_label="d"),
        ]
    )

    evaluated = evaluate_retrieval_result(record, result, top_k=20, cutoffs=(5, 10, 20))

    assert evaluated.best_article_rank == 2
    assert evaluated.best_exact_rank == 2
    assert evaluated.exact_match_depth == "article"
    assert evaluated.best_rank_by_match_level["article"] == 2
    assert evaluated.exact_hit_at["5"] is True
    assert evaluated.article_hit_at["5"] is True
    assert evaluated.reciprocal_rank_at_20 == pytest.approx(1 / 2)
    assert evaluated.metadata_completeness_rate == 1.0


def test_article_level_valid_match_does_not_emit_clause_mismatch_risk() -> None:
    """Article-level targets should not trigger provision-mismatch risks."""
    record = make_record(expected=[make_target(clause_number=None, match_level="article")])
    result = make_result([make_chunk(rank=1, clause_number="1", point_label="d")])

    evaluated = evaluate_retrieval_result(record, result, top_k=20, cutoffs=(20,))

    codes = {flag.code for flag in evaluated.risk_flags}
    assert evaluated.best_exact_rank == 1
    assert "expected_article_hit_without_exact_clause_hit" not in codes
    assert "child_provision_mismatch_under_expected_article" not in codes


def test_annual_leave_style_sibling_clause_risk_still_fires() -> None:
    """Clause targets still flag sibling Clause hits under the expected Article."""
    target = make_target(clause_number="1", point_label=None, match_level="clause")
    hits = [make_chunk(rank=1, article_number="113", clause_number="4")]
    evaluated = evaluate_retrieval_result(
        make_record(expected=[target]),
        make_result(hits),
        top_k=20,
        cutoffs=(20,),
    )

    codes = {flag.code for flag in evaluated.risk_flags}
    assert evaluated.best_article_rank == 1
    assert evaluated.best_exact_rank is None
    assert "expected_article_hit_without_exact_clause_hit" in codes
    assert "child_provision_mismatch_under_expected_article" in codes
    mismatch = next(
        flag
        for flag in evaluated.risk_flags
        if flag.code == "child_provision_mismatch_under_expected_article"
    )
    assert mismatch.details["expected_match_level"] == "clause"
    assert mismatch.details["top_result"]["clause_number"] == "4"


def test_risk_flags_wrong_law_and_wrong_top_article_include_details() -> None:
    """Wrong top result risks include expected target and lower-match details."""
    target = make_target()
    hits = [
        make_chunk(rank=1, law_id="OTHER", article_number="99", clause_number=None),
        make_chunk(rank=2, law_id="BLLD_VBHN", article_number="113", clause_number="4"),
    ]
    evaluated = evaluate_retrieval_result(
        make_record(expected=[target]),
        make_result(hits),
        top_k=20,
        cutoffs=(5, 10, 20),
    )

    by_code = {flag.code: flag for flag in evaluated.risk_flags}
    assert "top_result_from_wrong_law" in by_code
    assert "top_result_wrong_article_when_expected_article_exists_lower" in by_code
    assert "expected_article_hit_without_exact_clause_hit" in by_code
    assert (
        by_code["top_result_wrong_article_when_expected_article_exists_lower"].details[
            "matched_lower_result"
        ]["rank"]
        == 2
    )


def test_parent_text_metadata_mismatch_risk_is_separate_from_child_mismatch() -> None:
    """A textual parent reference is flagged separately from same-Article child mismatch."""
    target = make_target(clause_number="1", match_level="clause")
    hits = [
        make_chunk(
            rank=1,
            law_id="BLLD_VBHN",
            article_number="99",
            clause_number="1",
            parent_text="Nội dung viện dẫn Điều 113 trong phần giải thích.",
        )
    ]

    flags = build_risk_flags([target], hits, [target_match_result(target, hits)])

    codes = {flag.code for flag in flags}
    assert "parent_text_mentions_expected_article_but_chunk_metadata_mismatch" in codes
    assert "child_provision_mismatch_under_expected_article" not in codes


def test_metadata_missing_flags_are_emitted() -> None:
    """Missing citation/source/law metadata creates explicit risks."""
    hits = [make_chunk(rank=1, citation=None, source_url=None, law_id=None)]
    evaluated = evaluate_retrieval_result(
        make_record(),
        make_result(hits),
        top_k=20,
        cutoffs=(20,),
    )

    codes = {flag.code for flag in evaluated.risk_flags}
    assert "metadata_missing_citation" in codes
    assert "metadata_missing_source_url" in codes
    assert "metadata_missing_law_id" in codes


def test_empty_result_handling_sets_metrics_and_risk() -> None:
    """No-result queries are visible in metrics and risks."""
    evaluated = evaluate_retrieval_result(
        make_record(),
        make_result([]),
        top_k=20,
        cutoffs=(5, 10, 20),
    )

    assert evaluated.empty_result is True
    assert evaluated.best_exact_rank is None
    assert evaluated.exact_hit_at["20"] is False
    assert evaluated.metadata_completeness_rate == 0.0
    assert evaluated.risk_flags[0].code == "empty_results"


def test_aggregate_metric_computation_uses_match_level_exact_hits() -> None:
    """Aggregate exact-hit metrics use match-level-aware matching."""
    article_hit = evaluate_retrieval_result(
        make_record(
            query_id="article-hit",
            expected=[make_target(clause_number=None, point_label=None, match_level="article")],
        ),
        make_result([make_chunk(rank=1, clause_number="9", point_label="d")]),
        top_k=20,
        cutoffs=(5, 10, 20),
    )
    clause_miss = evaluate_retrieval_result(
        make_record(query_id="clause-miss"),
        make_result([make_chunk(rank=1, clause_number="4")]),
        top_k=20,
        cutoffs=(5, 10, 20),
    )

    metrics = aggregate_metrics([article_hit, clause_miss], cutoffs=(5, 10, 20))

    assert metrics.query_count == 2
    assert metrics.recall_at_5 == 0.5
    assert metrics.exact_hit_at_20 == 0.5
    assert metrics.article_hit_at_20 == 1.0
    assert metrics.mrr_at_20 == 0.5


@pytest.mark.asyncio
async def test_evaluate_dense_retrieval_builds_report_and_captures_errors() -> None:
    """The evaluator keeps running when one query fails and serializes new fields."""
    records = [
        make_record(query_id="ok", query="ok"),
        make_record(query_id="error", query="error"),
    ]
    retriever = FakeRetriever([make_result([make_chunk(rank=1)]), RuntimeError("boom")])

    report = await evaluate_dense_retrieval(
        retriever,
        records,
        collection_name="dev",
        vector_name="dense",
        top_k=20,
    )

    assert report.report_type == "dense_retrieval_evaluation_report"
    assert report.query_count == 2
    assert report.aggregate_metrics.error_count == 1
    assert report.per_query[1].retrieval_error == "boom"
    assert retriever.calls[0]["collection_name"] == "dev"
    payload = report.model_dump(mode="json")
    assert payload["aggregate_metrics"]["recall_at_20"] == 0.5
    assert payload["per_query"][0]["best_rank_by_match_level"]["clause"] == 1
    assert payload["per_query"][0]["exact_match_depth"] == "clause"


def test_cli_parser_and_validation() -> None:
    """The evaluation CLI exposes expected arguments and path safety."""
    parser = eval_cli.build_arg_parser()
    args = parser.parse_args(
        ["--queries", "data/eval/manual_retrieval_queries.jsonl", "--top-k", "20"]
    )

    assert args.top_k == 20
    eval_cli.validate_cli_arguments(
        queries_path=Path("data/eval/manual_retrieval_queries.jsonl"),
        output_path=Path("artifacts/reports/retrieval/dense_retrieval_eval.json"),
        top_k=20,
    )
    with pytest.raises(ValueError, match="top-k"):
        eval_cli.validate_cli_arguments(
            queries_path=Path("data/eval/manual_retrieval_queries.jsonl"),
            output_path=Path("artifacts/reports/retrieval/dense_retrieval_eval.json"),
            top_k=0,
        )
    with pytest.raises(ValueError, match="protected"):
        eval_cli.validate_cli_arguments(
            queries_path=Path("data/eval/manual_retrieval_queries.jsonl"),
            output_path=Path("data/processed/eval.json"),
            top_k=20,
        )
