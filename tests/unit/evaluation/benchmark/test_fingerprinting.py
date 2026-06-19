from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.evaluation.benchmark.enums import BenchmarkSplit, ReviewStatus
from src.evaluation.benchmark.fingerprinting import (
    canonical_json_bytes,
    sha256_canonical_data,
    sha256_file,
    sha256_records_by_stable_id,
    sha256_split_manifest,
)
from src.evaluation.benchmark.schemas import BenchmarkManifest, BenchmarkQuery, SplitManifest


def _split_manifest() -> SplitManifest:
    return SplitManifest(
        schema_version="1.0",
        benchmark_version="draft",
        strategy="connected_component_grouped_split",
        seed=1,
        development_ratio=0.5,
        grouping_fields=["case_family_id", "source_provision_group_id"],
        stratification_fields=[],
        input_fingerprint="a" * 64,
        assignments={"q1": BenchmarkSplit.DEVELOPMENT},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_canonical_hash_is_deterministic() -> None:
    left = sha256_canonical_data({"b": 2, "a": 1})
    right = sha256_canonical_data({"a": 1, "b": 2})
    assert left == right
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_meaningful_record_change_changes_hash() -> None:
    assert sha256_canonical_data({"a": 1}) != sha256_canonical_data({"a": 2})


def test_file_hash_changes_after_mutation(tmp_path: Path) -> None:
    path = tmp_path / "file.json"
    path.write_text("one\n", encoding="utf-8")
    before = sha256_file(path)
    path.write_text("two\n", encoding="utf-8")
    assert sha256_file(path) != before


def test_secret_like_data_is_not_serialized_into_manifest() -> None:
    with pytest.raises(ValidationError, match="secret-like"):
        BenchmarkManifest(
            schema_version="1.0",
            benchmark_version="draft",
            freeze_date=datetime(2026, 1, 1, tzinfo=UTC),
            record_counts={"queries": 1},
            raw_file_sha256={"queries": "a" * 64},
            canonical_content_sha256={"queries": "b" * 64},
            corpus_registry_raw_file_sha256="c" * 64,
            processed_chunks_raw_file_sha256="d" * 64,
            split_manifest_raw_file_sha256="e" * 64,
            split_manifest_canonical_content_sha256="f" * 64,
            manifest_canonical_content_sha256="1" * 64,
            review_status=ReviewStatus.FROZEN,
            change_log=["sk-or-secret"],
        )


def test_manifest_verification_detects_tampering(tmp_path: Path) -> None:
    manifest = _split_manifest()
    path = tmp_path / "split.json"
    path.write_bytes(canonical_json_bytes(manifest))
    expected = sha256_split_manifest(manifest)
    assert sha256_file(path) == expected
    path.write_text(
        path.read_text(encoding="utf-8").replace("development", "held_out_test"), encoding="utf-8"
    )
    assert sha256_file(path) != expected


def _query(query_id: str, query: str) -> BenchmarkQuery:
    return BenchmarkQuery.model_validate(
        {
            "id": query_id,
            "query": query,
            "primary_domain": "civil_family_identity",
            "question_types": ["single_article_lookup"],
            "expected_decision": "answer_allowed",
            "reviewer_notes": "Synthetic fixture.",
        }
    )


def test_jsonl_line_reordering_does_not_change_semantic_dataset_hash() -> None:
    left = [_query("b", "Câu hỏi có dấu tiếng Việt?"), _query("a", "Another question?")]
    right = list(reversed(left))
    assert sha256_records_by_stable_id(
        left, lambda record: record.id
    ) == sha256_records_by_stable_id(right, lambda record: record.id)


def test_raw_file_hash_changes_when_line_order_changes(tmp_path: Path) -> None:
    path = tmp_path / "queries.jsonl"
    first = '{"id":"a"}\n{"id":"b"}\n'
    second = '{"id":"b"}\n{"id":"a"}\n'
    path.write_text(first, encoding="utf-8")
    before = sha256_file(path)
    path.write_text(second, encoding="utf-8")
    assert sha256_file(path) != before


def test_vietnamese_diacritics_are_preserved_in_canonical_bytes() -> None:
    payload = {"query": "Câu hỏi về quyền dân sự"}
    assert "Câu hỏi".encode() in canonical_json_bytes(payload)
