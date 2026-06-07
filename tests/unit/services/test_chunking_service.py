"""Tests for the Phase 6 batch chunking service."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.processing.legal_chunk_models import ChunkingIssueCode, ChunkingStatus, LegalChunk
from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalHierarchyMetadata,
    LegalNode,
    LegalNodeLevel,
)
from src.services.chunking_service import (
    ChunkingService,
    ChunkingServiceError,
    discover_hierarchy_inputs,
)


class StepClock:
    """Deterministic UTC clock for service timing tests."""

    def __init__(self) -> None:
        """Initialize the clock at a stable UTC instant."""
        self._current = datetime(2026, 6, 7, 0, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        """Return the current instant and advance by one second."""
        value = self._current
        self._current += timedelta(seconds=1)
        return value


def _metadata(*, law_id: str, law_name: str) -> LegalHierarchyMetadata:
    """Create hierarchy metadata for service fixtures."""
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


def _document(*, law_id: str = "A_LAW", law_name: str | None = None) -> LegalHierarchyDocument:
    """Build a valid parent-inclusive hierarchy document."""
    title = law_name or f"Luật Kiểm thử {law_id}"
    root_text = "\n".join(
        [
            title,
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
        metadata=_metadata(law_id=law_id, law_name=title),
        warnings=[],
        nodes=[
            LegalNode(
                node_id=root_id,
                level=LegalNodeLevel.LAW,
                number=None,
                title=title,
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


def _run_service(
    input_dir: Path,
    output_path: Path,
    report_path: Path,
    *,
    law_ids: list[str] | None = None,
    overwrite: bool = False,
    chunk_writer: Any | None = None,
    report_writer: Any | None = None,
):
    """Run the chunking service with a deterministic clock."""
    return ChunkingService(
        clock=StepClock(),
        chunk_writer=chunk_writer,
        report_writer=report_writer,
    ).run(
        input_dir=input_dir,
        output_path=output_path,
        report_path=report_path,
        law_ids=law_ids,
        overwrite=overwrite,
    )


def test_discovers_filters_and_sorts_hierarchy_inputs(tmp_path: Path) -> None:
    """Discovery only selects hierarchy.json files under law ID directories."""
    input_dir = tmp_path / "input"
    _write_hierarchy(input_dir, _document(law_id="B_LAW"))
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))
    (input_dir / "loose_hierarchy.json").write_text("{}", encoding="utf-8")

    discovered = discover_hierarchy_inputs(input_dir)
    selected = discover_hierarchy_inputs(input_dir, law_ids=["B_LAW"])

    assert [item.law_id for item in discovered] == ["A_LAW", "B_LAW"]
    assert [item.law_id for item in selected] == ["B_LAW"]
    assert discovered[0].hierarchy_path == input_dir / "A_LAW" / "hierarchy.json"


def test_successful_run_writes_utf8_jsonl_and_report(tmp_path: Path) -> None:
    """Successful hierarchy inputs are chunked into corpus JSONL and report JSON."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW", law_name="Luật Kiểm thử A"))
    _write_hierarchy(input_dir, _document(law_id="B_LAW", law_name="Luật Kiểm thử B"))

    result = _run_service(input_dir, output_path, report_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    chunks = [LegalChunk.model_validate(json.loads(line)) for line in lines]

    assert result.report.total_laws == 2
    assert result.report.successful == 2
    assert result.report.failed == 0
    assert result.written_chunk_count == 2
    assert [chunk.law_id for chunk in chunks] == ["A_LAW", "B_LAW"]
    assert "\\u" not in output_path.read_text(encoding="utf-8")
    assert report_payload["chunks_by_law"] == {"A_LAW": 1, "B_LAW": 1}
    assert report_payload["chunks_by_level"] == {"point": 2}


def test_requested_missing_law_is_isolated_and_reported(tmp_path: Path) -> None:
    """Requested missing law IDs become failed per-law summaries."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))

    result = _run_service(
        input_dir,
        output_path,
        report_path,
        law_ids=["MISSING_LAW", "A_LAW"],
    )

    assert result.report.total_laws == 2
    assert result.report.successful == 1
    assert result.report.failed == 1
    assert result.failed_law_ids == ["MISSING_LAW"]
    assert [summary.law_id for summary in result.report.law_summaries] == [
        "A_LAW",
        "MISSING_LAW",
    ]
    assert result.report.errors[0].code == ChunkingIssueCode.MISSING_HIERARCHY_INPUT
    assert output_path.read_text(encoding="utf-8").count("\n") == 1


def test_invalid_hierarchy_schema_is_isolated(tmp_path: Path) -> None:
    """One invalid hierarchy does not block successful laws from being written."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))
    bad_path = _write_hierarchy(input_dir, _document(law_id="BAD_LAW"))
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    del payload["metadata"]["law_name"]
    bad_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _run_service(input_dir, output_path, report_path)

    assert result.report.successful == 1
    assert result.report.failed == 1
    assert result.failed_law_ids == ["BAD_LAW"]
    assert result.report.errors[0].code == ChunkingIssueCode.SCHEMA_VALIDATION_FAILED
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 1


def test_existing_outputs_require_overwrite(tmp_path: Path) -> None:
    """Existing JSONL or report files are protected unless overwrite=True."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))
    output_path.parent.mkdir(parents=True)
    output_path.write_text("existing", encoding="utf-8")

    with pytest.raises(ChunkingServiceError) as exc_info:
        _run_service(input_dir, output_path, report_path)

    assert exc_info.value.issue.code == ChunkingIssueCode.EXISTING_OUTPUT_BLOCKED
    assert output_path.read_text(encoding="utf-8") == "existing"

    result = _run_service(input_dir, output_path, report_path, overwrite=True)
    assert result.report.successful == 1
    assert output_path.read_text(encoding="utf-8") != "existing"


def test_writer_failure_raises_service_error(tmp_path: Path) -> None:
    """Writer failures become service-level errors."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))

    def failing_writer(path: Path, chunks: list[LegalChunk]) -> None:
        raise OSError(f"cannot write {path} with {len(chunks)} chunks")

    with pytest.raises(ChunkingServiceError) as exc_info:
        _run_service(input_dir, output_path, report_path, chunk_writer=failing_writer)

    assert exc_info.value.issue.code == ChunkingIssueCode.OUTPUT_WRITE_FAILED
    assert not output_path.exists()


def test_deterministic_rerun_produces_identical_jsonl(tmp_path: Path) -> None:
    """Repeated runs over the same inputs produce identical JSONL rows."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"
    _write_hierarchy(input_dir, _document(law_id="A_LAW"))

    first = _run_service(input_dir, output_path, report_path)
    first_jsonl = output_path.read_text(encoding="utf-8")
    second = _run_service(input_dir, output_path, report_path, overwrite=True)
    second_jsonl = output_path.read_text(encoding="utf-8")

    assert first_jsonl == second_jsonl
    assert first.report.total_chunks == second.report.total_chunks


def test_summary_status_with_failed_law(tmp_path: Path) -> None:
    """Failed laws use ChunkingStatus.FAILED in law summaries."""
    input_dir = tmp_path / "input"
    output_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "chunking_report.json"

    result = _run_service(input_dir, output_path, report_path, law_ids=["MISSING_LAW"])

    assert result.report.law_summaries[0].status == ChunkingStatus.FAILED
