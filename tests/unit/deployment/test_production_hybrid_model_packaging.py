from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_backend_dockerfile_packages_bge_m3_model_snapshot() -> None:
    dockerfile = (REPO_ROOT / "docker/backend/Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim AS embedding-model" in dockerfile
    assert "huggingface_hub==1.18.0" in dockerfile
    assert "snapshot_download(" in dockerfile
    assert "BAAI/bge-m3" in dockerfile
    assert "5617a9f61b028005a4858fdac845db406aefb181" in dockerfile
    assert (
        "COPY --from=embedding-model /models/embedding/bge-m3 /models/embedding/bge-m3"
        in dockerfile
    )
    assert "EMBEDDING_MODEL_PATH=/models/embedding/bge-m3" in dockerfile
    assert "HF_HUB_OFFLINE=1" in dockerfile
    assert "TRANSFORMERS_OFFLINE=1" in dockerfile


def test_production_deploy_preserves_hybrid_retrieval_and_model_path() -> None:
    workflow = (REPO_ROOT / ".github/workflows/deploy-production-container.yml").read_text(
        encoding="utf-8"
    )

    assert "EMBEDDING_MODEL_ID: BAAI/bge-m3" in workflow
    assert "EMBEDDING_MODEL_REVISION: 5617a9f61b028005a4858fdac845db406aefb181" in workflow
    assert "EMBEDDING_MODEL_PATH: /models/embedding/bge-m3" in workflow
    assert "--build-arg EMBEDDING_MODEL_PATH=" in workflow
    assert "Assert production backend image artifacts" in workflow
    assert "LEGAL_QA_RETRIEVAL_MODE=hybrid" in workflow
    assert "LEGAL_QA_RETRIEVAL_MODE=sparse" not in workflow
    assert "LEGAL_QA_RERANKING_ENABLED=false" in workflow
    assert "LEGAL_QA_MAX_TOP_K=5" in workflow
    assert "LEGAL_QA_WARMUP_ENDPOINT_ENABLED=true" in workflow
    assert 'EMBEDDING_MODEL_PATH="$EMBEDDING_MODEL_PATH"' in workflow


def test_production_ask_smoke_requires_packaged_model_warmup() -> None:
    workflow = (REPO_ROOT / ".github/workflows/production-ask-smoke.yml").read_text(
        encoding="utf-8"
    )

    assert "Verify production embedding warmup" in workflow
    assert "--max-time 220" in workflow
    assert "Warmup did not complete successfully; ask smoke was not sent." in workflow
    assert '"model_path_configured"' in workflow
    assert '"model_path_exists"' in workflow
    assert '"required_files_present"' in workflow
    assert '"model_load_completed"' in workflow
    assert '"encode_completed"' in workflow
