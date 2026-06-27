"""Integration tests for optional final evaluation artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_coverage_aware_retrieval_artifact_contract_if_available() -> None:
    """Check final retrieval artifact contract when local artifacts exist."""
    artifact_dir = Path("artifacts/reports/evaluation/advanced_rag/coverage_aware_retrieval")
    if not artifact_dir.exists():
        pytest.skip("Final retrieval artifacts are not available in this checkout")

    metrics_path = artifact_dir / "metrics_all.json"
    manifest_candidates = sorted(artifact_dir.glob("*manifest*.json"))
    assert metrics_path.exists()
    assert manifest_candidates
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_candidates[0].read_text(encoding="utf-8"))
    serialized_manifest = json.dumps(manifest, ensure_ascii=False)

    assert "coverage_aware_quota" in serialized_manifest
    assert "query_count" in metrics or "query_count" in manifest
    assert {"recall_at_10", "evidence_group_coverage_at_10"} & set(metrics)


def test_strict_generation_artifact_contract_if_available() -> None:
    """Check final strict generation artifact contract when local artifacts exist."""
    artifact_dir = Path(
        "artifacts/reports/evaluation/advanced_rag/"
        "strict_generation_evaluation_answerability_fallback_guard"
    )
    if not artifact_dir.exists():
        pytest.skip("Final strict generation artifacts are not available in this checkout")

    required = {
        "baseline_manifest.json",
        "metrics_all.json",
        "metrics_development.json",
        "metrics_held_out_test.json",
        "comparison.json",
        "case_results.jsonl",
    }
    assert required <= {path.name for path in artifact_dir.iterdir()}
    metrics = json.loads((artifact_dir / "metrics_all.json").read_text(encoding="utf-8"))
    manifest = json.loads((artifact_dir / "baseline_manifest.json").read_text(encoding="utf-8"))

    assert {
        "decision_accuracy",
        "answer_allowed_answer_rate",
        "fallback_required_fallback_rate",
        "citation_id_validity_rate",
        "retrieval_error_count",
        "generation_error_count",
    } <= metrics.keys()
    assert manifest["reranking_used"] is False
    assert manifest["held_out_used_for_tuning"] is False
