"""Unit tests for Phase 9A.5 retrieval workflow boundaries."""

from __future__ import annotations

import json
from pathlib import Path

from src.retrieval.workflows import (
    dense_evaluation,
    dense_retrieval,
    naive_rag,
    selection_smoke,
)
from src.retrieval.workflows.common import write_json_report


def test_retrieval_scripts_are_thin_workflow_wrappers() -> None:
    """Top-level retrieval scripts should only bootstrap and call workflow main."""
    wrappers = {
        "scripts/run_dense_retrieval.py": "src.retrieval.workflows.dense_retrieval",
        "scripts/evaluate_dense_retrieval.py": "src.retrieval.workflows.dense_evaluation",
        "scripts/run_selection_smoke.py": "src.retrieval.workflows.selection_smoke",
        "scripts/run_naive_rag.py": "src.retrieval.workflows.naive_rag",
        "scripts/evaluate_naive_rag_generation.py": (
            "src.retrieval.workflows.naive_rag_generation_eval"
        ),
    }

    for script_path, module_name in wrappers.items():
        source = Path(script_path).read_text(encoding="utf-8")
        assert f"from {module_name} import main" in source
        assert "def build_arg_parser" not in source
        assert "async def run_" not in source


def test_common_json_writer_creates_parent_directory(tmp_path: Path) -> None:
    """Shared JSON writer writes UTF-8 JSON and creates parent directories."""
    output = tmp_path / "nested" / "report.json"

    write_json_report(output, {"message": "quyền dân sự"})

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload == {"message": "quyền dân sự"}


def test_workflow_parsers_accept_existing_command_flags() -> None:
    """Workflow parsers preserve existing user-facing script arguments."""
    retrieval_args = dense_retrieval.build_arg_parser().parse_args(
        [
            "--query",
            "Quyền dân sự được công nhận và bảo vệ như thế nào?",
            "--collection-name",
            "vnlaw_chunks_bgem3_v1_full",
            "--url",
            "http://localhost:6333",
            "--top-k",
            "10",
            "--device",
            "cpu",
            "--output",
            "artifacts/reports/retrieval/manual_query_result.json",
        ]
    )
    evaluation_args = dense_evaluation.build_arg_parser().parse_args(
        [
            "--queries",
            "data/eval/manual_retrieval_queries.jsonl",
            "--top-k",
            "20",
            "--device",
            "cpu",
        ]
    )
    smoke_args = selection_smoke.build_arg_parser().parse_args(
        [
            "--queries",
            "data/eval/manual_retrieval_queries.jsonl",
            "--top-k",
            "20",
            "--device",
            "cpu",
            "--case-id",
            "civil_rights_protection",
            "--strict",
        ]
    )
    rag_args = naive_rag.build_arg_parser().parse_args(
        [
            "--query",
            "Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?",
            "--collection-name",
            "vnlaw_chunks_bgem3_v1_full",
            "--url",
            "http://localhost:6333",
            "--top-k",
            "20",
            "--device",
            "cpu",
            "--provider",
            "openrouter",
            "--model",
            "google/gemini-2.5-flash",
            "--output",
            "artifacts/reports/retrieval/naive_rag_single_query.json",
            "--strict-citations",
            "--no-auxiliary-context",
        ]
    )
    assert retrieval_args.query.startswith("Quyền dân sự")
    assert retrieval_args.top_k == 10
    assert evaluation_args.top_k == 20
    assert smoke_args.case_id == "civil_rights_protection"
    assert smoke_args.strict is True
    assert rag_args.provider == "openrouter"
    assert rag_args.strict_citations is True
    assert rag_args.no_auxiliary_context is True
