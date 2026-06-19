from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.benchmark.enums import (
    ExpectedDecision,
    LegalDomain,
    QuestionType,
)
from src.evaluation.benchmark.exceptions import BenchmarkLoadError
from src.evaluation.benchmark.loader import load_benchmark_queries, load_split_manifest


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _query_record(query_id: str = "q1") -> dict[str, object]:
    return {
        "id": query_id,
        "query": "Câu hỏi pháp lý giả lập có dấu tiếng Việt?",
        "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY.value,
        "question_types": [QuestionType.SINGLE_ARTICLE_LOOKUP.value],
        "expected_decision": ExpectedDecision.ANSWER_ALLOWED.value,
        "reviewer_notes": "Synthetic fixture.",
    }


def test_load_valid_utf8_jsonl_and_preserve_vietnamese_diacritics(tmp_path: Path) -> None:
    path = tmp_path / "queries.jsonl"
    _write_jsonl(path, [_query_record()])

    records = load_benchmark_queries(path)

    assert records[0].query == "Câu hỏi pháp lý giả lập có dấu tiếng Việt?"


def test_malformed_json_reports_line_number(tmp_path: Path) -> None:
    path = tmp_path / "queries.jsonl"
    _write_jsonl(path, [_query_record("q1")])
    path.write_text(path.read_text(encoding="utf-8") + "{bad json}\n", encoding="utf-8")

    with pytest.raises(BenchmarkLoadError, match=r"queries\.jsonl:2"):
        load_benchmark_queries(path)


def test_duplicate_ids_fail(tmp_path: Path) -> None:
    path = tmp_path / "queries.jsonl"
    _write_jsonl(path, [_query_record("q1"), _query_record("q1")])

    with pytest.raises(BenchmarkLoadError, match="duplicate record ID"):
        load_benchmark_queries(path)


def test_unknown_fields_fail(tmp_path: Path) -> None:
    path = tmp_path / "queries.jsonl"
    record = _query_record()
    record["unexpected"] = "bad"
    _write_jsonl(path, [record])

    with pytest.raises(BenchmarkLoadError, match="Extra inputs"):
        load_benchmark_queries(path)


def test_invalid_record_is_not_silently_skipped(tmp_path: Path) -> None:
    path = tmp_path / "queries.jsonl"
    record = _query_record()
    record["query"] = ""
    _write_jsonl(path, [_query_record("q1"), record])

    with pytest.raises(BenchmarkLoadError, match=r"queries\.jsonl:2"):
        load_benchmark_queries(path)


def test_duplicate_json_keys_fail_for_manifest_assignments(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    path.write_text(
        """
{
  "schema_version": "1.0",
  "benchmark_version": "draft",
  "strategy": "connected_component_grouped_split",
  "seed": 1,
  "development_ratio": 0.5,
  "grouping_fields": ["case_family_id", "source_provision_group_id"],
  "stratification_fields": [],
  "input_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "assignments": {
    "q1": "development",
    "q1": "held_out_test"
  },
  "created_at": "2026-01-01T00:00:00Z"
}
""",
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkLoadError, match="duplicate JSON object key"):
        load_split_manifest(path)
