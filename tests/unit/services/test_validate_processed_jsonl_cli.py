"""Tests for the Phase 7 processed JSONL validation CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.corpus import validate_processed_jsonl
from src.processing.legal_chunk_models import (
    ChunkingLevel,
    ChunkingMetadata,
    LegalChunk,
    _compute_text_hash,
)


def _chunk(**overrides: object) -> LegalChunk:
    """Build one payload-ready Article chunk for CLI tests."""
    text = "Nội dung văn bản pháp luật đủ dài để không phát sinh cảnh báo."
    parent_text = "Điều 1. Nội dung đầy đủ của điều luật kiểm thử."
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "chunker_version": "v0.1.0",
        "chunk_id": "cli_chunk_001",
        "law_id": "CLI_LAW",
        "law_name": "Luật kiểm thử CLI",
        "source_url": "https://thuvienphapluat.vn/CLI_LAW",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "law",
        "source_file": "data/interim/CLI_LAW/hierarchy.json",
        "level": ChunkingLevel.ARTICLE,
        "chunk_kind": "article_level",
        "source_node_id": "CLI_LAW__article_1",
        "parent_article_node_id": "CLI_LAW__article_1",
        "parent_chunk_id": "CLI_LAW__article_1__parent",
        "article_number": "1",
        "article_title": "Điều 1",
        "clause_number": None,
        "point_label": None,
        "citation": "Điều 1 Luật kiểm thử CLI",
        "hierarchy_path": "Luật kiểm thử CLI/Điều 1",
        "text": text,
        "parent_text": parent_text,
        "start_offset": 0,
        "end_offset": len(text),
        "article_start_offset": 0,
        "article_end_offset": 200,
        "text_hash": _compute_text_hash(text),
        "parent_text_hash": _compute_text_hash(parent_text),
        "metadata": ChunkingMetadata(
            is_empty_or_repealed=False,
            is_source_unit_repealed=False,
        ),
        "warnings": [],
    }
    payload.update(overrides)
    return LegalChunk(**payload)


def _write_fixture(
    tmp_path: Path,
    chunk: LegalChunk | None,
    *,
    raw_line: str | None = None,
) -> tuple[Path, Path]:
    """Write complete temporary inputs and return JSONL/config paths."""
    jsonl_path = tmp_path / "input" / "legal_chunks.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_line is not None:
        jsonl_path.write_text(f"{raw_line}\n", encoding="utf-8")
    elif chunk is not None:
        jsonl_path.write_text(
            f"{json.dumps(chunk.model_dump(mode='json'), ensure_ascii=False)}\n",
            encoding="utf-8",
        )
    else:
        raise ValueError("chunk or raw_line is required")

    chunking_report = tmp_path / "inputs" / "chunking_report.json"
    chunking_report.parent.mkdir(parents=True, exist_ok=True)
    chunking_report.write_text('{"total_chunks":1}\n', encoding="utf-8")

    hierarchy_root = tmp_path / "hierarchies"
    hierarchy_path = hierarchy_root / "CLI_LAW" / "hierarchy.json"
    hierarchy_path.parent.mkdir(parents=True, exist_ok=True)
    hierarchy_path.write_text(
        json.dumps(
            {
                "law_id": "CLI_LAW",
                "nodes": [
                    {
                        "node_id": "CLI_LAW__article_1",
                        "level": "article",
                        "number": "1",
                        "parent_id": "CLI_LAW__root",
                        "children": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config_path = tmp_path / "config" / "validation.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "validator_version": "v0.1.0",
                "input_path": "overridden-by-cli.jsonl",
                "chunking_report_path": str(chunking_report),
                "hierarchy_dir": str(hierarchy_root),
                "report_path": "overridden-by-cli.json",
                "require_hierarchy_traceability": True,
                "max_sample_failures": 50,
                "max_sample_warnings": 50,
            }
        ),
        encoding="utf-8",
    )
    return jsonl_path, config_path


def _args(
    jsonl_path: Path,
    config_path: Path,
    output_path: Path,
    *extra: str,
) -> list[str]:
    """Build common CLI arguments using temporary paths."""
    return [
        "--input",
        str(jsonl_path),
        "--config",
        str(config_path),
        "--output",
        str(output_path),
        *extra,
    ]


def test_cli_argument_defaults() -> None:
    """The official command exposes stable default paths and flags."""
    args = validate_processed_jsonl.build_arg_parser().parse_args([])

    assert args.input == Path("data/processed/legal_chunks.jsonl")
    assert args.config == Path("configs/processing/processed_jsonl_validation.yml")
    assert args.output == Path("artifacts/reports/chunking/processed_jsonl_validation_report.json")
    assert args.fail_on_warnings is False
    assert args.pretty is False
    assert args.quiet is False


def test_cli_writes_report_for_pass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clean temporary corpus writes a passing complete report."""
    jsonl_path, config_path = _write_fixture(tmp_path, _chunk())
    output_path = tmp_path / "report.json"

    exit_code = validate_processed_jsonl.main(_args(jsonl_path, config_path, output_path))

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["status"] == "pass"
    assert report["embedding_readiness"]["readiness_status"] == "ready"
    assert "Phase 7 processed JSONL validation complete" in capsys.readouterr().out


def test_cli_writes_pretty_report(tmp_path: Path) -> None:
    """Pretty mode writes indented UTF-8 JSON."""
    jsonl_path, config_path = _write_fixture(tmp_path, _chunk())
    output_path = tmp_path / "pretty.json"

    exit_code = validate_processed_jsonl.main(
        _args(jsonl_path, config_path, output_path, "--pretty", "--quiet")
    )

    content = output_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert '\n  "schema_version":' in content


def test_cli_returns_1_on_fail(tmp_path: Path) -> None:
    """A hard validation error returns one and still writes the report."""
    jsonl_path, config_path = _write_fixture(
        tmp_path,
        _chunk(text_hash="0" * 64),
    )
    output_path = tmp_path / "failed.json"

    exit_code = validate_processed_jsonl.main(
        _args(jsonl_path, config_path, output_path, "--quiet")
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["status"] == "fail"
    assert report["hash_mismatches"] == 1


def test_cli_pass_with_warnings_returns_0_by_default(tmp_path: Path) -> None:
    """Warning-only validation remains non-blocking by default."""
    text = "Nội dung ngắn."
    jsonl_path, config_path = _write_fixture(
        tmp_path,
        _chunk(text=text, text_hash=_compute_text_hash(text)),
    )
    output_path = tmp_path / "warnings.json"

    exit_code = validate_processed_jsonl.main(
        _args(jsonl_path, config_path, output_path, "--quiet")
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["status"] == "pass_with_warnings"


def test_cli_fail_on_warnings_returns_2(tmp_path: Path) -> None:
    """Strict warning mode maps warning-only reports to exit code two."""
    text = "Nội dung ngắn."
    jsonl_path, config_path = _write_fixture(
        tmp_path,
        _chunk(text=text, text_hash=_compute_text_hash(text)),
    )
    output_path = tmp_path / "strict_warnings.json"

    exit_code = validate_processed_jsonl.main(
        _args(
            jsonl_path,
            config_path,
            output_path,
            "--fail-on-warnings",
            "--quiet",
        )
    )

    assert exit_code == 2


def test_cli_quiet_suppresses_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Quiet mode suppresses normal output for automation."""
    jsonl_path, config_path = _write_fixture(tmp_path, _chunk())
    output_path = tmp_path / "quiet.json"

    exit_code = validate_processed_jsonl.main(
        _args(jsonl_path, config_path, output_path, "--quiet")
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_cli_creates_parent_report_directory(tmp_path: Path) -> None:
    """Report writing creates a missing parent directory."""
    jsonl_path, config_path = _write_fixture(tmp_path, _chunk())
    output_path = tmp_path / "new" / "nested" / "report.json"

    exit_code = validate_processed_jsonl.main(
        _args(jsonl_path, config_path, output_path, "--quiet")
    )

    assert exit_code == 0
    assert output_path.exists()


def test_cli_summary_includes_embedding_readiness(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Normal summary exposes the Phase 8 gate decision."""
    jsonl_path, config_path = _write_fixture(tmp_path, _chunk())
    output_path = tmp_path / "summary.json"

    exit_code = validate_processed_jsonl.main(_args(jsonl_path, config_path, output_path))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Embedding readiness: ready" in output
    assert "Embedding ready: true" in output
    assert f"Report: {output_path}" in output
