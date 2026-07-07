"""Tests for Qdrant client construction in evaluation workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.evaluation import qdrant as evaluation_qdrant


def test_evaluation_qdrant_client_preserves_unauthenticated_local_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_build_qdrant_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(evaluation_qdrant, "build_qdrant_client", fake_build_qdrant_client)

    evaluation_qdrant.build_evaluation_qdrant_client(
        url="http://localhost:6333",
        timeout_seconds=60,
        environ={},
    )

    assert captured == {
        "url": "http://localhost:6333",
        "timeout_seconds": 60,
        "api_key": None,
    }


def test_evaluation_qdrant_client_passes_environment_api_key_without_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Any] = {}

    def fake_build_qdrant_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(evaluation_qdrant, "build_qdrant_client", fake_build_qdrant_client)

    evaluation_qdrant.build_evaluation_qdrant_client(
        url="https://qdrant.example",
        timeout_seconds=60,
        environ={"QDRANT_API_KEY": " unit-test-qdrant-api-key "},
    )

    assert captured == {
        "url": "https://qdrant.example",
        "timeout_seconds": 60,
        "api_key": "unit-test-qdrant-api-key",
    }
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_evaluation_runners_use_authenticated_qdrant_helper() -> None:
    runner_paths = [
        Path("scripts/evaluation/run_frozen_retrieval_baseline.py"),
        Path("scripts/evaluation/run_frozen_hybrid_retrieval_baseline.py"),
        Path("scripts/evaluation/run_fusion_ablation.py"),
        Path("scripts/evaluation/run_coverage_aware_hybrid_retrieval.py"),
        Path("scripts/evaluation/run_reranking_ablation.py"),
        Path("scripts/evaluation/run_reranked_retrieval.py"),
        Path("scripts/evaluation/run_strict_generation_evaluation.py"),
    ]

    for path in runner_paths:
        source = path.read_text(encoding="utf-8")
        assert "build_evaluation_qdrant_client(" in source, path
        assert "build_qdrant_client(" not in source, path
