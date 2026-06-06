"""Tests for the Phase 5 batch legal parsing service."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.processing.legal_hierarchy_models import (
    LegalParsingStatus,
    ParsingIssueCode,
    StructuredParsingIssue,
)
from src.processing.legal_parser import LegalParser
from src.services.legal_parsing_service import (
    LegalParsingService,
    LegalParsingServiceError,
    discover_normalized_inputs,
)


class StepClock:
    """Deterministic UTC clock for service timing tests."""

    def __init__(self) -> None:
        """Initialize the clock at a stable UTC instant."""
        self._current = datetime(2026, 6, 5, 0, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        """Return the current instant and advance by one second."""
        value = self._current
        self._current += timedelta(seconds=1)
        return value


def _artifact_payload(
    normalized_text: str,
    *,
    law_id: str,
    article_count: int = 1,
    max_article: int = 1,
    has_article_1: bool = True,
) -> dict[str, Any]:
    """Build a minimal normalized artifact payload for service tests."""
    return {
        "law_id": law_id,
        "law_name": f"Luật Kiểm thử {law_id}",
        "source_url": f"https://thuvienphapluat.vn/{law_id}.aspx",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "raw_artifact_path": f"data/raw/{law_id}/latest/main.html",
        "normalized_text": normalized_text,
        "text_stats": {
            "normalized_text_chars": len(normalized_text),
            "line_count": len(normalized_text.splitlines()),
        },
        "markers": {
            "article_reference_count": article_count,
            "article_heading_count": article_count,
            "max_heading_article_number": max_article,
            "has_heading_article_1": has_article_1,
            "heading_sequence_score": 1.0,
        },
        "warnings": [],
        "metadata": {"cleaner_version": "v0.8.0"},
        "candidate_info": {"selection_strategy": "fixture"},
    }


def _write_normalized(
    input_dir: Path,
    law_id: str,
    text: str,
    *,
    article_count: int = 1,
    max_article: int = 1,
    has_article_1: bool = True,
    cleaned_text: str | None = None,
) -> Path:
    """Write one normalized fixture under input_dir/{LAW_ID}/normalized.json."""
    law_dir = input_dir / law_id
    law_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = law_dir / "normalized.json"
    payload = _artifact_payload(
        text,
        law_id=law_id,
        article_count=article_count,
        max_article=max_article,
        has_article_1=has_article_1,
    )
    normalized_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if cleaned_text is not None:
        (law_dir / "cleaned.txt").write_text(cleaned_text, encoding="utf-8")
    return normalized_path


def _run_service(
    input_dir: Path,
    output_dir: Path,
    report_path: Path,
    *,
    law_ids: list[str] | None = None,
    overwrite: bool = False,
    parser: LegalParser | None = None,
    hierarchy_writer: Any | None = None,
    report_writer: Any | None = None,
):
    """Run the parsing service with a deterministic clock."""
    return LegalParsingService(
        parser=parser,
        clock=StepClock(),
        hierarchy_writer=hierarchy_writer,
        report_writer=report_writer,
    ).run(
        input_dir=input_dir,
        output_dir=output_dir,
        report_path=report_path,
        law_ids=law_ids,
        overwrite=overwrite,
    )


def _issue_codes(issues: list[StructuredParsingIssue]) -> list[ParsingIssueCode]:
    """Return issue codes in emitted order."""
    return [issue.code for issue in issues]


def test_discovers_filters_and_sorts_normalized_inputs(tmp_path: Path) -> None:
    """Discovery only selects normalized.json files under law ID directories."""
    input_dir = tmp_path / "input"
    _write_normalized(input_dir, "B_LAW", "Điều 1. B\nNội dung.")
    _write_normalized(input_dir, "A_LAW", "Điều 1. A\nNội dung.")
    (input_dir / "A_LAW" / "hierarchy.json").write_text("{}", encoding="utf-8")
    (input_dir / "loose_normalized.json").write_text("{}", encoding="utf-8")

    discovered = discover_normalized_inputs(input_dir)
    selected = discover_normalized_inputs(input_dir, law_ids=["B_LAW"])

    assert [item.law_id for item in discovered] == ["A_LAW", "B_LAW"]
    assert [item.law_id for item in selected] == ["B_LAW"]
    assert discovered[0].normalized_path == input_dir / "A_LAW" / "normalized.json"
    assert discovered[0].cleaned_path == input_dir / "A_LAW" / "cleaned.txt"


def test_requested_missing_law_produces_failed_result(tmp_path: Path) -> None:
    """Requested laws without normalized input are reported deterministically."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. A\nNội dung.")

    result = _run_service(
        input_dir,
        output_dir,
        report_path,
        law_ids=["MISSING_LAW", "A_LAW"],
    )

    assert [item.law_id for item in result.report.results] == ["A_LAW", "MISSING_LAW"]
    missing = result.report.results[1]
    assert missing.status == LegalParsingStatus.FAILED
    assert missing.input_path == str(input_dir / "MISSING_LAW" / "normalized.json")
    assert _issue_codes(missing.errors) == [ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE]
    assert result.failed_law_ids == ["MISSING_LAW"]


def test_success_and_success_with_warnings_write_hierarchy_outputs(tmp_path: Path) -> None:
    """Successful and warning-bearing parser outputs write hierarchy JSON."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.")
    _write_normalized(
        input_dir,
        "B_LAW",
        "Điều 1. Một\n1. Khoản một\n1. Khoản lặp",
    )

    result = _run_service(input_dir, output_dir, report_path)

    a_output = output_dir / "A_LAW" / "hierarchy.json"
    b_output = output_dir / "B_LAW" / "hierarchy.json"
    assert result.report.successful == 1
    assert result.report.success_with_warnings == 1
    assert result.report.failed == 0
    assert a_output.exists()
    assert b_output.exists()
    assert result.written_hierarchy_paths == [str(a_output), str(b_output)]
    assert result.report.results[0].output_path == str(a_output)
    assert result.report.results[1].output_path == str(b_output)
    assert "Luật Kiểm thử A_LAW" in a_output.read_text(encoding="utf-8")
    assert "\\u" not in a_output.read_text(encoding="utf-8")


def test_failed_parse_does_not_write_hierarchy_but_report_is_written(tmp_path: Path) -> None:
    """Invalid per-law input is isolated and still appears in the report."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.")
    invalid_path = _write_normalized(input_dir, "BAD_LAW", "Điều 1. Hỏng\nNội dung.")
    payload = json.loads(invalid_path.read_text(encoding="utf-8"))
    del payload["raw_artifact_path"]
    invalid_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _run_service(input_dir, output_dir, report_path)

    assert result.report.total_documents == 2
    assert result.report.successful == 1
    assert result.report.failed == 1
    assert (output_dir / "A_LAW" / "hierarchy.json").exists()
    assert not (output_dir / "BAD_LAW" / "hierarchy.json").exists()
    assert report_path.exists()
    assert result.failed_law_ids == ["BAD_LAW"]
    assert ParsingIssueCode.SCHEMA_VALIDATION_FAILED in _issue_codes(result.report.errors)


def test_existing_hierarchy_requires_overwrite_to_replace(tmp_path: Path) -> None:
    """Existing hierarchy outputs are protected unless overwrite=True."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.")
    existing = output_dir / "A_LAW" / "hierarchy.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing", encoding="utf-8")

    blocked = _run_service(input_dir, output_dir, report_path)
    blocked_text = existing.read_text(encoding="utf-8")
    overwritten = _run_service(input_dir, output_dir, report_path, overwrite=True)

    assert blocked.report.failed == 1
    assert blocked.skipped_law_ids == ["A_LAW"]
    assert blocked_text == "existing"
    assert existing.read_text(encoding="utf-8") != ""
    assert existing.read_text(encoding="utf-8") != "existing"
    assert overwritten.report.successful == 1
    assert overwritten.written_hierarchy_paths == [str(existing)]


def test_report_aggregation_dedupes_identical_issues_and_keeps_distinct_laws(
    tmp_path: Path,
) -> None:
    """Report totals, summary, warnings, and errors aggregate deterministically."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.", article_count=2)
    _write_normalized(input_dir, "B_LAW", "Điều 1. Hai\nNội dung hai.", article_count=2)

    result = _run_service(input_dir, output_dir, report_path)
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert result.report.total_documents == 2
    assert result.report.success_with_warnings == 2
    assert result.report.nodes_by_level == {"law": 2, "article": 2}
    assert result.report.validation_summary.article_heading_mismatch == 2
    assert [item["law_id"] for item in report_payload["results"]] == ["A_LAW", "B_LAW"]
    assert len(result.report.warnings) == 2
    assert all(
        warning.code == ParsingIssueCode.ARTICLE_COUNT_MISMATCH
        for warning in result.report.warnings
    )
    assert result.report.input_dir == str(input_dir)
    assert result.report.output_dir == str(output_dir)
    assert result.report.started_at == "2026-06-05T00:00:00Z"
    assert result.report.finished_at.endswith("Z")
    assert result.report.duration_seconds >= 0


def test_top_level_report_deduplicates_identical_warnings(tmp_path: Path) -> None:
    """Top-level report warning aggregation removes exact duplicate issues."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.", article_count=2)

    class DuplicateWarningParser(LegalParser):
        """Parser test double that duplicates an already emitted warning."""

        def parse_file(self, *, normalized_path: Path, cleaned_path: Path | None = None):
            """Return a valid real parser result with duplicated warnings."""
            result = super().parse_file(normalized_path=normalized_path, cleaned_path=cleaned_path)
            duplicate_warnings = [*result.parsing_result.warnings, *result.parsing_result.warnings]
            return result.model_copy(
                update={
                    "warnings": [*result.warnings, *result.warnings],
                    "parsing_result": result.parsing_result.model_copy(
                        update={"warnings": duplicate_warnings},
                        deep=True,
                    ),
                },
                deep=True,
            )

    result = _run_service(
        input_dir,
        output_dir,
        report_path,
        parser=DuplicateWarningParser(),
    )

    assert result.report.success_with_warnings == 1
    assert len(result.report.results[0].warnings) == 2
    assert len(result.report.warnings) == 1
    assert result.report.warnings[0].code == ParsingIssueCode.ARTICLE_COUNT_MISMATCH


def test_hierarchy_write_failure_isolated_to_one_law(tmp_path: Path) -> None:
    """A hierarchy write failure marks one law failed and continues the batch."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.")
    _write_normalized(input_dir, "B_LAW", "Điều 1. Hai\nNội dung hai.")

    def writer(path: Path, document: Any) -> None:
        if path.parent.name == "A_LAW":
            raise OSError("forced hierarchy write failure")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document.model_dump(mode="json")), encoding="utf-8")

    result = _run_service(input_dir, output_dir, report_path, hierarchy_writer=writer)

    assert result.report.failed == 1
    assert result.report.successful == 1
    assert result.failed_law_ids == ["A_LAW"]
    assert not (output_dir / "A_LAW" / "hierarchy.json").exists()
    assert (output_dir / "B_LAW" / "hierarchy.json").exists()
    assert ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE in _issue_codes(result.report.errors)


def test_parser_exception_isolated_to_one_law(tmp_path: Path) -> None:
    """An unexpected parser exception is converted to a per-law failed result."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.")
    _write_normalized(input_dir, "B_LAW", "Điều 1. Hai\nNội dung hai.")

    class SelectiveParser(LegalParser):
        """Parser test double that raises for one law only."""

        def parse_file(self, *, normalized_path: Path, cleaned_path: Path | None = None):
            """Raise for A_LAW and delegate to the real parser otherwise."""
            if normalized_path.parent.name == "A_LAW":
                raise RuntimeError("forced parser failure")
            return super().parse_file(normalized_path=normalized_path, cleaned_path=cleaned_path)

    result = _run_service(input_dir, output_dir, report_path, parser=SelectiveParser())

    assert result.report.failed == 1
    assert result.report.successful == 1
    assert result.failed_law_ids == ["A_LAW"]
    assert (output_dir / "B_LAW" / "hierarchy.json").exists()
    assert ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE in _issue_codes(result.report.errors)


def test_report_write_failure_surfaces_service_error(tmp_path: Path) -> None:
    """Report write failures raise a structured service-level error."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.")

    def failing_report_writer(path: Path, report: Any) -> None:
        raise OSError(f"cannot write {path}: {report.total_documents}")

    with pytest.raises(LegalParsingServiceError) as exc_info:
        _run_service(input_dir, output_dir, report_path, report_writer=failing_report_writer)

    assert exc_info.value.issue.code == ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE
    assert exc_info.value.issue.context["report_path"] == str(report_path)


def test_service_result_is_deterministic_with_fake_clock(tmp_path: Path) -> None:
    """Two equivalent runs with fresh fake clocks produce identical reports."""
    input_dir = tmp_path / "input"
    output_one = tmp_path / "output_one"
    output_two = tmp_path / "output_two"
    report_one = tmp_path / "reports_one" / "legal_parsing_report.json"
    report_two = tmp_path / "reports_two" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung một.")

    first = _run_service(input_dir, output_one, report_one)
    second = _run_service(input_dir, output_two, report_two)
    first_dump = first.report.model_dump(mode="json")
    second_dump = second.report.model_dump(mode="json")
    first_dump["output_dir"] = "<output>"
    second_dump["output_dir"] = "<output>"
    first_dump["results"][0]["output_path"] = "<hierarchy>"
    second_dump["results"][0]["output_path"] = "<hierarchy>"

    assert first_dump == second_dump
