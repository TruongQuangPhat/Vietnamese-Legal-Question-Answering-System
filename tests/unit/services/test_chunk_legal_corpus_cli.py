"""Tests for the Phase 6 legal chunking CLI entrypoint."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import chunk_legal_corpus
from src.processing.legal_chunk_models import (
    ChunkingIssue,
    ChunkingIssueCode,
    ChunkingReport,
    ChunkingStatus,
    ChunkingSummary,
)
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
)
from src.services.chunking_service import ChunkingServiceError, ChunkingServiceResult


def _metadata(*, law_id: str, law_name: str) -> LegalHierarchyMetadata:
    """Create hierarchy metadata for CLI fixtures."""
    return LegalHierarchyMetadata(
        law_name=law_name,
        source_url=f"https://thuvienphapluat.vn/{law_id}.aspx",
        source_domain="thuvienphapluat.vn",
        source_type="html",
        raw_artifact_path=f"data/raw/{law_id}/latest/main.html",
        article_heading_count=1,
        max_heading_article_number=1,
        has_heading_article_1=True,
        heading_sequence_score=1.0,
    )


def _document(*, law_id: str = "CLI_LAW") -> LegalHierarchyDocument:
    """Build a minimal valid hierarchy document for CLI temp-path runs."""
    law_name = f"Luật Kiểm thử {law_id}"
    root_text = "\n".join(
        [
            law_name,
            "Điều 1. Phạm vi điều chỉnh",
            "Khoản 1. Nội dung khoản.",
            "Điểm a. Nội dung điểm.",
            "",
        ]
    )
    root_id = f"{law_id}__root"
    article_id = f"{root_id}__article_1"
    clause_id = f"{article_id}__clause_1"
    point_id = f"{clause_id}__point_a"
    article_start = root_text.index("Điều 1.")
    clause_start = root_text.index("Khoản 1.")
    point_start = root_text.index("Điểm a.")

    return LegalHierarchyDocument(
        schema_version="1.0",
        parser_version="v0.1.0",
        cleaner_version="v0.8.0",
        law_id=law_id,
        source_file=f"data/interim/{law_id}/normalized.json",
        root_node_id=root_id,
        metadata=_metadata(law_id=law_id, law_name=law_name),
        warnings=[],
        nodes=[
            LegalNode(
                node_id=root_id,
                level=LegalNodeLevel.LAW,
                number=None,
                title=law_name,
                text=root_text,
                start_offset=0,
                end_offset=len(root_text),
                parent_id=None,
                children=[article_id],
            ),
            LegalNode(
                node_id=article_id,
                level=LegalNodeLevel.ARTICLE,
                number="1",
                title="Phạm vi điều chỉnh",
                text=root_text[article_start:],
                start_offset=article_start,
                end_offset=len(root_text),
                parent_id=root_id,
                children=[clause_id],
            ),
            LegalNode(
                node_id=clause_id,
                level=LegalNodeLevel.CLAUSE,
                number="1",
                title=None,
                text=root_text[clause_start:],
                start_offset=clause_start,
                end_offset=len(root_text),
                parent_id=article_id,
                children=[point_id],
            ),
            LegalNode(
                node_id=point_id,
                level=LegalNodeLevel.POINT,
                number="a",
                title=None,
                text=root_text[point_start:],
                start_offset=point_start,
                end_offset=len(root_text),
                parent_id=clause_id,
                children=[],
            ),
        ],
    )


def _write_hierarchy(input_dir: Path, document: LegalHierarchyDocument) -> Path:
    """Write one hierarchy fixture under input_dir/{LAW_ID}/hierarchy.json."""
    path = input_dir / document.law_id / "hierarchy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _cli_args(
    input_dir: Path,
    output_path: Path,
    report_path: Path,
    *extra: str,
) -> list[str]:
    """Build common CLI arguments with temp paths."""
    return [
        "--input-dir",
        str(input_dir),
        "--output",
        str(output_path),
        "--report",
        str(report_path),
        *extra,
    ]


def _report(
    *,
    failed: int = 0,
    success_with_warnings: int = 0,
    warnings: list[ChunkingIssue] | None = None,
) -> ChunkingReport:
    """Build a small report for monkeypatched CLI service tests."""
    status = ChunkingStatus.SUCCESS
    if failed:
        status = ChunkingStatus.FAILED
    elif success_with_warnings:
        status = ChunkingStatus.SUCCESS_WITH_WARNINGS

    return ChunkingReport(
        schema_version="1.0",
        chunker_version="v0.1.0",
        started_at="2026-06-07T00:00:00Z",
        finished_at="2026-06-07T00:00:01Z",
        duration_seconds=1.0,
        input_dir="input",
        output_path="output/legal_chunks.jsonl",
        total_laws=1,
        successful=0 if failed or success_with_warnings else 1,
        success_with_warnings=success_with_warnings,
        failed=failed,
        total_chunks=0 if failed else 1,
        chunks_by_level={"article": 1} if not failed else {},
        chunks_by_law={"A_LAW": 1} if not failed else {},
        warnings=warnings or [],
        errors=[],
        law_summaries=[
            ChunkingSummary(
                law_id="A_LAW",
                status=status,
                input_path="input/A_LAW/hierarchy.json",
                total_chunks=0 if failed else 1,
                warning_count=len(warnings or []),
                error_count=failed,
            )
        ],
    )


def test_help_and_argument_parsing(capsys: pytest.CaptureFixture[str]) -> None:
    """Help text and supported flags are exposed by the CLI parser."""
    with pytest.raises(SystemExit) as exc_info:
        chunk_legal_corpus.main(["--help"])

    output = capsys.readouterr().out
    assert exc_info.value.code == 0
    assert "--input-dir" in output
    assert "--output" in output
    assert "--report" in output
    assert "--law-ids" in output
    assert "--overwrite" in output
    assert "--fail-on-warning" in output
    assert "--verbose" in output
    assert "--no-color" in output


def test_argument_defaults_and_flags_parse_correctly() -> None:
    """The parser exposes approved defaults and option semantics."""
    parser = chunk_legal_corpus.build_arg_parser()
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
    assert defaults.output == Path("data/processed/legal_chunks.jsonl")
    assert defaults.report == Path("artifacts/reports/chunking/chunking_report.json")
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
    """A tiny hierarchy law can be chunked through the CLI with temp paths."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="CLI_LAW"))

    exit_code = chunk_legal_corpus.main(_cli_args(input_dir, output_path, report_path))

    captured = capsys.readouterr()
    output_payload = output_path.read_text(encoding="utf-8")
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output_path.exists()
    assert report_path.exists()
    assert report_payload["total_laws"] == 1
    assert "Luật Kiểm thử CLI_LAW" in output_payload
    assert "Legal chunking completed." in captured.out
    assert f"Input dir: {input_dir}" in captured.out
    assert f"Output   : {output_path}" in captured.out
    assert "Summary" in captured.out
    assert "│ Total laws            │ 1" in captured.out
    assert "│ Success               │ 1" in captured.out
    assert "│ Total chunks          │ 1" in captured.out
    assert "Results" not in captured.out
    assert '"chunk_id"' not in captured.out
    assert captured.err == ""


def test_failed_documents_return_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Per-law failures return exit code 1 and still write temp reports."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"

    exit_code = chunk_legal_corpus.main(
        _cli_args(input_dir, output_path, report_path, "--law-ids", "MISSING_LAW")
    )

    captured = capsys.readouterr()
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert output_path.read_text(encoding="utf-8") == ""
    assert report_payload["failed"] == 1
    assert "│ Failed                │ 1" in captured.out
    assert captured.err == ""


def test_warning_exit_code_depends_on_fail_on_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Warning-bearing reports are zero by default and code 2 when requested."""
    issue = ChunkingIssue(
        code=ChunkingIssueCode.EMPTY_ARTICLE_CHUNK,
        message="empty article chunk",
        law_id="A_LAW",
    )

    class WarningService:
        """Service double returning a deterministic warning report."""

        def run(self, **_: Any) -> ChunkingServiceResult:
            """Return a warning-bearing service result."""
            report = _report(success_with_warnings=1, warnings=[issue])
            return ChunkingServiceResult(
                report=report,
                output_path=report.output_path,
                report_path="report.json",
                failed_law_ids=[],
                written_chunk_count=1,
            )

    monkeypatch.setattr(chunk_legal_corpus, "ChunkingService", WarningService)

    default_code = chunk_legal_corpus.main([])
    fail_on_warning_code = chunk_legal_corpus.main(["--fail-on-warning"])

    captured = capsys.readouterr()
    assert default_code == 0
    assert fail_on_warning_code == 2
    assert "Success with warnings" in captured.out


def test_failed_documents_take_precedence_over_fail_on_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hard failures return code 1 even when fail-on-warning is enabled."""

    class FailedService:
        """Service double returning one failed law."""

        def run(self, **_: Any) -> ChunkingServiceResult:
            """Return a failed service result."""
            report = _report(failed=1)
            return ChunkingServiceResult(
                report=report,
                output_path=report.output_path,
                report_path="report.json",
                failed_law_ids=["A_LAW"],
                written_chunk_count=0,
            )

    monkeypatch.setattr(chunk_legal_corpus, "ChunkingService", FailedService)

    assert chunk_legal_corpus.main(["--fail-on-warning"]) == 1


def test_verbose_output_prints_result_table(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verbose mode prints deterministic per-law table rows."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))
    _write_hierarchy(input_dir, _document(law_id="B_LAW"))

    exit_code = chunk_legal_corpus.main(
        _cli_args(input_dir, output_path, report_path, "--verbose", "--no-color")
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Results" in output
    assert "│ No. │ Law ID" in output
    assert "│ Status" in output
    assert "│ Chunks" in output
    assert "│ Warnings" in output
    assert "│ Errors" in output
    assert "│ Input" in output
    assert "success" in output
    assert str(input_dir / "A_LAW" / "hierarchy.json") in output
    assert str(input_dir / "B_LAW" / "hierarchy.json") in output
    assert "\x1b[" not in output


def test_no_color_disables_ansi_status_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The --no-color flag keeps verbose output free of ANSI escapes."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))

    exit_code = chunk_legal_corpus.main(
        _cli_args(input_dir, output_path, report_path, "--verbose", "--no-color")
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
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))
    _write_hierarchy(input_dir, _document(law_id="B_LAW"))
    output_path.parent.mkdir(parents=True)
    output_path.write_text("existing", encoding="utf-8")

    blocked_code = chunk_legal_corpus.main(
        _cli_args(input_dir, output_path, report_path, "--law-ids", "A_LAW")
    )
    blocked_text = output_path.read_text(encoding="utf-8")
    overwrite_code = chunk_legal_corpus.main(
        _cli_args(input_dir, output_path, report_path, "--law-ids", "A_LAW", "--overwrite")
    )

    output = capsys.readouterr().out
    assert blocked_code == 3
    assert blocked_text == "existing"
    assert overwrite_code == 0
    assert output_path.read_text(encoding="utf-8") != "existing"
    assert "B_LAW" not in output_path.read_text(encoding="utf-8")
    assert "│ Total laws            │ 1" in output


def test_service_level_error_returns_three_and_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Service-level failures are reported on stderr with exit code 3."""
    issue = ChunkingIssue(
        code=ChunkingIssueCode.OUTPUT_WRITE_FAILED,
        message="forced report write failure",
        law_id="BATCH",
    )

    class FailingService:
        """Service double that raises a structured service error."""

        def run(self, **_: Any) -> None:
            """Raise a deterministic service-level failure."""
            raise ChunkingServiceError(issue)

    monkeypatch.setattr(chunk_legal_corpus, "ChunkingService", FailingService)

    exit_code = chunk_legal_corpus.main([])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "Legal chunking failed: forced report write failure" in captured.err
    assert captured.out == ""


def test_importing_cli_module_is_safe(capsys: pytest.CaptureFixture[str]) -> None:
    """Importing the script exposes functions without running chunking."""
    module = importlib.reload(chunk_legal_corpus)

    captured = capsys.readouterr()
    assert callable(module.main)
    assert callable(module.build_arg_parser)
    assert captured.out == ""
    assert captured.err == ""
