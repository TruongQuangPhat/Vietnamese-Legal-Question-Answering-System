"""Tests for official indexing artifact summary and sanitization policy."""

from __future__ import annotations

import json
from pathlib import Path

from src.indexing.official_artifacts import (
    build_processed_corpus_validation_summary,
    sanitize_official_indexing_run,
)


def _raw_validation_report() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "pass_with_warnings",
        "input_path": "data/processed/legal_chunks.jsonl",
        "total_lines": 10,
        "valid_chunks": 10,
        "invalid_chunks": 0,
        "errors_total": 0,
        "warnings_total": 2,
        "contamination_warnings": 1,
        "chunks_by_level": {"clause": 10},
        "chunks_by_law": {"BLDS_2015": 10},
        "text_length_summary": {"count": 10, "short_text_warning_count": 1},
        "parent_text_length_summary": {"count": 10},
        "repealed_metadata_summary": {"metadata_empty_or_repealed_count": 0},
        "warning_distribution_summary": {
            "total_warnings": 2,
            "warning_issue_code_counts": {
                "TEXT_LENGTH_WARNING": 1,
                "WARNING_CONTAMINATION_FOUND": 1,
            },
            "deferred_resolution": {
                "reason": "warning-distribution audit only audits warning distribution."
            },
            "examples": [{"source_check": "contamination_audit"}],
        },
        "embedding_readiness": {
            "embedding_ready": True,
            "readiness_status": "ready_with_warnings",
            "payload_ready_rate": 1.0,
            "blocking_reasons": [],
            "warning_categories": {
                "contamination_warnings": 1,
                "short_text_warnings": 1,
            },
            "deferred_warning_followups": [{"source_check": "contamination_audit"}],
            "recommended_next_actions": ["Proceed to embedding/indexing."],
        },
    }


def test_clean_processed_corpus_summary_has_only_operational_fields() -> None:
    """Internal validation workflow wording is excluded from the clean summary."""
    summary = build_processed_corpus_validation_summary(_raw_validation_report())
    payload = summary.model_dump(mode="json")
    serialized = json.dumps(payload)

    assert payload["report_type"] == "processed_corpus_validation_summary"
    assert payload["run_type"] == "official_full_indexing"
    assert payload["workflow_name"] == "corpus_validation"
    assert payload["contamination_warnings"] == 1
    assert payload["short_text_warnings"] == 1
    assert "source_check" not in serialized


def test_sanitizer_cleans_existing_official_package(tmp_path: Path) -> None:
    """Existing reports are rewritten and the raw validation report is removed."""
    reports_root = tmp_path / "artifacts/reports/indexing"
    run_dir = reports_root / "run-1"
    run_dir.mkdir(parents=True)
    raw_path = run_dir / "processed_jsonl_validation_report.json"
    raw_path.write_text(json.dumps(_raw_validation_report()), encoding="utf-8")
    indexing_path = run_dir / "indexing_report_full.json"
    indexing_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "report_type": "indexing_report",
                "run_type": "official_full_indexing",
                "workflow_name": "embedding_indexing",
                "processed_validation_report_path": str(raw_path),
            }
        ),
        encoding="utf-8",
    )
    validation_path = run_dir / "index_validation_report_full.json"
    validation_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "report_type": "index_validation_report",
                "run_type": "official_full_index_validation",
                "workflow_name": "index_validation",
                "collection_schema_status": "pass",
                "payload_validation_status": "pass",
                "vector_validation_status": "pass",
                "filter_validation_status": "pass",
                "retrieval_sanity_status": "pass",
            }
        ),
        encoding="utf-8",
    )

    sanitize_official_indexing_run(run_dir, reports_root=reports_root)

    indexing = json.loads(indexing_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    summary_path = run_dir / "processed_corpus_validation_summary.json"
    assert indexing["processed_validation_report_path"].endswith(
        "processed_corpus_validation_summary.json"
    )
    assert validation["retrieval_baseline_ready"] is True
    assert summary_path.is_file()
    assert not raw_path.exists()
