"""Integration tests for processed JSONL export and validation."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.corpus import validate_processed_jsonl
from src.processing.legal_chunk_models import LegalChunk
from src.processing.legal_chunker import LegalChunker
from src.processing.legal_hierarchy_models import LegalParsingStatus
from src.processing.legal_parser import LegalParser

TINY_LEGAL_TEXT = """Chương I
QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Luật này quy định về phạm vi điều chỉnh.
a) Điểm a quy định nội dung cụ thể.
b) Điểm b quy định nội dung khác.

Điều 2. Đối tượng áp dụng
1. Luật này áp dụng đối với cơ quan, tổ chức, cá nhân có liên quan.
"""


def test_processed_jsonl_validation_workflow_accepts_valid_tiny_jsonl(
    tmp_path: Path,
) -> None:
    """Tiny chunks can be exported to JSONL and accepted by the validation CLI."""
    hierarchy_dir, chunks = _build_tiny_chunks(tmp_path)
    jsonl_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "processed_jsonl_validation_report.json"
    config_path = _write_validation_config(
        tmp_path,
        jsonl_path=jsonl_path,
        hierarchy_dir=hierarchy_dir,
        expected_chunks=len(chunks),
    )
    _write_jsonl(jsonl_path, chunks)

    raw_lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    parsed_lines = [json.loads(line) for line in raw_lines]
    exit_code = validate_processed_jsonl.main(
        [
            "--input",
            str(jsonl_path),
            "--config",
            str(config_path),
            "--output",
            str(report_path),
            "--quiet",
        ]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert len(raw_lines) == len(chunks)
    assert all("chunk_id" in line for line in parsed_lines)
    assert all("law_id" in line for line in parsed_lines)
    assert all("citation" in line for line in parsed_lines)
    assert exit_code == 0
    assert report["total_lines"] == len(chunks)
    assert report["valid_chunks"] == len(chunks)
    assert report["invalid_chunks"] == 0
    assert report["errors_total"] == 0
    assert jsonl_path.is_relative_to(tmp_path)
    assert report_path.is_relative_to(tmp_path)
    assert not (Path("data") / "processed" / "legal_chunks.jsonl").is_relative_to(tmp_path)


def test_processed_jsonl_validation_workflow_rejects_invalid_tiny_jsonl(
    tmp_path: Path,
) -> None:
    """The same validation CLI rejects malformed temporary JSONL."""
    hierarchy_dir, chunks = _build_tiny_chunks(tmp_path)
    jsonl_path = tmp_path / "processed" / "legal_chunks.jsonl"
    report_path = tmp_path / "reports" / "invalid_processed_jsonl_report.json"
    config_path = _write_validation_config(
        tmp_path,
        jsonl_path=jsonl_path,
        hierarchy_dir=hierarchy_dir,
        expected_chunks=len(chunks),
    )
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text('{"chunk_id": "broken", "law_id": "TINY_LAW"}\n', encoding="utf-8")

    exit_code = validate_processed_jsonl.main(
        [
            "--input",
            str(jsonl_path),
            "--config",
            str(config_path),
            "--output",
            str(report_path),
            "--quiet",
        ]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["status"] == "fail"
    assert report["invalid_chunks"] == 1
    assert report["schema_failures"] + report["required_field_failures"] > 0
    assert report["errors_total"] > 0


def _build_tiny_chunks(tmp_path: Path) -> tuple[Path, list[LegalChunk]]:
    """Parse and chunk a tiny law fixture using only temporary paths."""
    normalized_path = _write_normalized_artifact(tmp_path, TINY_LEGAL_TEXT)
    parse_result = LegalParser().parse_file(normalized_path=normalized_path)
    assert parse_result.status == LegalParsingStatus.SUCCESS
    assert parse_result.document is not None
    document = parse_result.document

    hierarchy_dir = tmp_path / "hierarchies"
    hierarchy_path = hierarchy_dir / document.law_id / "hierarchy.json"
    hierarchy_path.parent.mkdir(parents=True)
    hierarchy_path.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    chunks = LegalChunker().chunk_document(document, source_file=str(hierarchy_path))
    return hierarchy_dir, chunks


def _write_normalized_artifact(tmp_path: Path, normalized_text: str) -> Path:
    """Write a tiny normalized artifact using only temporary paths."""
    law_dir = tmp_path / "interim" / "TINY_LAW"
    law_dir.mkdir(parents=True)
    normalized_path = law_dir / "normalized.json"
    normalized_path.write_text(
        json.dumps(
            {
                "law_id": "TINY_LAW",
                "law_name": "Luật Kiểm thử",
                "source_url": "https://thuvienphapluat.vn/tiny-law",
                "source_domain": "thuvienphapluat.vn",
                "source_type": "html",
                "raw_artifact_path": str(tmp_path / "raw" / "TINY_LAW" / "latest" / "main.html"),
                "normalized_text": normalized_text,
                "text_stats": {
                    "normalized_text_chars": len(normalized_text),
                    "line_count": len(normalized_text.splitlines()),
                },
                "markers": {
                    "article_reference_count": 2,
                    "article_heading_count": 2,
                    "max_heading_article_number": 2,
                    "has_heading_article_1": True,
                    "heading_sequence_score": 1.0,
                },
                "warnings": [],
                "metadata": {"cleaner_version": "v0.8.0"},
                "candidate_info": {"selection_strategy": "tiny_fixture"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return normalized_path


def _write_jsonl(jsonl_path: Path, chunks: list[LegalChunk]) -> None:
    """Write temporary chunks as valid JSON Lines."""
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text(
        "".join(
            json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) + "\n" for chunk in chunks
        ),
        encoding="utf-8",
    )


def _write_validation_config(
    tmp_path: Path,
    *,
    jsonl_path: Path,
    hierarchy_dir: Path,
    expected_chunks: int,
) -> Path:
    """Write validation config and chunking report under temporary paths."""
    chunking_report_path = tmp_path / "reports" / "chunking_report.json"
    chunking_report_path.parent.mkdir(parents=True, exist_ok=True)
    chunking_report_path.write_text(
        json.dumps({"total_chunks": expected_chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    config_path = tmp_path / "config" / "processed_jsonl_validation.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "validator_version": "v0.1.0",
                "input_path": str(jsonl_path),
                "chunking_report_path": str(chunking_report_path),
                "hierarchy_dir": str(hierarchy_dir),
                "report_path": str(tmp_path / "reports" / "unused.json"),
                "require_hierarchy_traceability": True,
                "max_sample_failures": 50,
                "max_sample_warnings": 50,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config_path
