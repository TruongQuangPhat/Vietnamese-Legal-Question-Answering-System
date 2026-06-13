"""Tests for the Phase 5 legal hierarchy parsing CLI entrypoint."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.corpus import parse_legal_hierarchy
from src.processing.legal_hierarchy_models import ParsingIssueCode, StructuredParsingIssue
from src.services.legal_parsing_service import LegalParsingServiceError


def _artifact_payload(
    normalized_text: str,
    *,
    law_id: str,
    article_count: int = 1,
    max_article: int = 1,
    has_article_1: bool = True,
) -> dict[str, Any]:
    """Build a minimal normalized artifact payload for CLI tests."""
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
) -> Path:
    """Write a normalized artifact under a temp input directory."""
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
    return normalized_path


def _cli_args(
    input_dir: Path,
    output_dir: Path,
    report_path: Path,
    *extra: str,
) -> list[str]:
    """Build common CLI arguments with temp paths."""
    return [
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
        "--report",
        str(report_path),
        *extra,
    ]


def test_help_and_argument_parsing(capsys: pytest.CaptureFixture[str]) -> None:
    """Help text and supported flags are exposed by the CLI parser."""
    with pytest.raises(SystemExit) as exc_info:
        parse_legal_hierarchy.main(["--help"])

    output = capsys.readouterr().out
    assert exc_info.value.code == 0
    assert "--input-dir" in output
    assert "--output-dir" in output
    assert "--report" in output
    assert "--law-ids" in output
    assert "--overwrite" in output
    assert "--fail-on-warning" in output
    assert "--verbose" in output
    assert "--no-color" in output


def test_argument_defaults_and_flags_parse_correctly() -> None:
    """The parser exposes approved defaults and option semantics."""
    parser = parse_legal_hierarchy.build_arg_parser()
    defaults = parser.parse_args([])
    selected = parser.parse_args(
        [
            "--law-ids",
            "BLDS_2015",
            "LDD_VBHN",
            "--overwrite",
            "--fail-on-warning",
            "--verbose",
            "--no-color",
        ]
    )

    assert defaults.input_dir == Path("data/interim")
    assert defaults.output_dir == Path("data/interim")
    assert defaults.report == Path("artifacts/reports/parsing/legal_parsing_report.json")
    assert defaults.law_ids is None
    assert defaults.overwrite is False
    assert defaults.fail_on_warning is False
    assert defaults.verbose is False
    assert selected.law_ids == ["BLDS_2015", "LDD_VBHN"]
    assert selected.overwrite is True
    assert selected.fail_on_warning is True
    assert selected.verbose is True
    assert selected.no_color is True


def test_successful_cli_run_writes_outputs_and_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A tiny normalized law can be parsed through the CLI with temp paths."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "CLI_LAW", "Điều 1. Một\nNội dung một.")

    exit_code = parse_legal_hierarchy.main(_cli_args(input_dir, output_dir, report_path))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert (output_dir / "CLI_LAW" / "hierarchy.json").exists()
    assert report_path.exists()
    assert "Legal hierarchy parsing completed." in captured.out
    assert f"Input dir : {input_dir}" in captured.out
    assert "Summary" in captured.out
    assert "│ Total                 │ 1" in captured.out
    assert "│ Success               │ 1" in captured.out
    assert "Results" not in captured.out
    assert "No." not in captured.out
    assert "[success] CLI_LAW" not in captured.out
    assert captured.err == ""


def test_warning_exit_code_depends_on_fail_on_warning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Warning-bearing runs are zero by default and code 2 with fail-on-warning."""
    input_dir = tmp_path / "input"
    report_one = tmp_path / "reports_one" / "legal_parsing_report.json"
    report_two = tmp_path / "reports_two" / "legal_parsing_report.json"
    _write_normalized(input_dir, "WARN_LAW", "Điều 1. Một\nNội dung.", article_count=2)

    default_code = parse_legal_hierarchy.main(
        _cli_args(input_dir, tmp_path / "output_one", report_one)
    )
    fail_on_warning_code = parse_legal_hierarchy.main(
        _cli_args(
            input_dir,
            tmp_path / "output_two",
            report_two,
            "--fail-on-warning",
        )
    )

    captured = capsys.readouterr()
    assert default_code == 0
    assert fail_on_warning_code == 2
    assert "Success with warnings" in captured.out


def test_failed_documents_return_one_even_with_warnings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hard per-law failures take precedence over warning exit code 2."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "WARN_LAW", "Điều 1. Một\nNội dung.", article_count=2)
    bad_path = _write_normalized(input_dir, "BAD_LAW", "Điều 1. Hỏng\nNội dung.")
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    del payload["raw_artifact_path"]
    bad_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    exit_code = parse_legal_hierarchy.main(
        _cli_args(input_dir, output_dir, report_path, "--fail-on-warning")
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Success with warnings" in captured.out
    assert "Failed" in captured.out


def test_verbose_output_prints_result_table(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verbose mode prints deterministic per-law table rows."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung.")
    _write_normalized(input_dir, "B_LAW", "Điều 1. Hai\nNội dung.", article_count=2)
    bad_path = _write_normalized(input_dir, "BAD_LAW", "Điều 1. Hỏng\nNội dung.")
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    del payload["raw_artifact_path"]
    bad_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    exit_code = parse_legal_hierarchy.main(
        _cli_args(input_dir, output_dir, report_path, "--verbose", "--fail-on-warning")
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Results" in output
    assert "│ No. │ Law ID" in output
    assert "│ Status" in output
    assert "│ Warnings" in output
    assert "│ Errors" in output
    assert "│ Output" in output
    assert "success" in output
    assert "success_with_warnings" in output
    assert "failed" in output
    assert str(output_dir / "A_LAW" / "hierarchy.json") in output
    assert "no output" in output
    assert "[success] A_LAW" not in output
    assert "->" not in output
    assert "\x1b[" not in output


def test_no_color_disables_ansi_status_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The --no-color flag keeps verbose output free of ANSI escapes."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung.")

    exit_code = parse_legal_hierarchy.main(
        _cli_args(input_dir, output_dir, report_path, "--verbose", "--no-color")
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "\x1b[" not in output
    assert "success" in output


def test_law_id_selection_and_overwrite_behavior(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Selected law IDs and overwrite policy are passed through to the service."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "legal_parsing_report.json"
    _write_normalized(input_dir, "A_LAW", "Điều 1. Một\nNội dung.")
    _write_normalized(input_dir, "B_LAW", "Điều 1. Hai\nNội dung.")
    existing = output_dir / "A_LAW" / "hierarchy.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing", encoding="utf-8")

    blocked_code = parse_legal_hierarchy.main(
        _cli_args(input_dir, output_dir, report_path, "--law-ids", "A_LAW")
    )
    blocked_text = existing.read_text(encoding="utf-8")
    overwrite_code = parse_legal_hierarchy.main(
        _cli_args(input_dir, output_dir, report_path, "--law-ids", "A_LAW", "--overwrite")
    )

    output = capsys.readouterr().out
    assert blocked_code == 1
    assert blocked_text == "existing"
    assert overwrite_code == 0
    assert existing.read_text(encoding="utf-8") != "existing"
    assert not (output_dir / "B_LAW" / "hierarchy.json").exists()
    assert "│ Total                 │ 1" in output


def test_service_level_error_returns_three_and_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Service-level failures are reported on stderr with exit code 3."""
    issue = StructuredParsingIssue(
        code=ParsingIssueCode.GLOBAL_INPUT_OR_OUTPUT_FAILURE,
        message="forced report write failure",
        law_id="BATCH",
        context={"report_path": "forced"},
    )

    class FailingService:
        """Service double that raises a structured service error."""

        def run(self, **_: Any) -> None:
            """Raise a deterministic service-level failure."""
            raise LegalParsingServiceError(issue)

    monkeypatch.setattr(parse_legal_hierarchy, "LegalParsingService", FailingService)

    exit_code = parse_legal_hierarchy.main(
        _cli_args(tmp_path / "input", tmp_path / "output", tmp_path / "report.json")
    )

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "Legal hierarchy parsing failed: forced report write failure" in captured.err
    assert captured.out == ""


def test_importing_cli_module_is_safe(capsys: pytest.CaptureFixture[str]) -> None:
    """Importing the script exposes functions without running parsing."""
    module = importlib.reload(parse_legal_hierarchy)

    captured = capsys.readouterr()
    assert callable(module.main)
    assert callable(module.build_arg_parser)
    assert captured.out == ""
    assert captured.err == ""
