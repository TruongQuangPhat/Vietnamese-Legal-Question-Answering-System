"""Unit tests for Phase 7 processed JSONL validation models."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.processing.processed_jsonl_validation_models import (
    ProcessedJsonlIssue,
    ProcessedJsonlValidationConfig,
    ProcessedJsonlValidationIssueCode,
    ProcessedJsonlValidationReport,
)

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _issue(**overrides: object) -> ProcessedJsonlIssue:
    """Build a ProcessedJsonlIssue with sensible defaults."""
    payload: dict[str, object] = {
        "code": ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR,
        "message": "test issue",
        "law_id": "law_001",
        "chunk_id": "chunk_001",
        "line_number": 1,
        "context": {},
    }
    payload.update(overrides)
    return ProcessedJsonlIssue(**payload)


def _report(**overrides: object) -> ProcessedJsonlValidationReport:
    """Build a ProcessedJsonlValidationReport with sensible defaults."""
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "validator_version": "v0.1.0",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "duration_seconds": 1.0,
        "input_path": "data/processed/legal_chunks.jsonl",
        "chunking_report_path": "artifacts/reports/chunking/chunking_report.json",
        "hierarchy_dir": "data/interim",
        "traceability_checks_skipped": False,
        "total_lines": 100,
        "valid_chunks": 100,
        "invalid_chunks": 0,
        "jsonl_parse_failures": 0,
        "schema_failures": 0,
        "required_field_failures": 0,
        "duplicate_chunk_ids": 0,
        "count_reconciliation_failures": 0,
        "hash_mismatches": 0,
        "citation_failures": 0,
        "traceability_failures": 0,
        "contamination_failures": 0,
        "contamination_warnings": 0,
        "errors_total": 0,
        "warnings_total": 0,
        "chunks_by_level": {"article": 10, "clause": 20, "point": 70},
        "chunks_by_law": {"law_001": 100},
        "text_length_summary": {"min": 10, "max": 500, "mean": 100.0},
        "parent_text_length_summary": {"min": 100, "max": 5000, "mean": 1000.0},
        "long_parent_text_summary": {"short": 50, "medium": 30, "long": 15, "very_long": 5},
        "repealed_metadata_summary": {
            "is_empty_or_repealed": 10,
            "is_source_unit_repealed": 5,
        },
        "payload_readiness_summary": {"all_fields_present": 100},
        "embedding_readiness": {"ready": True, "empty_text_chunks": 0},
        "warning_distribution_summary": {"total_warnings": 0},
        "sample_failures": [],
        "sample_warnings": [],
        "status": "pass",
    }
    payload.update(overrides)
    return ProcessedJsonlValidationReport(**payload)


# ---------------------------------------------------------------------------
# Issue code enum
# ---------------------------------------------------------------------------


class TestIssueCodeEnum:
    """ProcessedJsonlValidationIssueCode has expected values."""

    def test_expected_values_exist(self) -> None:
        expected = {
            "JSONL_PARSE_ERROR",
            "SCHEMA_VALIDATION_FAILED",
            "REQUIRED_FIELD_MISSING",
            "HASH_MISMATCH",
            "CITATION_STRUCTURE_MISMATCH",
            "HARD_CONTAMINATION_FOUND",
            "WARNING_CONTAMINATION_FOUND",
            "REPEALED_METADATA_MISMATCH",
            "HIERARCHY_TRACEABILITY_FAILED",
            "TEXT_MISMATCH_HIERARCHY",
            "PARENT_TEXT_MISMATCH_HIERARCHY",
            "OFFSET_MISMATCH_HIERARCHY",
            "EMBEDDING_READINESS_ISSUE",
            "PAYLOAD_FIELD_MISSING",
            "VERY_LONG_PARENT_TEXT",
            "TEXT_LENGTH_WARNING",
            "EMPTY_TEXT_FOUND",
            "COUNT_RECONCILIATION_FAILED",
            "DUPLICATE_CHUNK_ID",
        }
        actual = {m.value for m in ProcessedJsonlValidationIssueCode}
        assert expected == actual

    def test_values_are_strings(self) -> None:
        for member in ProcessedJsonlValidationIssueCode:
            assert isinstance(member.value, str)
            assert len(member.value) > 0


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


class TestProcessedJsonlIssue:
    """ProcessedJsonlIssue model validation."""

    def test_minimal_issue(self) -> None:
        issue = ProcessedJsonlIssue(
            code=ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR,
            message="parse failed",
            law_id="law_001",
        )
        assert issue.code == ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR
        assert issue.message == "parse failed"
        assert issue.law_id == "law_001"
        assert issue.chunk_id is None
        assert issue.line_number is None
        assert issue.context == {}

    def test_full_issue(self) -> None:
        issue = _issue()
        assert issue.chunk_id == "chunk_001"
        assert issue.line_number == 1

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):  # ValidationError
            ProcessedJsonlIssue(
                code=ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR,
                message="test",
                law_id="law_001",
                unknown_field="value",  # type: ignore[call-arg]
            )

    def test_message_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            ProcessedJsonlIssue(
                code=ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR,
                message="",
                law_id="law_001",
            )

    def test_law_id_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            ProcessedJsonlIssue(
                code=ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR,
                message="test",
                law_id="",
            )

    def test_line_number_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _issue(line_number=0)

    def test_serialization_roundtrip(self) -> None:
        issue = _issue()
        data = issue.model_dump(mode="json")
        restored = ProcessedJsonlIssue(**data)
        assert restored == issue


# ---------------------------------------------------------------------------
# Report model — status logic
# ---------------------------------------------------------------------------


class TestReportStatus:
    """ProcessedJsonlValidationReport status field logic."""

    def test_pass_when_no_errors_no_warnings(self) -> None:
        report = _report(errors_total=0, warnings_total=0, status="pass")
        assert report.status == "pass"

    def test_fail_when_errors_total_positive(self) -> None:
        report = _report(errors_total=1, warnings_total=0, status="pass_with_warnings")
        assert report.status == "fail"

    def test_pass_with_warnings_when_only_warnings(self) -> None:
        report = _report(errors_total=0, warnings_total=1, status="pass")
        assert report.status == "pass_with_warnings"

    def test_pass_when_errors_warnings_both_zero(self) -> None:
        report = _report(errors_total=0, warnings_total=0)
        assert report.status == "pass"

    def test_status_fail_overrides_pass_with_warnings(self) -> None:
        report = _report(errors_total=1, warnings_total=1, status="pass_with_warnings")
        assert report.status == "fail"

    def test_status_fail_overrides_pass(self) -> None:
        report = _report(errors_total=1, warnings_total=0, status="pass")
        assert report.status == "fail"

    def test_pass_with_warnings_overrides_pass_when_warnings_exist(self) -> None:
        report = _report(errors_total=0, warnings_total=1, status="pass")
        assert report.status == "pass_with_warnings"

    def test_pass_restored_when_errors_warnings_become_zero(self) -> None:
        report = _report(errors_total=0, warnings_total=0, status="pass_with_warnings")
        assert report.status == "pass"


# ---------------------------------------------------------------------------
# Report model — serialization
# ---------------------------------------------------------------------------


class TestReportSerialization:
    """ProcessedJsonlValidationReport serialization and Vietnamese preservation."""

    def test_serializes_to_json(self) -> None:
        report = _report()
        data = report.model_dump(mode="json")
        assert isinstance(data, dict)
        assert data["status"] == "pass"
        assert data["schema_version"] == "1.0"
        assert data["warning_distribution_summary"] == {"total_warnings": 0}

    def test_vietnamese_preserved_in_serialization(self) -> None:
        report = _report(
            sample_warnings=[
                _issue(
                    message="Chứa BỘ TRƯỞNG trong văn bản",
                    law_id="luật_abc",
                )
            ],
        )
        text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
        assert "Chứa" in text
        assert "BỘ TRƯỞNG" in text
        assert "\\u" not in text

    def test_vietnamese_preserved_in_file_write(self, tmp_path: Path) -> None:
        report = _report(
            sample_warnings=[_issue(message="Văn bản chứa CHỦ TỊCH QUỐC HỘI", law_id="luật_xyz")],
        )
        out = tmp_path / "report.json"
        out.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        content = out.read_text(encoding="utf-8")
        assert "CHỦ TỊCH QUỐC HỘI" in content
        assert "\\u" not in content

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            _report(unknown_field="value")  # type: ignore[call-arg]

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _report(duration_seconds=-1.0)

    def test_negative_counters_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _report(total_lines=-1)

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _report(status="unknown")  # type: ignore[arg-type]

    def test_sample_failures_and_warnings_are_capped_lists(self) -> None:
        """sample_failures and sample_warnings are the only sample lists."""
        issue = _issue()
        report = _report(
            sample_failures=[issue],
            sample_warnings=[issue],
            errors_total=1,
            warnings_total=1,
        )
        assert len(report.sample_failures) == 1
        assert len(report.sample_warnings) == 1
        # No uncapped errors/warnings fields
        assert not hasattr(report, "errors")
        assert not hasattr(report, "warnings")

    def test_status_uses_total_counters_not_sample_lists(self) -> None:
        """Status logic uses errors_total/warnings_total, not sample lists."""
        # Even with empty samples, status should be fail if errors_total > 0
        report = _report(
            sample_failures=[],
            sample_warnings=[],
            errors_total=5,
            warnings_total=0,
            status="pass",
        )
        assert report.status == "fail"
        # Even with empty samples, status should be pass_with_warnings
        report2 = _report(
            sample_failures=[],
            sample_warnings=[],
            errors_total=0,
            warnings_total=3,
            status="pass",
        )
        assert report2.status == "pass_with_warnings"


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------


class TestProcessedJsonlValidationConfig:
    """ProcessedJsonlValidationConfig model validation."""

    def test_default_values(self) -> None:
        config = ProcessedJsonlValidationConfig(
            schema_version="1.0",
            validator_version="v0.1.0",
        )
        assert config.input_path == "data/processed/legal_chunks.jsonl"
        assert config.chunking_report_path == "artifacts/reports/chunking/chunking_report.json"
        assert config.hierarchy_dir == "data/interim"
        assert (
            config.report_path
            == "artifacts/reports/chunking/processed_jsonl_validation_report.json"
        )
        assert config.require_hierarchy_traceability is True
        assert config.max_sample_failures == 50
        assert config.max_sample_warnings == 50
        assert config.parent_text_short_chars == 4000
        assert config.parent_text_medium_chars == 10000
        assert config.parent_text_long_chars == 15000
        assert config.parent_text_very_long_chars == 20000
        assert len(config.hard_contamination_markers) == 4
        assert len(config.warning_contamination_markers) == 5
        assert len(config.repealed_placeholder_patterns) == 4

    def test_hard_contamination_markers(self) -> None:
        config = ProcessedJsonlValidationConfig(
            schema_version="1.0",
            validator_version="v0.1.0",
        )
        expected_hard = {
            "XÁC THỰC VĂN BẢN HỢP NHẤT",
            "Nơi nhận:",
            "Lưu:",
            "Văn bản này được hợp nhất",
        }
        assert set(config.hard_contamination_markers) == expected_hard

    def test_warning_contamination_markers(self) -> None:
        config = ProcessedJsonlValidationConfig(
            schema_version="1.0",
            validator_version="v0.1.0",
        )
        expected_warning = {
            "BỘ TRƯỞNG",
            "CHỦ NHIỆM",
            "CHỦ TỊCH QUỐC HỘI",
            "TM. QUỐC HỘI",
            "KT. BỘ TRƯỞNG",
        }
        assert set(config.warning_contamination_markers) == expected_warning

    def test_repealed_patterns(self) -> None:
        config = ProcessedJsonlValidationConfig(
            schema_version="1.0",
            validator_version="v0.1.0",
        )
        expected_patterns = {
            "(được bãi bỏ)",
            "Điều này được bãi bỏ",
            "Khoản này được bãi bỏ",
            "Điểm này được bãi bỏ",
        }
        assert set(config.repealed_placeholder_patterns) == expected_patterns

    def test_custom_thresholds(self) -> None:
        config = ProcessedJsonlValidationConfig(
            schema_version="1.0",
            validator_version="v0.1.0",
            parent_text_very_long_chars=30000,
            max_sample_failures=100,
        )
        assert config.parent_text_very_long_chars == 30000
        assert config.max_sample_failures == 100

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ProcessedJsonlValidationConfig(
                schema_version="1.0",
                validator_version="v0.1.0",
                unknown_field="value",  # type: ignore[call-arg]
            )

    def test_negative_thresholds_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProcessedJsonlValidationConfig(
                schema_version="1.0",
                validator_version="v0.1.0",
                parent_text_short_chars=-1,
            )

    def test_zero_max_samples_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProcessedJsonlValidationConfig(
                schema_version="1.0",
                validator_version="v0.1.0",
                max_sample_failures=0,
            )


# ---------------------------------------------------------------------------
# Config YAML loading
# ---------------------------------------------------------------------------


class TestConfigYamlLoading:
    """Config loads correctly from YAML file."""

    def test_loads_default_yaml(self, tmp_path: Path) -> None:
        yaml_content = """\
schema_version: "1.0"
validator_version: "v0.1.0"
input_path: "data/processed/legal_chunks.jsonl"
chunking_report_path: "artifacts/reports/chunking/chunking_report.json"
hierarchy_dir: "data/interim"
report_path: "artifacts/reports/chunking/processed_jsonl_validation_report.json"
require_hierarchy_traceability: true
max_sample_failures: 50
max_sample_warnings: 50
parent_text_short_chars: 4000
parent_text_medium_chars: 10000
parent_text_long_chars: 15000
parent_text_very_long_chars: 20000
hard_contamination_markers:
- "XÁC THỰC VĂN BẢN HỢP NHẤT"
- "Nơi nhận:"
warning_contamination_markers:
- "BỘ TRƯỞNG"
repealed_placeholder_patterns:
- "(được bãi bỏ)"
"""
        yaml_file = tmp_path / "config.yml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        import yaml

        with yaml_file.open("r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh)

        config = ProcessedJsonlValidationConfig(**payload)
        assert config.schema_version == "1.0"
        assert config.validator_version == "v0.1.0"
        assert config.require_hierarchy_traceability is True
        assert config.max_sample_failures == 50
        assert "XÁC THỰC VĂN BẢN HỢP NHẤT" in config.hard_contamination_markers
        assert "BỘ TRƯỞNG" in config.warning_contamination_markers
        assert "(được bãi bỏ)" in config.repealed_placeholder_patterns

    def test_yaml_vietnamese_preserved(self, tmp_path: Path) -> None:
        yaml_content = """\
schema_version: "1.0"
validator_version: "v0.1.0"
input_path: "data/processed/legal_chunks.jsonl"
chunking_report_path: "artifacts/reports/chunking/chunking_report.json"
hierarchy_dir: "data/interim"
report_path: "artifacts/reports/chunking/processed_jsonl_validation_report.json"
require_hierarchy_traceability: true
max_sample_failures: 50
max_sample_warnings: 50
parent_text_short_chars: 4000
parent_text_medium_chars: 10000
parent_text_long_chars: 15000
parent_text_very_long_chars: 20000
hard_contamination_markers:
- "XÁC THỰC VĂN BẢN HỢP NHẤT"
- "Nơi nhận:"
warning_contamination_markers:
- "CHỦ TỊCH QUỐC HỘI"
repealed_placeholder_patterns:
- "Điều này được bãi bỏ"
"""
        yaml_file = tmp_path / "config.yml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        import yaml

        with yaml_file.open("r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh)

        config = ProcessedJsonlValidationConfig(**payload)
        assert "XÁC THỰC VĂN BẢN HỢP NHẤT" in config.hard_contamination_markers
        assert "CHỦ TỊCH QUỐC HỘI" in config.warning_contamination_markers

        # Verify the YAML file itself preserves Vietnamese
        raw = yaml_file.read_text(encoding="utf-8")
        assert "XÁC THỰC" in raw
        assert "\\u" not in raw


# ---------------------------------------------------------------------------
# Cross-model: issue in report
# ---------------------------------------------------------------------------


class TestIssueInReport:
    """Issues integrate correctly into the report."""

    def test_sample_failures_populated(self) -> None:
        issue = _issue(
            code=ProcessedJsonlValidationIssueCode.HASH_MISMATCH,
            message="hash mismatch detected",
        )
        report = _report(
            sample_failures=[issue],
            errors_total=1,
            warnings_total=0,
            status="fail",
        )
        assert len(report.sample_failures) == 1
        assert report.sample_failures[0].code == ProcessedJsonlValidationIssueCode.HASH_MISMATCH
        assert report.status == "fail"

    def test_sample_warnings_populated(self) -> None:
        issue = _issue(
            code=ProcessedJsonlValidationIssueCode.WARNING_CONTAMINATION_FOUND,
            message="found BỘ TRƯỞNG",
        )
        report = _report(
            sample_warnings=[issue],
            errors_total=0,
            warnings_total=1,
            status="pass_with_warnings",
        )
        assert len(report.sample_warnings) == 1
        assert report.status == "pass_with_warnings"

    def test_report_counts_are_non_negative(self) -> None:
        report = _report(
            total_lines=40389,
            valid_chunks=40389,
            invalid_chunks=0,
        )
        assert report.total_lines == 40389
        assert report.valid_chunks == 40389
        assert report.invalid_chunks == 0
